"""
Processing Time Calculator - Estimate processing time before running

Accounts for batched inference, mixed GPU/CPU models, and parallel workers.
Shows a time range (optimistic - conservative) for realistic expectations.
"""

from pathlib import Path
from typing import Dict, List
import subprocess
import sys


class ProcessingCalculator:
    """Calculate estimated processing time for materials"""

    # Ratios: processing_minutes = audio_minutes * ratio (per single worker)
    # Calibrated for faster-whisper, beam_size=1, VAD on, condition_on_previous_text=False.
    # BATCHED ratios: with BatchedInferencePipeline (batch_size ~12-16 GPU, ~4 CPU)
    # NON-BATCHED ratios: single-segment-at-a-time (fallback)

    # GPU: GTX 1080 Ti class (Pascal, int8_float32). Turing/Ampere ~30-50% faster.
    WHISPER_RATIOS_GPU_BATCHED = {
        'tiny':     0.008,  # ~0.5s per min
        'base':     0.015,  # ~0.9s per min
        'small':    0.03,   # ~1.8s per min
        'medium':   0.07,   # ~4s per min  (measured: ~0.073 non-batched, batched ~2-3x faster)
        'large':    0.14,
        'large-v2': 0.14,
        'large-v3': 0.14,
    }
    WHISPER_RATIOS_GPU_SINGLE = {
        'tiny':     0.02,
        'base':     0.04,
        'small':    0.08,
        'medium':   0.18,
        'large':    0.35,
        'large-v2': 0.35,
        'large-v3': 0.35,
    }
    # CPU: int8 quantization. Model may be 'small' even when GPU uses 'medium'.
    WHISPER_RATIOS_CPU_BATCHED = {
        'tiny':     0.04,
        'base':     0.08,
        'small':    0.18,   # CPU sweet spot with batched
        'medium':   0.40,
        'large':    0.80,
        'large-v2': 0.80,
        'large-v3': 0.80,
    }
    WHISPER_RATIOS_CPU_SINGLE = {
        'tiny':     0.08,
        'base':     0.15,
        'small':    0.35,
        'medium':   0.70,
        'large':    1.40,
        'large-v2': 1.40,
        'large-v3': 1.40,
    }

    # Diarization ratios: processing_minutes = audio_minutes * ratio (per worker)
    # CPU: 1 worker during whisper (background, slow)
    # GPU: 2 workers after whisper finishes (fast, VRAM reclaimed)
    DIARIZE_RATIO_CPU = 0.15      # 1 min audio → 0.15 min on CPU per worker
    DIARIZE_RATIO_GPU = 0.03      # 1 min audio → 0.03 min on GPU per worker
    DIARIZE_CPU_WORKERS = 1       # During whisper (minimal CPU contention)
    DIARIZE_GPU_WORKERS = 2       # After whisper (GPU free)

    PDF_MB_PER_MINUTE = 2.0
    IMAGE_SECONDS_EACH = 3.0
    DOCUMENT_MB_PER_MINUTE = 5.0

    def __init__(self, whisper_model: str = 'base', diarize: bool = False):
        self.whisper_model = whisper_model
        self._diarize = diarize

        self._has_gpu = False
        try:
            import torch
            self._has_gpu = torch.cuda.is_available()
        except ImportError:
            pass

        # Detect batched inference availability
        self._batched = False
        try:
            from faster_whisper import BatchedInferencePipeline
            self._batched = True
        except ImportError:
            pass

        # Estimate config without touching the singleton
        self._gpu_workers = 0
        self._cpu_workers = 0
        self._gpu_batch_size = 1
        self._cpu_batch_size = 1
        self._cpu_model = whisper_model

        try:
            from .whisper_pool import WhisperModelPool, _FASTER_WHISPER, _BATCHED_AVAILABLE, _cuda_available, _gpu_vram_gb, _MODEL_MEM_CT2, _BATCH_MEM_PER_ELEMENT_GB
            import psutil as _ps

            # Use the same config calculation as WhisperModelPool
            # Create a temporary instance to compute config without loading models
            pool = WhisperModelPool.__new__(WhisperModelPool)
            pool._device = "cuda" if _cuda_available else "cpu"

            # CPU model selection: match GPU model when RAM allows
            gpu_mem = _MODEL_MEM_CT2.get(whisper_model, 2.5)
            free_ram = _ps.virtual_memory().available / (1024**3)
            if free_ram > (4.0 + gpu_mem * 3):
                pool._cpu_model_size = whisper_model
            else:
                pool._cpu_model_size = 'small' if whisper_model in ('medium', 'large', 'large-v2', 'large-v3') else whisper_model

            self._cpu_model = pool._cpu_model_size
            config = pool._calculate_config(whisper_model, hybrid_mode=(_cuda_available))

            self._gpu_workers = config['gpu_workers']
            self._cpu_workers = config['cpu_workers']
            self._gpu_batch_size = config['gpu_batch_size']
            self._cpu_batch_size = config['cpu_batch_size']

        except Exception:
            self._gpu_workers = 1 if self._has_gpu else 0
            self._cpu_workers = 2

    def _estimate_whisper_time(self, total_duration_seconds: float) -> tuple:
        """Estimate wall-clock processing time.

        Returns (optimistic_minutes, conservative_minutes).
        Optimistic: full throughput, no throttling.
        Conservative: +40% overhead for language detection, throttling, I/O.
        """
        dur_min = total_duration_seconds / 60.0

        # GPU throughput
        if self._has_gpu and self._gpu_workers > 0:
            if self._batched:
                gpu_ratio = self.WHISPER_RATIOS_GPU_BATCHED.get(self.whisper_model, 0.07)
            else:
                gpu_ratio = self.WHISPER_RATIOS_GPU_SINGLE.get(self.whisper_model, 0.18)
            gpu_capacity = self._gpu_workers / gpu_ratio  # minutes of audio per minute of wall-clock
        else:
            gpu_capacity = 0

        # CPU throughput
        if self._cpu_workers > 0:
            if self._batched:
                cpu_ratio = self.WHISPER_RATIOS_CPU_BATCHED.get(self._cpu_model, 0.18)
            else:
                cpu_ratio = self.WHISPER_RATIOS_CPU_SINGLE.get(self._cpu_model, 0.35)
            cpu_capacity = self._cpu_workers / cpu_ratio
        else:
            cpu_capacity = 0

        total_capacity = gpu_capacity + cpu_capacity  # audio-minutes per wall-minute
        if total_capacity <= 0:
            return (dur_min, dur_min)

        whisper_time = dur_min / total_capacity

        # Diarization: pipeline model
        # Phase A (during whisper): 1 CPU worker diarizes in background
        # Phase B (after whisper): remaining files on GPU with 2 workers
        diarize_tail = 0
        if self._diarize:
            # How much audio gets diarized on CPU during whisper?
            cpu_diarize_capacity = self.DIARIZE_CPU_WORKERS / self.DIARIZE_RATIO_CPU  # audio-min per wall-min
            cpu_diarized_during_whisper = cpu_diarize_capacity * whisper_time  # audio-minutes diarized
            remaining_audio = max(0, dur_min - cpu_diarized_during_whisper)

            # Remaining diarized on GPU after whisper
            if remaining_audio > 0:
                gpu_diarize_capacity = self.DIARIZE_GPU_WORKERS / self.DIARIZE_RATIO_GPU
                diarize_tail = remaining_audio / gpu_diarize_capacity

        optimistic = whisper_time + diarize_tail
        conservative = optimistic * 1.4
        return (optimistic, conservative, whisper_time, diarize_tail)

    def _get_media_duration(self, file_path: Path) -> float:
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(file_path)
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass
        return 0

    def calculate_audio_time(self, audio_paths: List[Path]) -> Dict:
        total_dur = 0
        ok = 0
        for p in audio_paths:
            d = self._get_media_duration(p)
            if d > 0:
                total_dur += d
                ok += 1
        opt, con, whisper_t, diarize_t = self._estimate_whisper_time(total_dur)
        return {
            'file_count': len(audio_paths), 'successful_count': ok,
            'total_duration_minutes': total_dur / 60.0,
            'processing_time_minutes': (opt + con) / 2,
            'processing_time_range': (opt, con),
            'whisper_time_minutes': whisper_t,
            'diarize_time_minutes': diarize_t,
            'model': self.whisper_model,
            'workers': self._gpu_workers + self._cpu_workers,
        }

    def calculate_video_time(self, video_paths: List[Path]) -> Dict:
        total_dur = 0
        ok = 0
        for p in video_paths:
            d = self._get_media_duration(p)
            if d > 0:
                total_dur += d
                ok += 1
        opt, con, whisper_t, diarize_t = self._estimate_whisper_time(total_dur)
        return {
            'file_count': len(video_paths), 'successful_count': ok,
            'total_duration_minutes': total_dur / 60.0,
            'processing_time_minutes': (opt + con) / 2,
            'processing_time_range': (opt, con),
            'whisper_time_minutes': whisper_t,
            'diarize_time_minutes': diarize_t,
            'model': self.whisper_model,
            'workers': self._gpu_workers + self._cpu_workers,
        }

    def calculate_pdf_time(self, pdf_paths: List[Path]) -> Dict:
        total_size = sum(p.stat().st_size for p in pdf_paths if p.exists())
        mb = total_size / (1024 * 1024)
        t = mb / self.PDF_MB_PER_MINUTE
        return {'file_count': len(pdf_paths), 'total_size_mb': mb, 'processing_time_minutes': t}

    def calculate_image_time(self, image_paths: List[Path]) -> Dict:
        t = len(image_paths) * self.IMAGE_SECONDS_EACH / 60.0
        return {'file_count': len(image_paths), 'processing_time_minutes': t}

    def calculate_document_time(self, doc_paths: List[Path]) -> Dict:
        total_size = sum(p.stat().st_size for p in doc_paths if p.exists())
        mb = total_size / (1024 * 1024)
        t = mb / self.DOCUMENT_MB_PER_MINUTE
        return {'file_count': len(doc_paths), 'total_size_mb': mb, 'processing_time_minutes': t}

    def calculate_all(self, materials: Dict[str, List[Path]]) -> Dict:
        audio_est = self.calculate_audio_time(materials.get('audio', []))
        video_est = self.calculate_video_time(materials.get('videos', []))
        pdf_est = self.calculate_pdf_time(materials.get('pdfs', []))
        image_est = self.calculate_image_time(materials.get('images', []))
        doc_est = self.calculate_document_time(materials.get('documents', []))

        total_time = (
            audio_est['processing_time_minutes'] +
            video_est['processing_time_minutes'] +
            pdf_est['processing_time_minutes'] +
            image_est['processing_time_minutes'] +
            doc_est['processing_time_minutes']
        )
        total_files = (
            audio_est['file_count'] + video_est['file_count'] +
            pdf_est['file_count'] + image_est['file_count'] + doc_est['file_count']
        )

        # Aggregate time range from whisper tasks
        opt_total = 0
        con_total = 0
        for est in (audio_est, video_est):
            r = est.get('processing_time_range', (est['processing_time_minutes'], est['processing_time_minutes']))
            opt_total += r[0]
            con_total += r[1]
        # Add non-whisper time to both
        other_time = pdf_est['processing_time_minutes'] + image_est['processing_time_minutes'] + doc_est['processing_time_minutes']
        opt_total += other_time
        con_total += other_time

        # Aggregate whisper and diarize times separately
        whisper_total = sum(est.get('whisper_time_minutes', 0) for est in (audio_est, video_est))
        diarize_total = sum(est.get('diarize_time_minutes', 0) for est in (audio_est, video_est))

        return {
            'audio': audio_est, 'videos': video_est,
            'pdfs': pdf_est, 'images': image_est, 'documents': doc_est,
            'totals': {
                'total_files': total_files,
                'total_time_minutes': total_time,
                'total_time_range': (opt_total, con_total),
                'total_time_hours': total_time / 60.0,
                'whisper_time_minutes': whisper_total,
                'diarize_time_minutes': diarize_total,
            }
        }

    def format_estimate(self, estimates: Dict) -> str:
        """Format for API / plain text."""
        t = estimates['totals']
        r = t.get('total_time_range', (t['total_time_minutes'], t['total_time_minutes']))
        return f"{t['total_files']} files | ~{self._fmt(r[0])} - {self._fmt(r[1])}"

    @staticmethod
    def _fmt(minutes: float) -> str:
        if minutes < 1:
            return f"{int(minutes * 60)}s"
        elif minutes < 60:
            m = int(minutes)
            s = int((minutes - m) * 60)
            return f"{m}m {s}s" if s > 0 else f"{m}m"
        else:
            h = int(minutes // 60)
            m = int(minutes % 60)
            return f"{h}h {m}m"
