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

import asyncio
import logging
import sys
import traceback
from pathlib import Path

# NOTE: the daemon must configure stdout buffering BEFORE it emits anything.
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

from ipc_protocol import (
    CancelBatchCommand,
    DetectCommand,
    EditPersonCommand,
    ErrorEvent,
    GetCorpusSummaryCommand,
    InspectPersonCommand,
    InvalidCommand,
    ListPersonsCommand,
    MergePersonsCommand,
    PingCommand,
    PongEvent,
    ProcessBatchCommand,
    ReadyEvent,
    RedoBatchCommand,
    RegisterPersonCommand,
    RenamePersonCommand,
    ScanFilesCommand,
    ShutdownCommand,
    ShuttingDownEvent,
    UnknownCommand,
    encode_event,
    parse_command,
)
import handlers
from utils import cancellation
from utils import engine_lock

# Keep these importable without loading config (which initialises dirs).
# Real preflight wiring lands with the batch-handler sub-gate.

ENGINE_VERSION = "1.0.0"  # will move to config.ENGINE_VERSION once preflight lands


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

_SIMPLE_HANDLERS = {
    DetectCommand: handlers.handle_detect,
    ListPersonsCommand: handlers.handle_list_persons,
    RegisterPersonCommand: handlers.handle_register_person,
    InspectPersonCommand: handlers.handle_inspect_person,
    EditPersonCommand: handlers.handle_edit_person,
    RenamePersonCommand: handlers.handle_rename_person,
    MergePersonsCommand: handlers.handle_merge_persons,
    ScanFilesCommand: handlers.handle_scan_files,
    GetCorpusSummaryCommand: handlers.handle_get_corpus_summary,
    CancelBatchCommand: handlers.handle_cancel_batch,
}


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

        handler = _SIMPLE_HANDLERS.get(type(cmd))
        if handler is not None:
            handler(cmd, emit)
            return True

        # ProcessBatch / RedoBatch are handled asynchronously in `_amain`
        # before `_handle` is invoked. Reaching this branch for them would
        # mean a wiring regression.
        emit(ErrorEvent(
            id=getattr(cmd, "id", None),
            error_type="unknown_command",
            message=f"no dispatcher entry for {type(cmd).__name__}",
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


async def _aread_line() -> str:
    """Read one line from stdin without blocking the event loop.

    asyncio.connect_read_pipe on Windows + sys.stdin is finicky; the thread
    handoff is boring and works everywhere. We spend ~zero wall-clock time
    in the worker (just waits on a syscall) so thread-pool exhaustion isn't
    a concern.
    """
    return await asyncio.to_thread(sys.stdin.readline)


async def _cancel_active_batch(task: asyncio.Task | None, timeout_s: float = 30.0) -> None:
    """Signal an active batch to stop and wait for it to finish.

    Called on shutdown / EOF. The pipeline observes the cancellation flag
    at phase boundaries; if it doesn't return within `timeout_s` we hard-
    cancel the asyncio task as a last resort.
    """
    if task is None or task.done():
        return
    cancellation.request_cancel()
    try:
        await asyncio.wait_for(task, timeout=timeout_s)
    except asyncio.TimeoutError:
        log.warning("batch task did not stop within %.0fs; cancelling", timeout_s)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


# Single-slot holder for the in-flight batch task. At most one batch runs
# at a time. `None` when idle. The read loop populates this on
# process_batch / redo_batch and drains it on shutdown / EOF / SIGINT.
_active_batch: asyncio.Task | None = None


def _on_batch_done(task: asyncio.Task) -> None:
    """Clear the active-batch slot and log any unhandled exception."""
    global _active_batch
    _active_batch = None
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.exception("batch task raised", exc_info=exc)


async def _amain() -> int:
    global _active_batch

    _configure_logging()
    log.info("daemon starting (engine_version=%s)", ENGINE_VERSION)

    try:
        lock_handle = engine_lock.acquire(engine_version=ENGINE_VERSION)
    except engine_lock.EngineLockHeld as exc:
        # Another daemon already owns `_voiceprints/`. Emit a structured
        # error so the Electron wrapper can surface it, then exit non-zero.
        emit(ErrorEvent(
            error_type="engine_lock_held",
            message=str(exc),
            recoverable=False,
        ))
        return 3

    emit(ReadyEvent(engine_version=ENGINE_VERSION, models_loaded=[]))

    try:
        while True:
            raw = await _aread_line()
            if not raw:
                # EOF — graceful close.
                log.info("stdin closed; shutting down")
                await _cancel_active_batch(_active_batch)
                emit(ShuttingDownEvent())
                return 0
            if not raw.strip():
                continue
            cmd = _read_command(raw)
            if cmd is None:
                continue

            if isinstance(cmd, ShutdownCommand):
                log.info("shutdown command received")
                await _cancel_active_batch(_active_batch)
                emit(ShuttingDownEvent())
                return 0

            if isinstance(cmd, (ProcessBatchCommand, RedoBatchCommand)):
                if _active_batch is not None and not _active_batch.done():
                    emit(ErrorEvent(
                        id=getattr(cmd, "id", None),
                        error_type="invalid_command_payload",
                        message="a batch is already running; send cancel_batch first",
                        recoverable=True,
                    ))
                    continue
                coro = (
                    handlers.async_handle_process_batch(cmd, emit)
                    if isinstance(cmd, ProcessBatchCommand)
                    else handlers.async_handle_redo_batch(cmd, emit)
                )
                _active_batch = asyncio.create_task(coro)
                _active_batch.add_done_callback(_on_batch_done)
                continue

            # Synchronous dispatch for every other command. Sync commands
            # are cheap (list_persons etc. — no IO latency to speak of);
            # the blocking stdin read is the only truly slow primitive
            # and it's already behind asyncio.to_thread.
            _handle(cmd)

    except KeyboardInterrupt:
        log.info("SIGINT received")
        cancellation.request_cancel()
        await _cancel_active_batch(_active_batch)
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

    finally:
        engine_lock.release(lock_handle)


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
