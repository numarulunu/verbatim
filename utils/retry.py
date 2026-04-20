"""
Retry decorator with exponential-ish backoff.

Wraps transient GPU errors (OOM recoveries, CUDA timeouts) and I/O failures.
Budget and backoff schedule come from config.RETRY_BUDGET / RETRY_BACKOFF_S.
"""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(
    fn: Callable[..., T],
    budget: int | None = None,
    backoff: tuple[int, ...] | None = None,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> Callable[..., T]:
    """Decorator-factory — returns a wrapped fn that retries on transient errors."""
    raise NotImplementedError


def is_transient(exc: BaseException) -> bool:
    """True for CUDA OOM / network / filesystem errors worth retrying."""
    raise NotImplementedError
