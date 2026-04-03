"""
Quiet-mode utilities.

When PIPELINE_QUIET=1, informational print statements across the pipeline
should stay silent so the console only surfaces actionable errors.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

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
    Print unless quiet mode is active. Also calls log callback if set.

    Args:
        error: Force printing even in quiet mode (for fatal diagnostics).
    """
    # Format message
    message = ' '.join(str(arg) for arg in args)

    # Determine log level from message prefix
    level = 'INFO'
    if error or '[ERROR]' in message:
        level = 'ERROR'
    elif '[WARN]' in message or 'Warning:' in message:
        level = 'WARN'
    elif '[SUCCESS]' in message or '[DONE]' in message or '[COMPLETE]' in message:
        level = 'SUCCESS'

    # Call log callback if set (for API server web UI)
    if _log_callback is not None:
        try:
            _log_callback(message, level)
        except:
            pass  # Don't let callback errors break logging

    # Print to console
    if error or not is_quiet():
        # Always flush to ensure output appears immediately
        if 'flush' not in kwargs:
            kwargs['flush'] = True
        print(*args, **kwargs)
