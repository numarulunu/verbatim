"""
Hardware-specific process controls for Windows + i7-12700K + GTX 1080 Ti.

Pins the current process (and therefore every child it spawns) to logical
P-cores 0-15. E-cores (16-19) are left idle for OS background work — they're
too slow for audio decoding and would stall the ProcessPool's critical path.

FFmpeg children inherit affinity, so pinning the orchestrator propagates to
every decode worker automatically.
"""
from __future__ import annotations

import logging
import os

import psutil

from config import P_CORE_AFFINITY

log = logging.getLogger(__name__)


def pin_to_p_cores() -> None:
    """Set the current process's CPU affinity to P-core logicals (inherited by children)."""
    proc = psutil.Process(os.getpid())
    try:
        proc.cpu_affinity(P_CORE_AFFINITY)
        log.info("pinned pid=%d to P-cores %s", os.getpid(), P_CORE_AFFINITY)
    except (AttributeError, psutil.AccessDenied, OSError) as exc:
        # cpu_affinity is missing on some platforms (macOS) — soft-fail.
        log.warning("cpu_affinity unavailable: %s", exc)


def detect_physical_layout() -> dict[str, list[int]]:
    """Return {'p_cores': [...], 'e_cores': [...]} by probing CPU topology."""
    total = psutil.cpu_count(logical=True) or 0
    physical = psutil.cpu_count(logical=False) or 0
    # 12700K: 8 P-cores × 2 SMT = 16 logicals, + 4 E-cores × 1 = 4, total 20.
    if total == 20 and physical == 12:
        return {"p_cores": list(range(16)), "e_cores": [16, 17, 18, 19]}
    log.warning(
        "unexpected CPU layout (logical=%d physical=%d); assuming first 16 are P-cores",
        total, physical,
    )
    return {
        "p_cores": list(range(min(16, total))),
        "e_cores": list(range(16, total)) if total > 16 else [],
    }


def verify_cuda_compute_capability(expected_major: int = 6) -> None:
    """
    Abort startup if GPU compute capability is not Pascal (6.x).

    int8_float32 is NATIVE-fast on Pascal via DP4A. On Turing (7.5+) and later,
    FP16 paths would be far faster — but the rest of the pipeline is tuned for
    the Pascal path. Fail early rather than silently misconfiguring.
    """
    try:
        import pynvml
    except ImportError:
        log.warning("pynvml not installed; skipping GPU compute-capability check")
        return
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        pynvml.nvmlShutdown()
    except pynvml.NVMLError as exc:
        log.warning("NVML probe failed: %s", exc)
        return
    log.info("GPU: %s  compute capability %d.%d", name, major, minor)
    if major != expected_major:
        raise RuntimeError(
            f"GPU compute capability {major}.{minor} detected; pipeline is tuned for "
            f"Pascal ({expected_major}.x). int8_float32 path may misbehave on a "
            "different architecture — review stage2 before proceeding."
        )
