"""
Shared cancellation signal for cooperative pipeline cancellation.

The daemon's `cancel_batch` handler calls `request_cancel()`. Pipeline code
(stage1/stage2/stage3) calls `cancel_check()` at phase boundaries; when the
flag is set, it raises `CancelledError` which propagates up to the per-file
loop and becomes a failure entry in `batch_complete`.

Why a `threading.Event` and not `asyncio.Event`: pipeline work runs inside
`asyncio.to_thread(...)` blocks. Threaded code can't poll an asyncio.Event
without a loop reference, but `threading.Event` is thread-safe by
construction. Events in the asyncio layer are fine to set via the same
module.
"""
from __future__ import annotations

import threading

_flag = threading.Event()


class CancelledError(Exception):
    """Raised by `cancel_check()` when a batch-level cancel has been requested."""


def request_cancel() -> None:
    """Set the cancellation flag. Called by the daemon's cancel_batch handler."""
    _flag.set()


def reset() -> None:
    """Clear the cancellation flag. Called at the start of every new batch."""
    _flag.clear()


def cancelled() -> bool:
    """Non-raising predicate for callers that want to check without branching on exceptions."""
    return _flag.is_set()


def cancel_check() -> None:
    """Raise CancelledError if a cancel has been requested; return cleanly otherwise."""
    if _flag.is_set():
        raise CancelledError("batch cancelled by user")
