"""
Transcriptor Bridge — JSON interface for the Electron app.

Wraps process_v2.py and outputs JSON progress lines.
Uses subprocess to isolate process_v2's ANSI output from our JSON.
"""

import os
import sys
import json
import argparse
import subprocess
import time
from pathlib import Path

# Backend dir comes from --backend arg or defaults to relative path (dev mode)
_default_backend = Path(__file__).resolve().parent.parent / 'backend'
BACKEND_DIR = Path(os.environ.get('TRANSCRIPTOR_BACKEND', str(_default_backend)))
VENV_PYTHON = str(BACKEND_DIR / '.venv' / 'Scripts' / 'python.exe')
PROCESS_V2 = str(BACKEND_DIR / 'process_v2.py')

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
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def load_job(job_path):
    with open(job_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def cmd_detect():
    """Output system info as JSON."""
    info = {
        'python': sys.version,
        'backend_dir': str(BACKEND_DIR),
        'backend_exists': BACKEND_DIR.exists(),
        'venv_exists': Path(VENV_PYTHON).exists(),
    }
    try:
        result = subprocess.run(
            [VENV_PYTHON, '-c', 'import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")'],
            capture_output=True, text=True, timeout=30
        )
        lines = result.stdout.strip().split('\n')
        info['cuda'] = lines[0] == 'True'
        info['gpu_name'] = lines[1] if len(lines) > 1 and lines[1] else None
    except Exception:
        info['cuda'] = False
        info['gpu_name'] = None

    try:
        result = subprocess.run(
            [VENV_PYTHON, '-c', 'import faster_whisper; print("ok")'],
            capture_output=True, text=True, timeout=15
        )
        info['whisper'] = 'ok' in result.stdout
    except Exception:
        info['whisper'] = False

    try:
        result = subprocess.run(
            [VENV_PYTHON, '-c', 'import pytesseract; pytesseract.get_tesseract_version(); print("ok")'],
            capture_output=True, text=True, timeout=10
        )
        info['tesseract'] = 'ok' in result.stdout
    except Exception:
        info['tesseract'] = False

    emit(info)


def _get_duration(path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=30
        )
        return round(float(result.stdout.strip()), 1)
    except Exception:
        return 0


def cmd_scan(job):
    """Scan for files and output JSON list."""
    input_dir = Path(job['input'])
    output_dir = Path(job['output'])

    if not input_dir.is_dir():
        emit({'files': [], 'done': [], 'error': 'Input folder not found'})
        return

    output_dir.mkdir(parents=True, exist_ok=True)

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

        file_type = 'unknown'
        for t, exts in SUPPORTED_EXTS.items():
            if ext in exts:
                file_type = t
                break

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
            if file_type in ('audio', 'video'):
                entry['duration'] = _get_duration(str(fpath))
            pending.append(entry)

    emit({'files': pending, 'done': done})


def cmd_run(job):
    """Run transcription by spawning process_v2.py as a subprocess."""
    input_dir = Path(job['input'])
    output_dir = Path(job['output'])
    selected_files = job.get('files', [])

    # If specific files selected, create temp dir with just those
    actual_input = input_dir
    temp_dir = None
    if selected_files:
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix='transcriptor_'))
        for fname in selected_files:
            src = input_dir / fname
            if src.exists():
                dst = temp_dir / fname
                try:
                    os.link(str(src), str(dst))
                except Exception:
                    import shutil
                    shutil.copy2(str(src), str(dst))
        actual_input = temp_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write a temp config for process_v2
    config = {
        'source_directory': str(actual_input),
        'output_directory': str(output_dir),
        'whisper_model': job.get('whisperModel', 'medium'),
        'whisper_language': job.get('whisperLanguage', ''),
        'whisper_beam_size': job.get('whisperBeamSize', 1),
        'whisper_diarize': job.get('diarize', False),
        'whisper_diarize_speakers': job.get('diarizeSpeakers', 0),
        'process_audio': job.get('processAudio', True),
        'process_videos': job.get('processVideos', True),
        'process_pdf': job.get('processPdf', True),
        'process_images': job.get('processImages', True),
        'process_docx': job.get('processDocx', True),
        'process_xlsx': job.get('processXlsx', True),
        'process_pptx': job.get('processPptx', True),
        'process_txt': job.get('processTxt', True),
        'process_csv': job.get('processCsv', False),
        'process_rtf': job.get('processRtf', False),
    }

    import tempfile
    config_file = Path(tempfile.mktemp(suffix='.json', prefix='transcriptor_config_'))
    config_file.write_text(json.dumps(config), encoding='utf-8')

    emit({'type': 'status', 'message': f'Loading Whisper model ({config["whisper_model"]})...'})

    # Count files to process
    total = 0
    for fpath in actual_input.rglob('*'):
        if fpath.is_file() and fpath.suffix.lower() in ALL_EXTS:
            # Check if already done
            out_check = output_dir / (fpath.stem + '.txt')
            if not out_check.exists():
                total += 1

    if total == 0:
        emit({'type': 'batch_done', 'processed': 0, 'failed': 0, 'elapsed_seconds': 0})
        _cleanup(temp_dir, config_file)
        return

    emit({'type': 'status', 'message': f'Processing {total} files...'})

    # Spawn process_v2.py as subprocess — its ANSI output goes to its own stderr/stdout
    # We don't pipe its stdout — we don't need it
    start_time = time.time()

    proc = subprocess.Popen(
        [VENV_PYTHON, PROCESS_V2, str(actual_input), '--output', str(output_dir), '--config', str(config_file)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(BACKEND_DIR),
        creationflags=0x00004000 if sys.platform == 'win32' else 0,  # BELOW_NORMAL_PRIORITY
    )

    # Send Enter to skip the preflight prompt
    try:
        proc.stdin.write(b'\n')
        proc.stdin.flush()
        proc.stdin.close()
    except Exception:
        pass

    # Monitor output directory for new .txt files
    known_files = {f.name.lower() for f in output_dir.iterdir() if f.suffix == '.txt'} if output_dir.is_dir() else set()
    processed = 0
    failed = 0

    while proc.poll() is None:
        time.sleep(2)

        # Check for new .txt files in output
        current_files = {f.name.lower() for f in output_dir.iterdir() if f.suffix == '.txt'} if output_dir.is_dir() else set()
        new_files = current_files - known_files

        for new_file in new_files:
            processed += 1
            known_files.add(new_file)
            elapsed = time.time() - start_time
            eta = 0
            if processed > 0 and processed < total:
                rate = processed / elapsed
                eta = (total - processed) / rate

            emit({
                'type': 'file_done',
                'file': new_file.replace('.txt', ''),
                'success': True,
                'done': processed,
                'total': total,
                'percent': round(processed / total * 100, 1),
                'eta_seconds': round(eta),
                'elapsed_seconds': round(elapsed, 1),
            })

    elapsed = time.time() - start_time

    # Final check for any files created during the last poll
    if output_dir.is_dir():
        final_files = {f.name.lower() for f in output_dir.iterdir() if f.suffix == '.txt'}
        for new_file in (final_files - known_files):
            processed += 1

    emit({
        'type': 'batch_done',
        'processed': processed,
        'failed': max(0, total - processed),
        'elapsed_seconds': round(elapsed, 1),
    })

    _cleanup(temp_dir, config_file)


def _cleanup(temp_dir, config_file):
    if temp_dir and temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    if config_file and config_file.exists():
        try:
            config_file.unlink()
        except Exception:
            pass


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
