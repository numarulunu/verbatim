"""
Hardware-specific process controls for Windows + i7-12700K.

Pins the current process (and therefore every child it spawns) to logical
P-cores 0-15. E-cores (16-19) are left idle for OS background work — they're
too slow for audio decoding and would stall the ProcessPool's critical path.

FFmpeg children inherit affinity, so pinning the orchestrator propagates to
every decode worker automatically.
"""
from __future__ import annotations


def pin_to_p_cores() -> None:
    """Set the current process's CPU affinity to P-cores only (logicals 0-15)."""
    raise NotImplementedError


def detect_physical_layout() -> dict[str, list[int]]:
    """Return {'p_cores': [...], 'e_cores': [...]} for this host. Logs warning on non-12700K."""
    raise NotImplementedError


def verify_cuda_compute_capability(expected_major: int = 6) -> None:
    """Abort startup if GPU compute capability is not Pascal (6.x). Guards against FP16 gimping."""
    raise NotImplementedError
