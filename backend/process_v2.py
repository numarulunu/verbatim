"""
Material Processing Pipeline - Text Extraction Only

Processes materials from the Material folder and extracts text:
- Audio: Direct Whisper transcription (MP3, WAV, FLAC, OGG, M4A, AAC, WMA)
- Videos: Extract audio via ffmpeg -> Whisper transcription
- PDFs: OCR text extraction
- Images: OCR text extraction
- Documents: Text extraction (DOCX, XLSX, PPTX, CSV, TXT, RTF)

All outputs are saved as text files in the Transcriptions directory.
"""

import sys
import os
import warnings
from pathlib import Path
import argparse

# Suppress torchcodec warning before any pyannote import
warnings.filterwarnings("ignore", message=".*torchcodec.*")
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
import time
import subprocess
import threading
import re
import psutil

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

import logging

from core.config_loader import load_config, PipelineConfig
from core.document_processor import DocumentProcessor, DocumentProcessingError
from core.enhanced_ocr import EnhancedOCR
from core.whisper_pool import WhisperModelPool
from core.quiet import quiet_print
from core.processing_calculator import ProcessingCalculator
from core.diarizer import Diarizer, assign_speakers, assign_speakers_to_words, format_diarized_transcript, format_timestamped_transcript, is_available as diarizer_available
from core.progress_bar import (
    ProgressBar, Spinner,
    print_preflight, print_model_info, print_model_info_full, print_no_files, print_error,
    dim, bold, cyan, green, bold_cyan,
)

logger = logging.getLogger('transcriptor.process')


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to be safe for Windows/Linux/Mac"""
    # Remove invalid characters for Windows: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Check for reserved Windows names
    reserved_names = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                     'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                     'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
    if sanitized.upper() in reserved_names:
        sanitized = f"_{sanitized}"

    # Limit length (leave room for extension and counter)
    if len(sanitized) > 240:
        sanitized = sanitized[:240]

    if not sanitized:
        sanitized = "unnamed"

    return sanitized


# Supported format sets
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus'}
VIDEO_EXTS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.ts'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
DOC_EXTS = {'.docx', '.xlsx', '.pptx', '.csv', '.txt', '.rtf'}


class MaterialProcessor:
    """Process materials and extract text from audio, video, PDFs, images, and documents"""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.doc_processor = DocumentProcessor()
        self.ocr = EnhancedOCR()
        self.whisper_pool = None  # Lazy init only when needed
        self.diarizer = None  # Lazy init only when diarize=True

        # Statistics (thread-safe)
        self.stats_lock = threading.Lock()
        self.stats = {
            'audio_processed': 0,
            'videos_processed': 0,
            'pdfs_processed': 0,
            'images_processed': 0,
            'documents_processed': 0,
            'errors': 0
        }

        # Progress tracking
        self.progress_bar = None

        # Source directory for relative path calculation
        self.source_dir = None

        # Track processed files to prevent duplicates (thread-safe)
        self.processed_files = set()
        self.processed_files_lock = threading.Lock()

        # Error log (thread-safe) - surfaces at end of processing
        self._errors = []
        self._errors_lock = threading.Lock()

        # Retry queue for failed files (thread-safe)
        self._retry_queue = []
        self._retry_lock = threading.Lock()

        # Background diarization pipeline
        self._diarize_queue = None  # Queue() — set up in process_all
        self._diarize_total = 0
        self._diarize_done = 0
        self._diarize_done_lock = threading.Lock()
        self._diarize_lock = threading.Lock()

        # Progress bar thread safety
        self._progress_lock = threading.Lock()

        # Base directory for audio cache (resolved to project root)
        self._project_root = Path(__file__).parent.parent.resolve()

    def _log_error(self, file_path: Path, message: str):
        """Record an error for display at the end of processing"""
        logger.error("Processing error [%s]: %s", file_path.name, message)
        with self._errors_lock:
            self._errors.append((file_path.name, message))

    def find_materials(self, source_dir: Path) -> Dict[str, List[Path]]:
        """Find all materials in source directory, grouped by type"""
        materials = {
            'audio': [],
            'videos': [],
            'pdfs': [],
            'images': [],
            'documents': []
        }

        if not source_dir.exists():
            logger.error("Source directory not found: %s", source_dir)
            return materials

        for file_path in source_dir.rglob('*'):
            if not file_path.is_file():
                continue

            ext = file_path.suffix.lower()

            if self.config.process_audio and ext in AUDIO_EXTS:
                materials['audio'].append(file_path)
            elif self.config.process_videos and ext in VIDEO_EXTS:
                materials['videos'].append(file_path)
            elif self.config.process_pdf and ext == '.pdf':
                materials['pdfs'].append(file_path)
            elif self.config.process_images and ext in IMAGE_EXTS:
                materials['images'].append(file_path)
            elif ext in DOC_EXTS:
                if ext == '.docx' and self.config.process_docx:
                    materials['documents'].append(file_path)
                elif ext == '.xlsx' and self.config.process_xlsx:
                    materials['documents'].append(file_path)
                elif ext == '.pptx' and self.config.process_pptx:
                    materials['documents'].append(file_path)
                elif ext == '.csv' and self.config.process_csv:
                    materials['documents'].append(file_path)
                elif ext == '.txt' and self.config.process_txt:
                    materials['documents'].append(file_path)
                elif ext == '.rtf' and self.config.process_rtf:
                    materials['documents'].append(file_path)

        # Deduplicate (handles symlinks, junctions)
        for file_type in materials:
            unique_paths = {p.resolve() for p in materials[file_type]}
            materials[file_type] = list(unique_paths)

        return materials

    def _apply_diarization(self, result: dict, media_path: Path) -> str:
        """Apply speaker diarization to whisper result if enabled, else return plain text."""
        if not self.diarizer:
            return result['text'].strip()

        num_speakers = getattr(self.config, 'whisper_diarize_speakers', 0)
        speaker_segments = self.diarizer.diarize(str(media_path), num_speakers=num_speakers)
        if not speaker_segments:
            return result['text'].strip()

        # Prefer word-level timestamps (much sharper speaker transitions)
        words = result.get('words', [])
        if words:
            tagged_words = assign_speakers_to_words(words, speaker_segments, min_speaker_seconds=0.0)
            return format_diarized_transcript(words=tagged_words)

        # Fallback to segment-level
        segments = result.get('segments', [])
        if segments:
            tagged_segments = assign_speakers(segments, speaker_segments)
            return format_diarized_transcript(segments=tagged_segments)

        return result['text'].strip()

    def process_audio(self, audio_path: Path, output_dir: Path) -> Optional[dict]:
        """Transcribe audio file directly with Whisper (no extraction needed).
        Returns raw whisper result dict (diarization runs in a separate phase).
        """
        if not self.whisper_pool:
            self._log_error(audio_path, "Whisper pool not initialized")
            return None

        try:
            result = self._transcribe_with_retry(audio_path)
            if result and result.get('text', '').strip():
                with self.stats_lock:
                    self.stats['audio_processed'] += 1
                return result
            return None

        except Exception as e:
            self._log_error(audio_path, f"{type(e).__name__}: {e}")
            with self.stats_lock:
                self.stats['errors'] += 1
            return None

    def _transcribe_with_retry(self, media_path: Path, max_retries: int = 2) -> Optional[dict]:
        """Transcribe a file with automatic retry on transient errors (OOM, CUDA)."""
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                return self.whisper_pool.transcribe(str(media_path))
            except Exception as e:
                last_error = e
                err_name = type(e).__name__
                is_oom = 'OutOfMemory' in err_name or 'out of memory' in str(e).lower()
                is_cuda = 'cuda' in str(e).lower() or 'CUDA' in str(e)

                if (is_oom or is_cuda) and attempt < max_retries:
                    logger.warning("Transient error on attempt %d for %s: %s — retrying", attempt, media_path.name, e)
                    # Clear GPU cache and wait before retry
                    try:
                        import torch
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    time.sleep(2)
                    continue
                else:
                    raise last_error
        raise last_error  # Should never reach here

    def process_video(self, video_path: Path, output_dir: Path) -> Optional[dict]:
        """Process video: transcribe with Whisper (direct MP4 read or ffmpeg extraction).
        Returns raw whisper result dict (diarization runs in a separate phase).
        """
        if not self.whisper_pool:
            self._log_error(video_path, "Whisper pool not initialized")
            return None

        try:
            if self.whisper_pool.get_backend() == "faster-whisper":
                result = self._transcribe_with_retry(video_path)
            else:
                audio_path = self._extract_audio(video_path)
                if not audio_path:
                    self._log_error(video_path, "Audio extraction failed (ffmpeg)")
                    with self.stats_lock:
                        self.stats['errors'] += 1
                    return None
                try:
                    result = self.whisper_pool.transcribe(str(audio_path))
                finally:
                    audio_path.unlink(missing_ok=True)

            if result and result.get('text', '').strip():
                with self.stats_lock:
                    self.stats['videos_processed'] += 1
                return result
            return None

        except Exception as e:
            self._log_error(video_path, f"{type(e).__name__}: {e}")
            with self.stats_lock:
                self.stats['errors'] += 1
            return None

    def _extract_audio(self, video_path: Path) -> Optional[Path]:
        """Extract audio from video using ffmpeg"""
        try:
            cache_dir = self._project_root / 'audio_cache'
            cache_dir.mkdir(exist_ok=True)
            audio_path = cache_dir / f"{video_path.stem}.wav"

            cmd = [
                'ffmpeg', '-loglevel', 'error',
                '-i', str(video_path),
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                '-y', str(audio_path)
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            return audio_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        except Exception:
            return None

    def process_pdf(self, pdf_path: Path, output_dir: Path) -> Optional[str]:
        """Process PDF: OCR text extraction"""
        try:
            text = self.ocr.extract_text(str(pdf_path))
            if text and text.strip():
                with self.stats_lock:
                    self.stats['pdfs_processed'] += 1
                return text
            return None
        except Exception as e:
            self._log_error(pdf_path, str(e))
            with self.stats_lock:
                self.stats['errors'] += 1
            return None

    def process_image(self, image_path: Path, output_dir: Path) -> Optional[str]:
        """Process image: OCR text extraction"""
        try:
            text = self.ocr.extract_text(str(image_path))
            if text and text.strip():
                with self.stats_lock:
                    self.stats['images_processed'] += 1
                return text
            return None
        except Exception as e:
            self._log_error(image_path, str(e))
            with self.stats_lock:
                self.stats['errors'] += 1
            return None

    def process_document(self, doc_path: Path, output_dir: Path) -> Optional[str]:
        """Process document: text extraction"""
        try:
            text = self.doc_processor.extract_text(str(doc_path))
            if text and text.strip():
                with self.stats_lock:
                    self.stats['documents_processed'] += 1
                return text
            return None
        except Exception as e:
            self._log_error(doc_path, str(e))
            with self.stats_lock:
                self.stats['errors'] += 1
            return None

    def _get_output_path(self, source_path: Path, output_dir: Path) -> Path:
        """Get the output path for a source file, preserving folder structure"""
        if self.source_dir:
            try:
                resolved_source = source_path.resolve()
                relative_path = resolved_source.relative_to(self.source_dir)
                relative_dir = relative_path.parent
            except ValueError:
                relative_dir = Path('.')
        else:
            relative_dir = Path('.')

        safe_name = sanitize_filename(source_path.stem)
        output_subdir = output_dir / relative_dir
        return output_subdir / f"{safe_name}.txt"

    def save_text(self, source_path: Path, text: str, output_dir: Path):
        """Save extracted text to file with sanitized filename, preserving folder structure"""
        try:
            output_path = self._get_output_path(source_path, output_dir)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Ensure unique filename if file exists
            counter = 1
            base_path = output_path
            while output_path.exists():
                safe_name = sanitize_filename(source_path.stem)
                output_path = base_path.parent / f"{safe_name}_{counter}.txt"
                counter += 1

            output_path.write_text(text, encoding='utf-8')
            logger.info("Saved: %s", output_path.name)
        except Exception as e:
            logger.error("Error saving %s: %s", source_path.name, e)
            quiet_print(f"Error saving {source_path.name}: {e}", error=True)

    def _dispatch_file(self, file_path: Path, file_type: str, output_dir: Path):
        """Dispatch a single file to the appropriate processor.
        Returns (whisper_result_dict, None) for audio/video,
                (None, extracted_text) for other types,
                (None, None) on failure.
        """
        if file_type == 'audio':
            return (self.process_audio(file_path, output_dir), None)
        elif file_type == 'video':
            return (self.process_video(file_path, output_dir), None)
        elif file_type == 'pdf':
            return (None, self.process_pdf(file_path, output_dir))
        elif file_type == 'image':
            return (None, self.process_image(file_path, output_dir))
        elif file_type == 'document':
            return (None, self.process_document(file_path, output_dir))
        return (None, None)

    def _process_file_wrapper(self, file_path: Path, file_type: str, output_dir: Path):
        """Wrapper for processing a single file (for parallel execution).
        Audio/video: whisper only (saves plain text), queues diarization for phase 2.
        Other types: process and save directly.
        """
        # Check if already processed (prevent duplicates)
        file_key = file_path.resolve()
        with self.processed_files_lock:
            if file_key in self.processed_files:
                return (True, file_path)
            self.processed_files.add(file_key)

        try:
            result, text = self._dispatch_file(file_path, file_type, output_dir)

            # CPU types (pdf, image, document): save text directly
            if text:
                self.save_text(file_path, text, output_dir)
                with self._progress_lock:
                    if self.progress_bar:
                        self.progress_bar.update(1)
                return (True, file_path)

            # Audio/video: save plain text now, queue diarization in background
            if result and isinstance(result, dict):
                plain_text = format_timestamped_transcript(result.get('segments', []))
                if not plain_text:
                    plain_text = result['text'].strip()
                self.save_text(file_path, plain_text, output_dir)

                # Queue for background diarization + save word timestamps for resume
                if self._diarize_queue is not None and file_type in ('audio', 'video'):
                    output_path = self._get_output_path(file_path, output_dir)
                    # Save .whisper.json sidecar (resume marker + diarization data)
                    import json
                    sidecar = output_path.with_name(output_path.stem + '.whisper.json')
                    sidecar.write_text(json.dumps({
                        'words': result.get('words', []),
                        'segments': result.get('segments', []),
                        'text': result.get('text', ''),
                        'source': str(file_path),
                    }), encoding='utf-8')
                    self._diarize_queue.put((file_path, result, output_path))
                    with self._diarize_lock:
                        self._diarize_total += 1

                with self._progress_lock:
                    if self.progress_bar:
                        self.progress_bar.update(1)
                return (True, file_path)
            else:
                # Processing returned None — record for retry
                with self._retry_lock:
                    self._retry_queue.append((file_path, file_type))
                with self._progress_lock:
                    if self.progress_bar:
                        self.progress_bar.update(1)
                return (False, file_path)
        except Exception as e:
            logger.error("Worker exception: %s", e, exc_info=True)
            with self.stats_lock:
                self.stats['errors'] += 1
            with self._retry_lock:
                self._retry_queue.append((file_path, file_type))
            with self._progress_lock:
                if self.progress_bar:
                    self.progress_bar.update(1)
            return (False, file_path)

    def _diarize_worker(self, diarize_stop: threading.Event):
        """Background worker that pulls items from the diarize queue and applies diarization."""
        while not diarize_stop.is_set() or not self._diarize_queue.empty():
            try:
                media_path, whisper_result, output_path = self._diarize_queue.get(timeout=2)
            except Empty:
                continue
            try:
                diarized = self._apply_diarization(whisper_result, media_path)
                if diarized and '[Speaker' in diarized:
                    # Diarization succeeded — overwrite and remove sidecar
                    output_path.write_text(diarized, encoding='utf-8')
                    sidecar = output_path.with_name(output_path.stem + '.whisper.json')
                    sidecar.unlink(missing_ok=True)
                # If no speaker tags, keep the sidecar for retry/resume
            except Exception as e:
                self._log_error(media_path, f"Diarize: {type(e).__name__}: {e}")
            with self._diarize_done_lock:
                self._diarize_done += 1

    def _prepare_materials(self, source_dir: Path, output_dir: Path) -> dict:
        """Phase 1: Setup, filtering, material discovery.
        Returns filtered materials dict. Returns empty dict if nothing to process.
        """
        # Clear processed files tracking from previous runs
        with self.processed_files_lock:
            self.processed_files.clear()

        self.source_dir = source_dir.resolve()
        materials = self.find_materials(source_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Filter out already-processed files
        filtered = {k: [] for k in materials}
        for file_type, files in materials.items():
            for file_path in files:
                output_path = self._get_output_path(file_path, output_dir)
                if not output_path.exists():
                    filtered[file_type].append(file_path)

        return filtered

    def _run_primary_processing(self, materials: dict, output_dir: Path):
        """Phase 2: Whisper init, thread pool dispatch, progress tracking, retries.
        Stores diarize_threads and diarize_stop on self for phase 3.
        """
        total_files = sum(len(files) for files in materials.values())

        # Determine if we need Whisper (audio or video files present)
        needs_whisper = bool(materials['audio'] or materials['videos'])
        video_workers = self.config.max_parallel_workers

        logger.info("Starting processing: %d files", total_files)

        if needs_whisper:
            logger.info("Loading Whisper models (%s)", self.config.whisper_model)
            spinner = Spinner(f"Loading Whisper models ({self.config.whisper_model})...")
            spinner.start()
            self.whisper_pool = WhisperModelPool()
            self.whisper_pool.initialize(
                self.config.whisper_model,
                force_cpu=(self.config.whisper_device == 'cpu'),
                language=self.config.whisper_language or None,
                beam_size=self.config.whisper_beam_size,
            )
            video_workers = self.whisper_pool.get_num_workers()
            info = self.whisper_pool.get_info()
            spinner.stop()
            logger.info("Whisper loaded: %s, %d GPU + %d CPU workers",
                        info.get('backend', '?'), info.get('gpu_workers', 0), info.get('cpu_workers', 0))
            print_model_info_full(info)

            # Initialize diarization if enabled
            if self.config.whisper_diarize and diarizer_available():
                diarize_spinner = Spinner("Loading speaker diarization model...")
                diarize_spinner.start()
                self.diarizer = Diarizer()
                if not self.diarizer.initialize():
                    self.diarizer = None
                diarize_spinner.stop()
                if self.diarizer:
                    from core.progress_bar import green, dim
                    logger.info("Speaker diarization enabled")
                    print(f"  {green('✓')} {dim('Speaker diarization enabled')}")
                    print()

        cpu_workers = min(8, psutil.cpu_count(logical=False) or 4)
        total_workers = max(video_workers, cpu_workers)

        # Wire live resource display from whisper pool's governor
        resource_fn = self.whisper_pool.get_resource_status if self.whisper_pool else None

        # Wire live diarization counter
        def _diarize_status():
            with self._diarize_done_lock:
                return (self._diarize_done, self._diarize_total)
        diarize_fn = _diarize_status if self.diarizer else None

        self.progress_bar = ProgressBar(total_files, desc="Processing", workers=total_workers,
                                        resource_fn=resource_fn, diarize_fn=diarize_fn)

        # ── Background diarization pipeline ──────────────────────────────
        # Diarize workers run concurrently with whisper: CPU during whisper,
        # auto-switch to GPU when whisper finishes and frees VRAM.
        self._diarize_threads = []
        self._diarize_stop = threading.Event()

        if self.diarizer:
            self._diarize_queue = Queue()

            # Resume: pick up any .whisper.json sidecars left from a previous run
            import json
            for sidecar in output_dir.rglob('*.whisper.json'):
                try:
                    data = json.loads(sidecar.read_text(encoding='utf-8'))
                    txt_path = sidecar.with_name(sidecar.name.replace('.whisper.json', '.txt'))
                    media = Path(data.get('source', ''))
                    if txt_path.exists() and media.exists():
                        self._diarize_queue.put((media, data, txt_path))
                        with self._diarize_lock:
                            self._diarize_total += 1
                except Exception as e:
                    logger.error("Failed to load diarize sidecar %s: %s", sidecar, e, exc_info=True)
            if self._diarize_total > 0:
                from core.progress_bar import dim, yellow
                logger.info("Resuming diarization for %d files", self._diarize_total)
                print(f"  {yellow('↻')} {dim(f'Resuming diarization for {self._diarize_total} files')}")

            # 1 worker during whisper (CPU, minimal contention)
            t = threading.Thread(target=self._diarize_worker, args=(self._diarize_stop,), daemon=True)
            t.start()
            self._diarize_threads.append(t)

        # Build a flat task list: (file_path, file_type)
        whisper_tasks = []
        cpu_tasks = []

        type_map = {
            'audio': 'audio', 'videos': 'video',
            'pdfs': 'pdf', 'images': 'image', 'documents': 'document'
        }

        for mat_key, file_type in type_map.items():
            for fp in materials[mat_key]:
                if mat_key in ('audio', 'videos'):
                    whisper_tasks.append((fp, file_type))
                else:
                    cpu_tasks.append((fp, file_type))

        # Process whisper tasks and CPU tasks concurrently
        futures = []

        whisper_executor = None
        cpu_executor = None

        if whisper_tasks:
            whisper_executor = ThreadPoolExecutor(max_workers=video_workers)
            for fp, ft in whisper_tasks:
                futures.append(whisper_executor.submit(self._process_file_wrapper, fp, ft, output_dir))

        if cpu_tasks:
            cpu_executor = ThreadPoolExecutor(max_workers=cpu_workers)
            for fp, ft in cpu_tasks:
                futures.append(cpu_executor.submit(self._process_file_wrapper, fp, ft, output_dir))

        # Wait for all futures
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error("Worker exception: %s", e, exc_info=True)
                with self.stats_lock:
                    self.stats['errors'] += 1

        # Shutdown executors
        if whisper_executor:
            whisper_executor.shutdown(wait=False)
        if cpu_executor:
            cpu_executor.shutdown(wait=False)

        if self.progress_bar:
            self.progress_bar.finish()

        # Retry failed files (sequentially, one at a time, with GPU cache cleared)
        with self._retry_lock:
            retry_list = list(self._retry_queue)
            self._retry_queue.clear()

        if retry_list:
            from core.progress_bar import yellow, dim
            logger.warning("Retrying %d failed files", len(retry_list))
            print(f"  {yellow('↻')} {dim(f'Retrying {len(retry_list)} failed files...')}")

            # Clear GPU cache before retries
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass

            # Allow re-processing by removing from processed set
            with self.processed_files_lock:
                for fp, ft in retry_list:
                    self.processed_files.discard(fp.resolve())

            # Clear previous errors for these files
            with self._errors_lock:
                retry_names = {fp.name for fp, _ in retry_list}
                self._errors = [(n, m) for n, m in self._errors if n not in retry_names]
                # Reset error count for retried files
                self.stats['errors'] = max(0, self.stats['errors'] - len(retry_list))

            # Process one at a time to avoid OOM
            for fp, ft in retry_list:
                time.sleep(1)  # Brief pause between retries
                try:
                    result, text = self._dispatch_file(fp, ft, output_dir)
                    if text:
                        self.save_text(fp, text, output_dir)
                    elif result and isinstance(result, dict):
                        txt = format_timestamped_transcript(result.get('segments', [])) or result['text'].strip()
                        self.save_text(fp, txt, output_dir)
                        # Queue for background diarization
                        if self._diarize_queue is not None:
                            output_path = self._get_output_path(fp, output_dir)
                            self._diarize_queue.put((fp, result, output_path))
                            with self._diarize_lock:
                                self._diarize_total += 1
                except Exception as e:
                    logger.warning("Retry failed for %s: %s: %s", fp.name, type(e).__name__, e)
                    self._log_error(fp, f"Retry failed: {type(e).__name__}: {e}")
                    with self.stats_lock:
                        self.stats['errors'] += 1

    def _run_diarization_drain(self):
        """Phase 3: Drain remaining diarization queue, cleanup.
        Must be called after _run_primary_processing.
        """
        if self.diarizer and self._diarize_queue is not None:
            remaining = self._diarize_queue.qsize()
            if remaining > 0:
                from core.progress_bar import dim

                # Free whisper models -> reclaim GPU VRAM
                if self.whisper_pool:
                    self.whisper_pool.clear()

                # Move diarizer to GPU (5-10x faster than CPU)
                try:
                    import torch
                    torch.cuda.empty_cache()
                    self.diarizer._pipeline.to(torch.device("cuda"))
                except Exception as e:
                    logger.error("Failed to move diarizer to GPU: %s", e, exc_info=True)

                logger.info("Diarizing remaining %d files on GPU", remaining)
                print(f"  {dim('⠿')} {dim(f'Diarizing remaining {remaining} files on GPU...')}")

                # Spin up 1 more GPU worker to help drain (2 total)
                t = threading.Thread(target=self._diarize_worker, args=(self._diarize_stop,), daemon=True)
                t.start()
                self._diarize_threads.append(t)

            # Signal workers to stop after queue is empty, then wait
            self._diarize_stop.set()
            for t in self._diarize_threads:
                t.join(timeout=3600)  # 1h max wait

            with self._diarize_done_lock:
                done = self._diarize_done
            with self._diarize_lock:
                total = self._diarize_total
            if total > 0:
                from core.progress_bar import dim, green
                logger.info("Diarization complete: %d/%d files", done, total)
                print(f"  {green('✓')} {dim(f'{done}/{total} files diarized')}")

    def process_all(self, source_dir: Path, output_dir: Path):
        """Process all materials with parallel processing.
        Orchestrates three phases: prepare, primary processing, diarization drain.
        """
        materials = self._prepare_materials(source_dir, output_dir)
        if not materials:
            return

        total_files = sum(len(files) for files in materials.values())
        if total_files == 0:
            return

        self._run_primary_processing(materials, output_dir)
        self._run_diarization_drain()

        # Print completion summary
        self._print_summary()

    def _print_summary(self):
        """Print a summary of what was processed and any errors."""
        from core.progress_bar import dim, bold, green, red, yellow, cyan

        s = self.stats
        total_ok = (s['audio_processed'] + s['videos_processed'] +
                    s['pdfs_processed'] + s['images_processed'] + s['documents_processed'])
        errors = s['errors']

        parts = []
        if s['audio_processed']:
            parts.append(f"{s['audio_processed']} audio")
        if s['videos_processed']:
            parts.append(f"{s['videos_processed']} video")
        if s['pdfs_processed']:
            parts.append(f"{s['pdfs_processed']} PDF")
        if s['images_processed']:
            parts.append(f"{s['images_processed']} image")
        if s['documents_processed']:
            parts.append(f"{s['documents_processed']} doc")

        if total_ok > 0:
            detail = dim(", ").join(dim(p) for p in parts)
            logger.info("Transcribed %d files (%s)", total_ok, ", ".join(parts))
            print(f"  {green('✓')} {bold(str(total_ok))} {dim('transcribed')}  ({detail})")
        else:
            logger.warning("No files were transcribed")
            print(f"  {yellow('⚠')} {dim('No files were transcribed.')}")

        if errors > 0:
            logger.error("%d files failed", errors)
            print(f"  {red('✗')} {bold(str(errors))} {dim('failed')}")
            # Show up to 5 error details
            with self._errors_lock:
                for name, msg in self._errors[:5]:
                    logger.error("  %s: %s", name, msg)
                    print(f"    {dim('·')} {dim(name)}: {dim(msg)}")
                if len(self._errors) > 5:
                    print(f"    {dim(f'... and {len(self._errors) - 5} more')}")

        print()


def run_preflight(source_dir: Path, config: PipelineConfig) -> bool:
    """Run preflight check to estimate processing time"""
    processor = MaterialProcessor(config)
    processor.source_dir = source_dir.resolve()
    materials = processor.find_materials(source_dir)

    total_files = sum(len(files) for files in materials.values())
    if total_files == 0:
        print_no_files("No files found to process.")
        return False

    # Filter out already-processed files
    output_dir = Path(config.output_directory)
    filtered = {k: [] for k in materials}
    for file_type, files in materials.items():
        for file_path in files:
            output_path = processor._get_output_path(file_path, output_dir)
            if not output_path.exists():
                filtered[file_type].append(file_path)

    remaining_files = sum(len(files) for files in filtered.values())
    skipped = total_files - remaining_files

    if remaining_files == 0:
        print_no_files(f"All {total_files} files already transcribed.")
        return False

    calculator = ProcessingCalculator(config.whisper_model, diarize=config.whisper_diarize)
    estimates = calculator.calculate_all(filtered)

    if skipped > 0:
        logger.info("%d files already transcribed, skipping", skipped)
        print()
        print(f"  {dim(f'{skipped} files already transcribed, skipping.')}")

    print_preflight(estimates)
    return True


def run_diarize_pass(output_dir: Path, source_dir: Path, config: PipelineConfig):
    """Run a standalone diarization pass on pending .whisper.json sidecars.
    Used when all transcription is complete but diarization was interrupted.
    """
    from core.progress_bar import bold_cyan, dim, yellow, green
    from core.diarizer import (
        Diarizer, is_available as diarizer_available,
        assign_speakers, assign_speakers_to_words, format_diarized_transcript,
    )
    import json

    pending = list(output_dir.rglob('*.whisper.json'))
    if not pending:
        return

    print()
    print(f"  {bold_cyan('Transcriptor')}")
    print(f"  {dim('─' * 50)}")
    print()
    print(f"  {yellow('↻')} {dim(f'{len(pending)} files need diarization')}")
    print()
    print(f"  {dim('Press Enter to start...')}")
    input()

    if not diarizer_available():
        return

    diarize_spinner = Spinner("Loading speaker diarization model...")
    diarize_spinner.start()
    diarizer = Diarizer()
    # Load directly to GPU (no whisper competing)
    if not diarizer.initialize(device="cuda"):
        diarizer.initialize(device="cpu")
    diarize_spinner.stop()
    print(f"  {green('✓')} {dim('Speaker diarization loaded (GPU)')}")
    print()

    diarize_bar = ProgressBar(len(pending), desc="Diarizing")
    num_speakers = config.whisper_diarize_speakers if hasattr(config, 'whisper_diarize_speakers') else 0
    errors = 0

    for sidecar in sorted(pending):
        try:
            data = json.loads(sidecar.read_text(encoding='utf-8'))
            txt_path = sidecar.with_name(sidecar.name.replace('.whisper.json', '.txt'))
            media = Path(data.get('source', ''))

            # Find source media: try stored path, then match by txt filename
            if not media.exists():
                for sub in [source_dir] + [d for d in source_dir.rglob('*') if d.is_dir()]:
                    for ext in ('.mp4', '.mp3', '.wav', '.m4a', '.flac', '.ogg'):
                        candidate = sub / (txt_path.stem + ext)
                        if candidate.exists():
                            media = candidate
                            break
                    if media.exists():
                        break

            if txt_path.exists() and media.exists():
                speaker_segments = diarizer.diarize(str(media), num_speakers=num_speakers)
                if speaker_segments:
                    words = data.get('words', [])
                    segments = data.get('segments', [])
                    text = None
                    if words:
                        tagged = assign_speakers_to_words(words, speaker_segments, min_speaker_seconds=0.0)
                        text = format_diarized_transcript(words=tagged)
                    elif segments:
                        tagged = assign_speakers(segments, speaker_segments)
                        text = format_diarized_transcript(segments=tagged)
                    if text and '[Speaker' in text:
                        txt_path.write_text(text, encoding='utf-8')
                        sidecar.unlink(missing_ok=True)
        except Exception as e:
            logger.error("Diarize pass failed for %s: %s", sidecar.name, e, exc_info=True)
            errors += 1
        diarize_bar.update(1)

    diarize_bar.finish()
    done = len(pending) - errors
    print(f"  {green('✓')} {dim(f'{done} files diarized')}")
    if errors:
        from core.progress_bar import red
        print(f"  {red('✗')} {dim(f'{errors} failed')}")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Material Processing Pipeline')
    parser.add_argument('source_dir', nargs='?', default='Material',
                       help='Source directory containing materials')
    parser.add_argument('--output', '-o', default=None,
                       help='Output directory (default: from config)')
    parser.add_argument('--config', '-c', default='.pipeline_settings.json',
                       help='Configuration file')

    args = parser.parse_args()

    # Enable quiet mode
    os.environ['PIPELINE_QUIET'] = '1'

    config = load_config(args.config)
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output) if args.output else Path(config.output_directory)

    try:
        has_files = run_preflight(source_dir, config)

        # Check for pending diarization (leftover .whisper.json from interrupted run)
        pending_diarize = list(output_dir.rglob('*.whisper.json')) if config.whisper_diarize else []

        if not has_files and not pending_diarize:
            sys.exit(0)

        if not has_files and pending_diarize:
            run_diarize_pass(output_dir, source_dir, config)
            sys.exit(0)

        if has_files:
            input()  # Wait for Enter

        processor = MaterialProcessor(config)
        processor.process_all(source_dir, output_dir)

        print()

    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        print(f"\n\n  {dim('Interrupted.')}")
        sys.exit(1)
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        print()
        print_error(str(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
