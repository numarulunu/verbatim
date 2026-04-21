"""
Vocality engine daemon — stdin/stdout JSON entry point.

GATE 4 SCAFFOLD. Only handles `ping` and `shutdown`; responds to every other
command with an `unknown_command` error event. Gates 5+ add the real
handlers (person management, process_batch, redo_batch, etc.) on top of
this skeleton.

Design invariants (Gate 2):
- Line-buffered stdout so JSON events land at the receiver promptly.
- Stderr for logs + tracebacks; never mixed with events on stdout.
- Emits a spontaneous `ready` event on startup.
- Clean shutdown on stdin EOF OR on `shutdown` command: emits
  `shutting_down`, breaks the read loop, exits 0.
- Uncaught exception: emits `error(daemon_crash)` then exits 2.

For Gate 4 the read loop is synchronous — `for line in sys.stdin`. Gate 5
converts it to asyncio so `cancel_batch` can interrupt in-flight
`process_batch` work.
"""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

# NOTE: the daemon must configure stdout buffering BEFORE it emits anything.
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

from ipc_protocol import (
    CancelAcceptedEvent,
    ErrorEvent,
    InvalidCommand,
    PingCommand,
    PongEvent,
    ReadyEvent,
    ShutdownCommand,
    ShuttingDownEvent,
    UnknownCommand,
    encode_event,
    parse_command,
)
from utils import cancellation

# Keep these importable without loading config (which initialises dirs).
# We'll wire real lock + preflight in Gate 5.

ENGINE_VERSION = "1.0.0"  # will move to config.ENGINE_VERSION in Gate 5


# ---------------------------------------------------------------------------
# Logging — stderr only. File handler lands in Gate 5 (needs LOG_DIR from config).
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def _configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Clear any prior handlers (e.g., from pytest) to keep stderr clean.
    root.handlers.clear()
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(stream)


log = logging.getLogger("vocality.daemon")


# ---------------------------------------------------------------------------
# Emit helper
# ---------------------------------------------------------------------------

def emit(event) -> None:
    """Write an event as a JSON line to stdout."""
    sys.stdout.write(encode_event(event))
    # line_buffering=True flushes on '\n', but be explicit anyway so
    # external callers that pipe through non-line-buffered transports
    # still see events promptly.
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle(cmd) -> bool:
    """
    Dispatch one command. Returns False if the loop should exit (shutdown),
    True to keep running. Never raises — handler failures become error events.
    """
    try:
        if isinstance(cmd, PingCommand):
            emit(PongEvent(id=cmd.id))
            return True

        if isinstance(cmd, ShutdownCommand):
            log.info("shutdown command received")
            emit(ShuttingDownEvent())
            return False

        # Gate 4: every other command is "not implemented yet". Gate 5 replaces
        # these stubs with real handlers.
        emit(ErrorEvent(
            id=getattr(cmd, "id", None),
            error_type="unknown_command",
            message=f"command {type(cmd).__name__} not implemented in Gate 4",
            recoverable=True,
            context={"cmd": getattr(cmd, "cmd", None)},
        ))
        return True

    except Exception as exc:  # noqa: BLE001 — handler boundary must never kill the daemon
        log.exception("handler failure on %r", cmd)
        emit(ErrorEvent(
            id=getattr(cmd, "id", None),
            error_type="daemon_crash",
            message=f"handler raised {type(exc).__name__}: {exc}",
            recoverable=False,
        ))
        return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _read_command(line: str):
    """Parse a stdin line into a Command, or emit an error and return None."""
    try:
        return parse_command(line)
    except UnknownCommand as exc:
        emit(ErrorEvent(
            error_type="unknown_command",
            message=f"unknown command: {exc.args[0]!r}",
            recoverable=True,
        ))
    except InvalidCommand as exc:
        emit(ErrorEvent(
            error_type="invalid_command_payload",
            message=str(exc),
            recoverable=True,
        ))
    return None


def main() -> int:
    _configure_logging()
    log.info("daemon starting (engine_version=%s)", ENGINE_VERSION)

    emit(ReadyEvent(engine_version=ENGINE_VERSION, models_loaded=[]))

    try:
        for raw in sys.stdin:
            if not raw.strip():
                continue
            cmd = _read_command(raw)
            if cmd is None:
                continue
            keep_going = _handle(cmd)
            if not keep_going:
                return 0
        # EOF reached without an explicit shutdown — treat as graceful close.
        log.info("stdin closed; shutting down")
        emit(ShuttingDownEvent())
        return 0

    except KeyboardInterrupt:
        log.info("SIGINT received")
        cancellation.request_cancel()
        emit(ShuttingDownEvent())
        return 0

    except Exception as exc:  # noqa: BLE001 — top-level safety net
        log.exception("uncaught exception in main loop")
        emit(ErrorEvent(
            error_type="daemon_crash",
            message=f"{type(exc).__name__}: {exc}",
            recoverable=False,
            context={"traceback_head": traceback.format_exc().splitlines()[-6:]},
        ))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
