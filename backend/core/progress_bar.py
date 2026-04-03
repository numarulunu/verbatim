"""
CLI Progress Display - Claude Code inspired UI

Clean, minimal progress display with:
- Braille dot spinner animation
- ANSI color output
- Single-line progress with ETA
- Animated status transitions
"""

import sys
import time
import threading
import os

# Force UTF-8 output on Windows (required for Unicode progress bar characters)
if sys.platform == "win32":
    try:
        # Set console code page to UTF-8
        os.system("chcp 65001 > nul 2>&1")
        # Reconfigure stdout/stderr to UTF-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── ANSI helpers ──────────────────────────────────────────────────────────────

def _supports_ansi() -> bool:
    """Check if terminal supports ANSI escape codes."""
    if os.getenv("NO_COLOR"):
        return False
    if sys.platform == "win32":
        # Windows 10 1607+ supports ANSI via Virtual Terminal Processing
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ANSI on stdout
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_ANSI = _supports_ansi()


def _c(code: str, text: str) -> str:
    """Apply ANSI color code to text. No-op if ANSI not supported."""
    if not _ANSI:
        return text
    return f"\033[{code}m{text}\033[0m"


# Color shortcuts
def dim(text: str) -> str:
    return _c("2", text)

def bold(text: str) -> str:
    return _c("1", text)

def cyan(text: str) -> str:
    return _c("36", text)

def green(text: str) -> str:
    return _c("32", text)

def red(text: str) -> str:
    return _c("31", text)

def yellow(text: str) -> str:
    return _c("33", text)

def bold_cyan(text: str) -> str:
    return _c("1;36", text)

def bold_green(text: str) -> str:
    return _c("1;32", text)

def dim_white(text: str) -> str:
    return _c("2;37", text)


# ── Spinner ───────────────────────────────────────────────────────────────────

BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """Braille dot spinner with message, Claude CLI style."""

    def __init__(self, message: str = ""):
        self.message = message
        self._running = False
        self._thread = None
        self._frame = 0
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self, final_message: str = None):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        # Clear the spinner line
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
        if final_message:
            sys.stdout.write(final_message + "\n")
            sys.stdout.flush()

    def update_message(self, message: str):
        with self._lock:
            self.message = message

    def _animate(self):
        while self._running:
            with self._lock:
                frame = cyan(BRAILLE_FRAMES[self._frame % len(BRAILLE_FRAMES)])
                msg = self.message
            sys.stdout.write(f"\r  {frame} {msg}" + " " * 20)
            sys.stdout.flush()
            self._frame += 1
            time.sleep(0.08)


# ── Progress Bar ──────────────────────────────────────────────────────────────

class ProgressBar:
    """
    Claude CLI-style progress display.

    Shows:
      ⠹ Processing  ━━━━━━━━━━━━━━━────────  68%  17/25 files  ETA 1m 24s
    """

    BAR_WIDTH = 20

    def __init__(self, total: int, desc: str = "Processing", workers: int = 1,
                 resource_fn=None, diarize_fn=None, **kwargs):
        self.total = total
        self.current = 0
        self.desc = desc
        self.workers = workers
        self.resource_fn = resource_fn  # Callable returning resource status dict
        self.diarize_fn = diarize_fn    # Callable returning (done, total) for diarization
        self.start_time = time.time()
        self.last_update = 0
        self.lock = threading.Lock()
        self.finished = False
        self._frame = 0

        # Render initial state
        self._render()

        # Heartbeat thread for spinner animation + elapsed time updates
        self._heartbeat_active = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._heartbeat_thread.start()

    def update(self, n: int = 1):
        with self.lock:
            self.current += n
            now = time.time()
            if now - self.last_update < 0.08 and self.current < self.total:
                return
            self.last_update = now
            self._render()

    def _render(self):
        if self.finished:
            return

        clamped = min(self.current, self.total)
        pct = (clamped / self.total * 100) if self.total > 0 else 0
        filled = int((clamped / self.total) * self.BAR_WIDTH) if self.total > 0 else 0

        # ETA calculation
        elapsed = time.time() - self.start_time
        if self.current > 0:
            rate = self.current / elapsed
            remaining = (self.total - self.current) / rate if rate > 0 else 0
            eta = self._fmt_time(remaining)
        else:
            eta = self._fmt_time(elapsed)

        # Spinner frame
        spinner = cyan(BRAILLE_FRAMES[self._frame % len(BRAILLE_FRAMES)])

        # Progress bar with Unicode
        bar_filled = "━" * filled
        bar_empty = "─" * (self.BAR_WIDTH - filled)
        bar = bold_cyan(bar_filled) + dim(bar_empty)

        # Compose line
        pct_str = bold(f"{pct:5.1f}%")
        count_str = dim(f"{clamped}/{self.total}")
        eta_label = dim("ETA") if self.current > 0 else dim("elapsed")
        eta_str = dim(eta)

        # Compact resource + diarize status
        extra = ""
        if self.resource_fn:
            try:
                status = self.resource_fn()
                if status:
                    state = status.get('state', '')
                    icons = {'boost': green('⚡'), 'normal': dim('●'),
                             'conserve': yellow('▼'), 'pause': red('⏸')}
                    icon = icons.get(state, dim('●'))
                    c = status.get('cpu', 0)
                    r = status.get('ram', 0)
                    g = status.get('gpu')
                    gpu_part = f" GPU {g}%" if g is not None else ""
                    extra = f"  {icon} {dim(f'CPU {c}% RAM {r}%{gpu_part}')}"
            except Exception:
                pass

        if self.diarize_fn:
            try:
                d_done, d_total = self.diarize_fn()
                if d_total > 0:
                    extra += f"  {dim(f'spk:{d_done}/{d_total}')}"
            except Exception:
                pass

        line = f"  {spinner} {self.desc}  {bar}  {pct_str}  {count_str}  {eta_label} {eta_str}{extra}"
        # Clear line + carriage return (prevents wrapping artifacts)
        sys.stdout.write(f"\r\033[2K{line}")
        sys.stdout.flush()

    def _heartbeat(self):
        """Update spinner frame and re-render periodically."""
        while self._heartbeat_active and not self.finished:
            time.sleep(0.08)
            with self.lock:
                self._frame += 1
                if not self.finished:
                    self._render()

    def finish(self):
        with self.lock:
            self._heartbeat_active = False
            self.current = self.total
            self.finished = True

            elapsed = time.time() - self.start_time
            elapsed_str = self._fmt_time(elapsed)

            bar = bold_green("━" * self.BAR_WIDTH)
            check = green("✓")
            done = bold_green("Done")
            count_str = dim(f"{self.total}/{self.total}")
            time_str = dim(f"in {elapsed_str}")

            line = f"\r  {check} {done}  {bar}  {bold('100.0%')}  {count_str}  {time_str}"
            sys.stdout.write(line + " " * 10 + "\n")
            sys.stdout.flush()

    def close(self):
        if not self.finished:
            self.finish()

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        if seconds < 0:
            return "0s"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}h {m}m"
        elif m > 0:
            return f"{m}m {s}s"
        else:
            return f"{s}s"


# ── Preflight display ─────────────────────────────────────────────────────────

def print_preflight(estimates: dict):
    """Print Claude CLI-style preflight summary."""
    totals = estimates['totals']
    total_files = totals['total_files']

    # Header
    print()
    print(f"  {bold_cyan('Transcriptor')}")
    print(f"  {dim('─' * 50)}")
    print()

    # File type breakdown
    sections = [
        ('audio', 'Audio', '♪'),
        ('videos', 'Video', '▶'),
        ('pdfs', 'PDF', '◆'),
        ('images', 'Image', '◼'),
        ('documents', 'Docs', '≡'),
    ]

    for key, label, icon in sections:
        data = estimates.get(key, {})
        count = data.get('file_count', 0)
        if count == 0:
            continue

        count_str = bold(str(count))
        label_str = dim(label)

        extras = []
        if 'total_duration_minutes' in data and data['total_duration_minutes'] > 0:
            dur = _fmt_duration(data['total_duration_minutes'])
            extras.append(dim(f"{dur} duration"))
        if 'total_size_mb' in data and data['total_size_mb'] > 0:
            extras.append(dim(f"{data['total_size_mb']:.1f} MB"))

        extra_str = dim(" · ").join(extras)
        if extra_str:
            extra_str = f"  {extra_str}"

        print(f"  {cyan(icon)} {count_str} {label_str}{extra_str}")

    print()

    # Total estimate with transcription/diarization breakdown
    time_range = totals.get('total_time_range')
    workers = estimates.get('audio', {}).get('workers', estimates.get('videos', {}).get('workers', 1))

    if time_range and time_range[0] != time_range[1]:
        opt_str = _fmt_duration(time_range[0])
        con_str = _fmt_duration(time_range[1])
        time_display = f"{dim('~')}{bold(opt_str)} {dim('-')} {bold(con_str)}"
    else:
        time_display = f"{dim('~')}{bold(_fmt_duration(totals['total_time_minutes']))}"

    print(f"  {dim('Total:')} {bold(str(total_files))} {dim('files')}  {dim('·')}  {time_display}  {dim('·')}  {bold(str(workers))} {dim('workers')}")

    # Show transcription vs diarization breakdown
    whisper_t = totals.get('whisper_time_minutes', 0)
    diarize_t = totals.get('diarize_time_minutes', 0)
    if whisper_t > 0:
        parts = [f"transcription ~{_fmt_duration(whisper_t)}"]
        if diarize_t > 0:
            parts.append(f"diarization ~{_fmt_duration(diarize_t)}")
        print(f"         {dim(' + ').join(dim(p) for p in parts)}")

    print()
    print(f"  {dim('Press Enter to start...')}")


def print_model_info(backend: str, model: str, gpu_w: int, cpu_w: int):
    """Print model loading result, Claude CLI style."""
    check = green("✓")
    parts = [
        f"{check} {bold(backend)}",
        dim(f"model: {model}"),
        dim(f"{gpu_w} GPU + {cpu_w} CPU"),
    ]
    print(f"  {dim(' · ').join(parts)}")
    print()


def print_model_info_full(info: dict):
    """Print detailed model loading result with batch info."""
    check = green("✓")
    backend = bold(info.get('backend', '?'))

    gpu_w = info.get('gpu_workers', 0)
    cpu_w = info.get('cpu_workers', 0)
    gpu_model = info.get('gpu_model', '?')
    cpu_model = info.get('cpu_model', '?')
    gpu_bs = info.get('gpu_batch_size', 1)
    cpu_bs = info.get('cpu_batch_size', 1)
    batched = info.get('batched', False)

    parts = []
    if gpu_w > 0:
        gpu_str = f"{gpu_w} GPU ({gpu_model}"
        if batched and gpu_bs > 1:
            gpu_str += f", batch={gpu_bs}"
        gpu_str += ")"
        parts.append(gpu_str)
    if cpu_w > 0:
        cpu_threads = info.get('cpu_threads', 0)
        cpu_str = f"{cpu_w} CPU ({cpu_model}"
        if batched and cpu_bs > 1:
            cpu_str += f", batch={cpu_bs}"
        if cpu_threads > 0:
            cpu_str += f", {cpu_threads}t each"
        cpu_str += ")"
        parts.append(cpu_str)

    worker_str = dim(" + ").join(dim(p) for p in parts)
    print(f"  {check} {backend}  {worker_str}")
    print()


def print_no_files(message: str = "No files to process"):
    """Print no-files message."""
    print()
    print(f"  {dim(message)}")
    print()


def print_error(message: str):
    """Print error message."""
    print(f"  {red('✗')} {red(message)}")


def _fmt_duration(minutes: float) -> str:
    if minutes < 1:
        return f"{int(minutes * 60)}s"
    elif minutes < 60:
        m = int(minutes)
        s = int((minutes - m) * 60)
        if s > 0:
            return f"{m}m {s}s"
        return f"{m}m"
    else:
        h = int(minutes // 60)
        m = int(minutes % 60)
        return f"{h}h {m}m"


class DummyProgressBar:
    def __init__(self, *args, **kwargs):
        pass
    def update(self, n: int = 1):
        pass
    def finish(self):
        pass
    def close(self):
        pass


def create_progress_bar(total: int, desc: str = "Processing", enabled: bool = True,
                        workers: int = 1, resource_fn=None):
    if enabled and total > 0:
        return ProgressBar(total, desc, workers=workers, resource_fn=resource_fn)
    return DummyProgressBar()
