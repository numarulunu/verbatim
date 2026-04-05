"""
Transcriptor Bridge — JSON interface for the Electron app.

Wraps process_v2.py's MaterialProcessor and outputs JSON progress lines
instead of ANSI terminal output. Same pattern as Video Convertor's --run mode.

Usage:
    python bridge.py --scan --job job.json     # List pending files as JSON
    python bridge.py --run --job job.json      # Process with JSON progress output
    python bridge.py --detect                  # System info as JSON
"""

import os
import sys
import json
import argparse
import time
import threading
from pathlib import Path

# Add backend to path — but DON'T import heavy modules at top level.
# Only import torch/whisper/etc when actually needed (--run and --detect).
BACKEND_DIR = Path(__file__).resolve().parent.parent / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

os.environ['PIPELINE_QUIET'] = '1'

SUPPORTED_EXTS = {
    'audio': {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus'},
    'video': {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.ts'},
    'image': {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'},
    'pdf': {'.pdf'},
    'document': {'.docx', '.xlsx', '.pptx', '.csv', '.txt', '.rtf'},
}

ALL_EXTS = set()
for v in SUPPORTED_EXTS.values():
    ALL_EXTS |= v


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def load_job(job_path):
    with open(job_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def cmd_detect():
    """Output system info as JSON."""
    info = {
        'python': sys.version,
        'backend_dir': str(BACKEND_DIR),
        'backend_exists': BACKEND_DIR.exists(),
    }
    # Check for GPU/CUDA
    try:
        import torch
        info['cuda'] = torch.cuda.is_available()
        if info['cuda']:
            info['gpu_name'] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            info['vram_gb'] = round((getattr(props, 'total_memory', 0) or getattr(props, 'total_mem', 0)) / (1024**3), 1)
    except ImportError:
        info['cuda'] = False

    # Check for whisper
    try:
        import faster_whisper
        info['whisper'] = True
    except ImportError:
        info['whisper'] = False

    # Check for tesseract
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        info['tesseract'] = True
    except Exception:
        info['tesseract'] = False

    emit(info)


def cmd_scan(job):
    """Scan for files and output JSON list."""
    input_dir = Path(job['input'])
    output_dir = Path(job['output'])

    if not input_dir.is_dir():
        emit({'files': [], 'done': [], 'error': 'Input folder not found'})
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Get existing output files
    done_names = set()
    if output_dir.is_dir():
        done_names = {f.stem.lower() for f in output_dir.iterdir() if f.suffix == '.txt'}

    pending = []
    done = []

    for fpath in sorted(input_dir.rglob('*')):
        if not fpath.is_file():
            continue
        ext = fpath.suffix.lower()
        if ext not in ALL_EXTS:
            continue

        # Determine file type
        file_type = 'unknown'
        for t, exts in SUPPORTED_EXTS.items():
            if ext in exts:
                file_type = t
                break

        # Check if already transcribed
        if fpath.stem.lower() in done_names:
            out_file = None
            for f in output_dir.iterdir():
                if f.stem.lower() == fpath.stem.lower() and f.suffix == '.txt':
                    out_file = f
                    break
            done.append({
                'path': str(fpath),
                'name': fpath.name,
                'size': fpath.stat().st_size,
                'type': file_type,
                'output_size': out_file.stat().st_size if out_file else 0,
            })
        else:
            entry = {
                'path': str(fpath),
                'name': fpath.name,
                'size': fpath.stat().st_size,
                'type': file_type,
            }
            # Get duration for audio/video
            if file_type in ('audio', 'video'):
                entry['duration'] = _get_duration(str(fpath))
            pending.append(entry)

    emit({'files': pending, 'done': done})


def _get_duration(path):
    """Get media duration in seconds."""
    try:
        import subprocess
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=30
        )
        return round(float(result.stdout.strip()), 1)
    except Exception:
        return 0


def cmd_run(job):
    """Run transcription with JSON progress output."""
    import warnings
    warnings.filterwarnings("ignore")
    from core.config_loader import PipelineConfig

    input_dir = Path(job['input'])
    output_dir = Path(job['output'])
    selected_files = job.get('files', [])

    # Build config
    config = PipelineConfig()
    config.source_directory = str(input_dir)
    config.output_directory = str(output_dir)
    config.whisper_model = job.get('whisperModel', 'medium')
    config.whisper_language = job.get('whisperLanguage', '')
    config.whisper_beam_size = job.get('whisperBeamSize', 1)
    config.whisper_diarize = job.get('diarize', False)
    config.whisper_diarize_speakers = job.get('diarizeSpeakers', 0)
    config.process_audio = job.get('processAudio', True)
    config.process_videos = job.get('processVideos', True)
    config.process_pdf = job.get('processPdf', True)
    config.process_images = job.get('processImages', True)
    config.process_docx = job.get('processDocx', True)
    config.process_xlsx = job.get('processXlsx', True)
    config.process_pptx = job.get('processPptx', True)
    config.process_txt = job.get('processTxt', True)
    config.process_csv = job.get('processCsv', False)
    config.process_rtf = job.get('processRtf', False)

    # If specific files selected, create a temp input dir with only those
    actual_input = input_dir
    temp_dir = None
    if selected_files:
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix='transcriptor_'))
        for fname in selected_files:
            src = input_dir / fname
            if src.exists():
                dst = temp_dir / fname
                # Create symlink or copy
                try:
                    os.link(str(src), str(dst))
                except Exception:
                    import shutil
                    shutil.copy2(str(src), str(dst))
        actual_input = temp_dir
        config.source_directory = str(actual_input)

    output_dir.mkdir(parents=True, exist_ok=True)

    from process_v2 import MaterialProcessor

    processor = MaterialProcessor(config)
    processor.source_dir = actual_input.resolve()
    materials = processor.find_materials(actual_input)

    total_files = sum(len(files) for files in materials.values())
    if total_files == 0:
        emit({'type': 'batch_done', 'processed': 0, 'failed': 0, 'elapsed_seconds': 0})
        return

    emit({'type': 'status', 'message': f'Found {total_files} files to process'})

    # Filter out already processed
    filtered = {k: [] for k in materials}
    for file_type, files_list in materials.items():
        for file_path in files_list:
            out_path = processor._get_output_path(file_path, output_dir)
            if not out_path.exists():
                filtered[file_type].append(file_path)

    remaining = sum(len(f) for f in filtered.values())
    if remaining == 0:
        emit({'type': 'batch_done', 'processed': 0, 'failed': 0, 'elapsed_seconds': 0})
        return

    # Monkey-patch the progress to emit JSON
    processed_count = [0]
    start_time = time.time()
    original_wrapper = processor._process_file_wrapper

    def json_wrapper(file_path, file_type, output_dir_arg):
        result = original_wrapper(file_path, file_type, output_dir_arg)
        processed_count[0] += 1
        elapsed = time.time() - start_time
        eta = 0
        if processed_count[0] > 0 and processed_count[0] < remaining:
            rate = processed_count[0] / elapsed
            eta = (remaining - processed_count[0]) / rate

        success = result[0] if result else False
        emit({
            'type': 'file_done',
            'file': file_path.name,
            'success': success,
            'done': processed_count[0],
            'total': remaining,
            'percent': round(processed_count[0] / remaining * 100, 1),
            'eta_seconds': round(eta),
            'elapsed_seconds': round(elapsed, 1),
        })
        return result

    processor._process_file_wrapper = json_wrapper

    # Emit loading status
    emit({'type': 'status', 'message': f'Loading models ({config.whisper_model})...'})

    try:
        processor.process_all(actual_input, output_dir)
    except Exception as e:
        emit({'type': 'error', 'message': str(e)})
    finally:
        elapsed = time.time() - start_time
        stats = processor.stats
        emit({
            'type': 'batch_done',
            'processed': (stats['audio_processed'] + stats['videos_processed'] +
                         stats['pdfs_processed'] + stats['images_processed'] +
                         stats['documents_processed']),
            'failed': stats['errors'],
            'elapsed_seconds': round(elapsed, 1),
            'stats': dict(stats),
        })

        # Cleanup temp dir
        if temp_dir and temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description='Transcriptor Bridge')
    parser.add_argument('--detect', action='store_true')
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--job', type=str)
    args = parser.parse_args()

    if args.detect:
        cmd_detect()
    elif args.scan:
        job = load_job(args.job)
        cmd_scan(job)
    elif args.run:
        job = load_job(args.job)
        cmd_run(job)


if __name__ == '__main__':
    main()
