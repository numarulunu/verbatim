"""
Retry decorator with backoff.

Wraps transient GPU errors (CUDA OOM recoveries, timeouts) and I/O failures.
Budget and backoff schedule come from config.RETRY_BUDGET / RETRY_BACKOFF_S.
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Callable, TypeVar

from config import RETRY_BACKOFF_S, RETRY_BUDGET

T = TypeVar("T")

log = logging.getLogger(__name__)

# Substring match on str(exc) lowercased. Covers torch, pyannote, urllib, OSError.
_TRANSIENT_SUBSTRINGS = (
    "cuda",
    "cufft",
    "cudnn",
    "out of memory",
    "oom",
    "timeout",
    "timed out",
    "connection reset",
    "temporarily unavailable",
    "resource busy",
    "device or resource busy",
    "broken pipe",
)


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying."""
    msg = str(exc).lower()
    return any(s in msg for s in _TRANSIENT_SUBSTRINGS)


def with_retry(
    fn: Callable[..., T],
    budget: int | None = None,
    backoff: tuple[int, ...] | None = None,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> Callable[..., T]:
    """Decorator-factory — returns a wrapped fn that retries on transient errors."""
    budget = budget if budget is not None else RETRY_BUDGET
    backoff = backoff if backoff is not None else RETRY_BACKOFF_S

    @functools.wraps(fn)
    def wrapped(*args, **kwargs) -> T:
        last_exc: BaseException | None = None
        for attempt in range(budget):
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                if not is_transient(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= budget:
                    break
                sleep_s = backoff[min(attempt, len(backoff) - 1)]
                log.warning(
                    "retry %d/%d in %ds (%s): %s",
                    attempt + 1, budget, sleep_s, type(exc).__name__, exc,
                )
                if on_retry is not None:
                    on_retry(attempt, exc)
                time.sleep(sleep_s)
        assert last_exc is not None
        raise last_exc

    return wrapped
