"""
Quiet-mode utilities with structured logging.

When PIPELINE_QUIET=1, informational print statements across the pipeline
should stay silent so the console only surfaces actionable errors.

All messages are also routed through Python's logging module with timestamps
and severity, written to transcriptor.log alongside the console output.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

# ── Structured logging setup ─────────────────────────────────────────────────

_log_file = Path(__file__).parent.parent / 'transcriptor.log'

_fmt = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')

# File handler: everything goes to transcriptor.log
_file_handler = logging.FileHandler(_log_file, encoding='utf-8')
_file_handler.setFormatter(_fmt)

# Stream handler: only for direct logger.* calls (not quiet_print, which has its own print())
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_fmt)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_file_handler, _stream_handler],
)

logger = logging.getLogger('transcriptor')

# quiet_print routes messages through _quiet_logger (file-only) to avoid
# double console output — quiet_print already handles its own print() calls.
_quiet_logger = logging.getLogger('transcriptor.quiet')
_quiet_logger.propagate = False  # Don't bubble up to root's StreamHandler
_quiet_logger.addHandler(_file_handler)

# Global callback for logging (used by API server)
_log_callback: Optional[Callable[[str, str], None]] = None


def set_log_callback(callback: Optional[Callable[[str, str], None]]) -> None:
    """
    Set a callback function for logging messages.

    Args:
        callback: Function that takes (message: str, level: str) or None to clear
    """
    global _log_callback
    _log_callback = callback


def is_quiet() -> bool:
    """Return True if quiet mode is enabled."""
    return os.environ.get("PIPELINE_QUIET") == "1"


def quiet_print(*args: Any, error: bool = False, **kwargs: Any) -> None:
    """
    Log a message via Python logging and optionally print to console.

    All messages are written to transcriptor.log regardless of quiet mode.
    Console output is suppressed when PIPELINE_QUIET=1 (unless error=True).
    Also calls the log callback if set (for API server web UI).

    Args:
        error: Force printing even in quiet mode (for fatal diagnostics).
    """
    # Format message
    message = ' '.join(str(arg) for arg in args)

    # Determine log level from message content
    level = 'INFO'
    if error or '[ERROR]' in message:
        level = 'ERROR'
    elif '[WARN]' in message or 'Warning:' in message or 'Warning ' in message:
        level = 'WARN'
    elif '[SUCCESS]' in message or '[DONE]' in message or '[COMPLETE]' in message:
        level = 'SUCCESS'

    # Route to Python logging (file only — no StreamHandler to avoid double console output)
    _stripped = message.strip()
    if _stripped:
        if level == 'ERROR':
            _quiet_logger.error(_stripped)
        elif level == 'WARN':
            _quiet_logger.warning(_stripped)
        else:
            _quiet_logger.info(_stripped)

    # Call log callback if set (for API server web UI)
    if _log_callback is not None:
        try:
            _log_callback(message, level)
        except Exception:
            pass  # Don't let callback errors break logging

    # Print to console (gated by quiet mode)
    if error or not is_quiet():
        # Always flush to ensure output appears immediately
        if 'flush' not in kwargs:
            kwargs['flush'] = True
        print(*args, **kwargs)
