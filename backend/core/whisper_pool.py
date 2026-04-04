"""
Whisper Model Pool - Batched Multi-Worker Pool with Resource-Aware Throttling

Uses faster-whisper (CTranslate2) with BatchedInferencePipeline for maximum throughput.
GPU workers: batched inference (medium model, int8_float32, batch_size auto)
CPU workers: batched inference (small model, int8, lower batch_size)
Dynamic resource monitoring prevents system overload while squeezing safe throughput.
"""

import os
import threading
import time
import warnings
import psutil
from typing import Optional, Tuple
from queue import Queue

# Suppress noisy HuggingFace warnings about symlinks on Windows
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
warnings.filterwarnings("ignore", message=".*huggingface_hub.*cache.*symlinks.*")
warnings.filterwarnings("ignore", message=".*pynvml.*deprecated.*")
warnings.filterwarnings("ignore", category=FutureWarning, module=".*pynvml.*")

import logging

from .quiet import quiet_print

logger = logging.getLogger('transcriptor.whisper')

# ── Hardware detection ────────────────────────────────────────────────────────

_cuda_available = False
_gpu_name = "Unknown"
_gpu_vram_gb = 0.0
_gpu_compute_capability = (0, 0)
try:
    import torch
    _cuda_available = torch.cuda.is_available()
    if _cuda_available:
        _gpu_name = torch.cuda.get_device_name(0)
        _gpu_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        _gpu_compute_capability = torch.cuda.get_device_capability(0)
except ImportError:
    pass


def _best_gpu_compute_type() -> str:
    """Pick the fastest CTranslate2 compute type for the GPU.
    SM 7.0+ (Volta/Turing/Ampere): float16
    SM 6.x  (Pascal, e.g. GTX 1080 Ti): int8_float32
    Older: float32
    """
    major, _ = _gpu_compute_capability
    if major >= 7:
        return "float16"
    elif major == 6:
        return "int8_float32"
    return "float32"


# ── Backend detection ─────────────────────────────────────────────────────────

_FASTER_WHISPER = False
_BATCHED_AVAILABLE = False
_OPENAI_WHISPER = False

try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    _FASTER_WHISPER = True
    try:
        from faster_whisper import BatchedInferencePipeline
        _BATCHED_AVAILABLE = True
    except ImportError:
        pass
except ImportError:
    pass

if not _FASTER_WHISPER:
    try:
        import whisper as openai_whisper
        _OPENAI_WHISPER = True
    except ImportError:
        pass


# ── Resource Governor ─────────────────────────────────────────────────────────

class ResourceGovernor:
    """Adaptive resource governor — scales processing intensity based on system load.

    Distinguishes between OUR CPU usage (expected) and EXTERNAL load (back off).
    Instead of binary pause/resume, continuously adjusts a power_level (0.0-1.0)
    that scales batch sizes per-transcription call.

    Power states:
      boost    (>0.8)  System idle, push harder — batch_size * 1.5
      normal   (>0.5)  Steady state — base batch_size
      conserve (>0.1)  External load detected — batch_size * 0.6
      pause    (≤0.1)  Critical pressure — wait until headroom returns
    """

    def __init__(self, check_interval: float = 1.0):
        self._interval = check_interval
        self._process = psutil.Process()
        self._logical_cores = psutil.cpu_count(logical=True) or 8
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # EMA smoothing factor (0.3 = responsive but stable)
        self._alpha = 0.3

        # Smoothed resource readings (0-100 scale)
        self.cpu_total = 0.0
        self.cpu_own = 0.0
        self.cpu_external = 0.0
        self.ram_pct = 0.0
        self.gpu_compute = 0.0    # GPU core utilization %
        self.vram_pct = 0.0       # VRAM usage %

        # Derived state
        self.power_level = 1.0    # 0.0-1.0
        self.state = "boost"      # boost/normal/conserve/pause

        # NVML for real GPU monitoring (CTranslate2 doesn't use PyTorch allocator)
        self._nvml_handle = None
        if _cuda_available:
            try:
                import warnings as _w
                with _w.catch_warnings():
                    _w.filterwarnings("ignore", message=".*pynvml.*deprecated.*")
                    from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex
                nvmlInit()
                self._nvml_handle = nvmlDeviceGetHandleByIndex(0)
            except Exception:
                pass

        # Prime psutil counters (first call always returns 0)
        psutil.cpu_percent(interval=0)
        try:
            self._process.cpu_percent(interval=0)
        except Exception:
            pass

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def wait_if_busy(self, timeout: float = 60.0):
        """Block only under critical pressure (power_level near zero)."""
        if self.power_level > 0.1:
            return
        deadline = time.monotonic() + timeout
        while self.power_level <= 0.1 and time.monotonic() < deadline:
            time.sleep(0.5)

    def get_batch_multiplier(self) -> float:
        """Returns multiplier for batch sizes (0.3x – 1.0x). Never exceeds base."""
        if self.power_level > 0.5:
            return 1.0
        elif self.power_level > 0.2:
            return 0.6
        else:
            return 0.3

    def get_status(self) -> dict:
        """Current resource snapshot for live display."""
        return {
            'cpu': round(self.cpu_total),
            'ram': round(self.ram_pct),
            'gpu': round(self.gpu_compute) if _cuda_available else None,
            'vram': round(self.vram_pct) if _cuda_available else None,
            'power': round(self.power_level, 2),
            'state': self.state,
        }

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(self._interval)

    def _update(self):
        a = self._alpha

        # CPU: total system
        raw_total = psutil.cpu_percent(interval=0)
        self.cpu_total = a * raw_total + (1 - a) * self.cpu_total

        # CPU: our process (normalize from per-core % to system %)
        try:
            raw_own = self._process.cpu_percent(interval=0) / self._logical_cores
        except Exception:
            raw_own = 0
        self.cpu_own = a * raw_own + (1 - a) * self.cpu_own

        # CPU: external = total minus ours
        self.cpu_external = max(0, self.cpu_total - self.cpu_own)

        # RAM
        raw_ram = psutil.virtual_memory().percent
        self.ram_pct = a * raw_ram + (1 - a) * self.ram_pct

        # GPU via NVML (sees CTranslate2 allocations, not just PyTorch)
        if self._nvml_handle:
            try:
                from pynvml import nvmlDeviceGetUtilizationRates, nvmlDeviceGetMemoryInfo  # noqa
                util = nvmlDeviceGetUtilizationRates(self._nvml_handle)
                mem = nvmlDeviceGetMemoryInfo(self._nvml_handle)
                raw_gpu = util.gpu
                raw_vram = (mem.used / mem.total * 100) if mem.total > 0 else 0
            except Exception:
                raw_gpu = 0
                raw_vram = 0
            self.gpu_compute = a * raw_gpu + (1 - a) * self.gpu_compute
            self.vram_pct = a * raw_vram + (1 - a) * self.vram_pct

        # Only system RAM drives throttling decisions.
        # CPU: our own workers are supposed to use the CPU — not a pressure signal.
        # VRAM: CTranslate2 pre-allocates its memory pool at load — always ~95-100%.
        #       Reducing batch size doesn't free VRAM. Not a useful signal.
        # RAM: the real indicator of external pressure (other apps eating memory).
        # Ramps 0→1 over 85%→95%
        ram_pressure = min(1.0, max(0.0, (self.ram_pct - 85) / 10.0))

        pressure = ram_pressure
        with self._lock:
            self.power_level = max(0.0, min(1.0, 1.0 - pressure))

            if self.power_level > 0.5:
                self.state = "normal"
            elif self.power_level > 0.1:
                self.state = "conserve"
            else:
                self.state = "pause"


# ── Model memory constants ────────────────────────────────────────────────────

# Base model VRAM/RAM in GB (faster-whisper CTranslate2)
_MODEL_MEM_CT2 = {
    'tiny': 0.4, 'base': 0.7, 'small': 1.1,
    'medium': 2.5, 'large': 5.0, 'large-v2': 5.0, 'large-v3': 5.0,
}
# Extra VRAM per batch element during batched inference (~MB per element)
_BATCH_MEM_PER_ELEMENT_GB = 0.12


# ── Whisper Model Pool ────────────────────────────────────────────────────────

class WhisperModelPool:
    """Thread-safe pool with batched inference and resource-aware throttling.

    GPU workers: BatchedInferencePipeline + medium model + auto batch_size
    CPU workers: BatchedInferencePipeline + small model (faster on CPU) + smaller batch_size
    """

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self, model_size: str = "auto", force_cpu: bool = False,
                   num_workers: int = None, hybrid_mode: bool = True,
                   language: str = None, beam_size: int = 1) -> bool:
        with self._init_lock:
            if self._initialized and hasattr(self, '_model_size') and self._model_size == model_size:
                return True

            if not _FASTER_WHISPER and not _OPENAI_WHISPER:
                raise RuntimeError("No whisper backend. Install faster-whisper or openai-whisper.")

            self._backend = "faster-whisper" if _FASTER_WHISPER else "openai-whisper"
            self._language = language
            self._beam_size = max(1, beam_size)

            if model_size == "auto":
                model_size = self._select_model_by_memory()

            self._model_size = model_size
            # CPU model: match GPU model when RAM allows, otherwise fall back to 'small'
            free_ram_gb = psutil.virtual_memory().available / (1024**3)
            cpu_model_mem = _MODEL_MEM_CT2.get(model_size, 2.5)
            # Need ~4GB system headroom + model RAM per worker (estimate 3 workers)
            if free_ram_gb > (4.0 + cpu_model_mem * 3):
                self._cpu_model_size = model_size  # Same quality as GPU
            else:
                self._cpu_model_size = 'small' if model_size in ('medium', 'large', 'large-v2', 'large-v3') else model_size

            self._device = "cpu"
            if not force_cpu and _cuda_available:
                self._device = "cuda"
            if force_cpu:
                hybrid_mode = False

            # Calculate workers and batch sizes
            config = self._calculate_config(model_size, hybrid_mode)
            self._gpu_workers = config['gpu_workers']
            self._cpu_workers = config['cpu_workers']
            self._gpu_batch_size = config['gpu_batch_size']
            self._cpu_batch_size = config['cpu_batch_size']
            self._cpu_threads = config.get('cpu_threads', 4)
            self._num_workers = self._gpu_workers + self._cpu_workers

            if num_workers is not None and not hybrid_mode:
                if self._device == "cuda":
                    self._gpu_workers = num_workers
                    self._cpu_workers = 0
                else:
                    self._gpu_workers = 0
                    self._cpu_workers = num_workers
                self._num_workers = num_workers

            # Adaptive resource governor — scales batch sizes based on system load
            self._governor = ResourceGovernor(check_interval=1.0)
            self._governor.start()

            # Load models
            self._models = []
            self._model_queue = Queue(maxsize=self._num_workers)
            self._load_models()

            self._initialized = True
            return True

    def transcribe(self, audio_path: str, **kwargs) -> dict:
        """Transcribe audio/video file. Thread-safe, batched, resource-aware."""
        self._governor.wait_if_busy()

        entry = self._model_queue.get()
        try:
            if self._backend == "faster-whisper":
                return self._transcribe_faster(entry, audio_path, **kwargs)
            else:
                return self._transcribe_openai(entry, audio_path, **kwargs)
        finally:
            self._model_queue.put(entry)

    # ── Transcription backends ────────────────────────────────────────────────

    def _transcribe_faster(self, entry: dict, audio_path: str, **kwargs) -> dict:
        params = {
            'beam_size': self._beam_size,
            'vad_filter': True,
            'vad_parameters': {'min_silence_duration_ms': 500},
            'condition_on_previous_text': False,
            # ── Micro-optimizations ──
            'temperature': 0,           # Single pass, no retry cascade (default retries 6 temps)
            'no_speech_threshold': 0.4,  # Skip silence faster (default 0.6, lower = more aggressive)
        }
        if self._language:
            params['language'] = self._language

        # Batched pipeline: dynamically scale batch_size based on system load
        if entry.get('batched'):
            base_bs = entry['batch_size']
            multiplier = self._governor.get_batch_multiplier()
            params['batch_size'] = max(1, int(base_bs * multiplier))

        params.update(kwargs)

        # Always request word timestamps for accurate diarization
        params['word_timestamps'] = True

        segments, info = entry['model'].transcribe(audio_path, **params)

        seg_list = []
        word_list = []
        text_parts = []
        for seg in segments:
            text_parts.append(seg.text)
            seg_list.append({'start': seg.start, 'end': seg.end, 'text': seg.text})
            # Collect word-level timestamps
            if hasattr(seg, 'words') and seg.words:
                for w in seg.words:
                    word_list.append({
                        'start': w.start,
                        'end': w.end,
                        'word': w.word,
                    })

        return {
            'text': " ".join(text_parts),
            'segments': seg_list,
            'words': word_list,
            '_device': "GPU" if entry['device'] == "cuda" else "CPU",
            '_language': getattr(info, 'language', 'unknown'),
            '_duration': getattr(info, 'duration', 0),
        }

    def _transcribe_openai(self, entry: dict, audio_path: str, **kwargs) -> dict:
        import warnings
        device = entry['device']
        if 'cuda' in device and 'fp16' not in kwargs:
            kwargs['fp16'] = True
        elif 'cpu' in device and 'fp16' not in kwargs:
            kwargs['fp16'] = False
        if 'verbose' not in kwargs:
            kwargs['verbose'] = None
        kwargs['condition_on_previous_text'] = False
        kwargs.setdefault('temperature', 0)
        kwargs.setdefault('no_speech_threshold', 0.4)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            result = entry['model'].transcribe(audio_path, **kwargs)

        result['_device'] = "GPU" if 'cuda' in device else "CPU"
        return result

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_models(self):
        if self._backend == "faster-whisper":
            self._load_faster_whisper()
        else:
            self._load_openai_whisper()

    def _load_faster_whisper(self):
        gpu_compute = _best_gpu_compute_type()
        use_batched = _BATCHED_AVAILABLE

        # Use thread count from config calculation
        cpu_threads = self._cpu_threads or 4

        # GPU workers: primary model + batched pipeline
        for i in range(self._gpu_workers):
            try:
                base_model = FasterWhisperModel(
                    self._model_size,
                    device="cuda",
                    compute_type=gpu_compute,
                    num_workers=1,
                )
                if use_batched:
                    pipeline = BatchedInferencePipeline(model=base_model)
                    entry = {
                        'model': pipeline,
                        'device': 'cuda',
                        'batched': True,
                        'batch_size': self._gpu_batch_size,
                        'model_name': self._model_size,
                    }
                else:
                    entry = {'model': base_model, 'device': 'cuda', 'batched': False,
                             'model_name': self._model_size}
                self._models.append(entry)
                self._model_queue.put(entry)
            except Exception as e:
                quiet_print(f"ERROR loading GPU model {i+1}: {e}", error=True)
                raise

        # CPU workers: same or smaller model + batched pipeline
        for i in range(self._cpu_workers):
            try:
                base_model = FasterWhisperModel(
                    self._cpu_model_size,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=cpu_threads,
                )
                if use_batched:
                    pipeline = BatchedInferencePipeline(model=base_model)
                    entry = {
                        'model': pipeline,
                        'device': 'cpu',
                        'batched': True,
                        'batch_size': self._cpu_batch_size,
                        'model_name': self._cpu_model_size,
                    }
                else:
                    entry = {'model': base_model, 'device': 'cpu', 'batched': False,
                             'model_name': self._cpu_model_size}
                self._models.append(entry)
                self._model_queue.put(entry)
            except Exception as e:
                quiet_print(f"ERROR loading CPU model {i+1}: {e}", error=True)
                raise

    def _load_openai_whisper(self):
        import warnings
        for i in range(self._gpu_workers):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore")
                    model = openai_whisper.load_model(self._model_size, device="cuda")
                entry = {'model': model, 'device': 'cuda', 'batched': False,
                         'model_name': self._model_size}
                self._models.append(entry)
                self._model_queue.put(entry)
            except Exception as e:
                quiet_print(f"ERROR loading GPU model {i+1}: {e}", error=True)
                raise

        for i in range(self._cpu_workers):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore")
                    model = openai_whisper.load_model(self._cpu_model_size, device="cpu")
                entry = {'model': model, 'device': 'cpu', 'batched': False,
                         'model_name': self._cpu_model_size}
                self._models.append(entry)
                self._model_queue.put(entry)
            except Exception as e:
                quiet_print(f"ERROR loading CPU model {i+1}: {e}", error=True)
                raise

    # ── Configuration calculation ─────────────────────────────────────────────

    def _calculate_config(self, model_size: str, hybrid_mode: bool) -> dict:
        """Calculate optimal workers and batch sizes based on hardware."""
        gpu_mem = _MODEL_MEM_CT2.get(model_size, 2.5)
        cpu_model = self._cpu_model_size
        cpu_mem = _MODEL_MEM_CT2.get(cpu_model, 1.1)

        gpu_workers = 0
        gpu_batch_size = 1
        cpu_workers = 0
        cpu_batch_size = 1
        config_cpu_threads = 4

        if _cuda_available and self._device != "cpu":
            # Reserve 2.5 GB for system (display, other apps, CUDA overhead)
            usable_vram = max(0, _gpu_vram_gb - 2.5)

            if _BATCHED_AVAILABLE:
                # Batched: fewer workers, higher batch_size = better GPU utilization
                # Try 2 workers first, then 1 if not enough VRAM
                for n_workers in (2, 1):
                    base_cost = n_workers * gpu_mem
                    if base_cost > usable_vram:
                        continue
                    remaining = usable_vram - base_cost
                    per_worker_budget = remaining / n_workers
                    bs = max(4, min(24, int(per_worker_budget / _BATCH_MEM_PER_ELEMENT_GB)))
                    gpu_workers = n_workers
                    gpu_batch_size = bs
                    break
                if gpu_workers == 0:
                    gpu_workers = 1
                    gpu_batch_size = 4
            else:
                # Non-batched: more workers
                max_by_vram = int(usable_vram / gpu_mem)
                gpu_workers = max(1, min(max_by_vram, 4))
                gpu_batch_size = 1

        if hybrid_mode or self._device == "cpu":
            physical_cores = psutil.cpu_count(logical=False) or 4
            logical_cores = psutil.cpu_count(logical=True) or physical_cores
            total_ram_gb = psutil.virtual_memory().total / (1024**3)
            free_ram_gb = psutil.virtual_memory().available / (1024**3)
            # Reserve 2GB or 10% of total RAM for system, whichever is larger
            headroom = max(2.0, total_ram_gb * 0.10)
            usable_ram = max(0, free_ram_gb - headroom)
            max_by_ram = int(usable_ram / cpu_mem)

            # 4 threads per worker is the CTranslate2 sweet spot
            threads_per_worker = 4
            if self._device == "cuda":
                # Reserve threads for GPU I/O (batch feeding, result processing)
                # Without headroom, CPU workers starve GPU → GPU drops to 10-15%
                available = max(4, logical_cores - 8)
            else:
                available = logical_cores
            optimal = max(1, available // threads_per_worker)
            # Cap at 5 workers
            optimal = min(5, optimal)
            cpu_workers = max(1, min(max_by_ram, optimal))
            config_cpu_threads = threads_per_worker

            if _BATCHED_AVAILABLE:
                cpu_batch_size = 8  # 32GB RAM handles this easily
            else:
                cpu_batch_size = 1

        if not hybrid_mode:
            if self._device == "cuda":
                gpu_workers = max(1, gpu_workers)
                cpu_workers = 0
            else:
                cpu_workers = max(1, cpu_workers)
                gpu_workers = 0

        return {
            'gpu_workers': gpu_workers, 'gpu_batch_size': gpu_batch_size,
            'cpu_workers': cpu_workers, 'cpu_batch_size': cpu_batch_size,
            'cpu_threads': config_cpu_threads if cpu_workers > 0 else 0,
        }

    def _select_model_by_memory(self) -> str:
        if _cuda_available:
            if _gpu_vram_gb > 10: return "large-v3"
            elif _gpu_vram_gb > 5: return "medium"
            elif _gpu_vram_gb > 2: return "small"
            elif _gpu_vram_gb > 1.5: return "base"
            else: return "tiny"
        else:
            ram = psutil.virtual_memory().available / (1024**3)
            if ram > 16: return "medium"
            elif ram > 8: return "small"
            elif ram > 4: return "base"
            else: return "tiny"

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_device(self) -> str:
        return getattr(self, '_device', 'unknown')

    def get_num_workers(self) -> int:
        return getattr(self, '_num_workers', 0)

    def get_backend(self) -> str:
        return getattr(self, '_backend', 'unknown')

    def get_info(self) -> dict:
        """Full info dict for display."""
        return {
            'backend': self.get_backend(),
            'gpu_workers': getattr(self, '_gpu_workers', 0),
            'cpu_workers': getattr(self, '_cpu_workers', 0),
            'gpu_model': getattr(self, '_model_size', '?'),
            'cpu_model': getattr(self, '_cpu_model_size', '?'),
            'gpu_batch_size': getattr(self, '_gpu_batch_size', 1),
            'cpu_batch_size': getattr(self, '_cpu_batch_size', 1),
            'cpu_threads': getattr(self, '_cpu_threads', 0),
            'batched': _BATCHED_AVAILABLE,
        }

    def get_resource_status(self) -> dict:
        if hasattr(self, '_governor'):
            return self._governor.get_status()
        return {}

    def clear(self):
        if hasattr(self, '_governor'):
            self._governor.stop()
        if hasattr(self, '_models') and self._models:
            self._models.clear()
            self._model_queue = None
        if _cuda_available:
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
        self._initialized = False
