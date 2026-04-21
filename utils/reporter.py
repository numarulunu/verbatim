"""
Pipeline progress reporter.

Pipeline code (stage1/2/3, orchestrator) doesn't know whether it's running
under the CLI or under the Electron daemon. It calls `reporter.phase_started(...)`
and the concrete reporter decides what to do:

- `NullReporter` (CLI): no-op. The existing tqdm / stderr logging stays in
  place for operator feedback.
- `CallbackReporter` (daemon): every call constructs the matching
  `ipc_protocol` event and hands it to the daemon's `emit()` sink, which
  writes it as a JSON line on stdout.

Every reporter instance can be bound to an originating command id; the
bound id is stamped onto every emitted event so the Electron renderer can
correlate progress back to the `ProcessBatchCommand` / `RedoBatchCommand`
that started the batch.

This module has NO dependency on the daemon — `CallbackReporter` takes a
plain `callable(event) -> None`. Pipeline code only ever sees the
`Reporter` interface.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from ipc_protocol import (
    TOTAL_PHASES,
    BatchCompleteEvent,
    BatchStartedEvent,
    ErrorEvent,
    FileCompleteEvent,
    FileStartedEvent,
    PhaseCompleteEvent,
    PhaseProgressEvent,
    PhaseStartedEvent,
    WarningEvent,
)

log = logging.getLogger(__name__)


class Reporter:
    """
    Base class. Pipeline code holds a `Reporter` reference and calls the
    convenience methods below. The default `on_event` raises
    `NotImplementedError`; concrete subclasses override it.
    """

    def __init__(self, cmd_id: str | None = None) -> None:
        self.cmd_id = cmd_id

    def on_event(self, event: Any) -> None:
        raise NotImplementedError(
            "Reporter subclasses must implement on_event(event)"
        )

    # -- event builders -----------------------------------------------------

    def batch_started(self, file_count: int, options: dict[str, Any]) -> None:
        self.on_event(BatchStartedEvent(
            id=self.cmd_id,
            file_count=file_count,
            options=dict(options),
        ))

    def file_started(self, file: str, index: int, total: int) -> None:
        self.on_event(FileStartedEvent(
            id=self.cmd_id,
            file=file,
            index=index,
            total=total,
        ))

    def phase_started(
        self,
        file_index: int,
        phase: str,
        phase_index: int,
    ) -> None:
        self.on_event(PhaseStartedEvent(
            id=self.cmd_id,
            file_index=file_index,
            phase=phase,
            phase_index=phase_index,
            total_phases=TOTAL_PHASES,
        ))

    def phase_progress(
        self,
        file_index: int,
        phase: str,
        phase_progress: float,
    ) -> None:
        self.on_event(PhaseProgressEvent(
            id=self.cmd_id,
            file_index=file_index,
            phase=phase,
            phase_progress=float(phase_progress),
        ))

    def phase_complete(
        self,
        file_index: int,
        phase: str,
        elapsed_s: float,
    ) -> None:
        self.on_event(PhaseCompleteEvent(
            id=self.cmd_id,
            file_index=file_index,
            phase=phase,
            elapsed_s=float(elapsed_s),
        ))

    def file_complete(
        self,
        file_index: int,
        output_path: str,
        stats: dict[str, Any],
    ) -> None:
        self.on_event(FileCompleteEvent(
            id=self.cmd_id,
            file_index=file_index,
            output_path=output_path,
            stats=dict(stats),
        ))

    def batch_complete(
        self,
        total_files: int,
        successful: int,
        failed: int,
        total_elapsed_s: float,
        failures: list[dict[str, Any]],
    ) -> None:
        self.on_event(BatchCompleteEvent(
            id=self.cmd_id,
            total_files=total_files,
            successful=successful,
            failed=failed,
            total_elapsed_s=float(total_elapsed_s),
            failures=list(failures),
        ))

    def error(
        self,
        error_type: str,
        message: str,
        recoverable: bool = False,
        context: dict[str, Any] | None = None,
        file: str | None = None,
    ) -> None:
        self.on_event(ErrorEvent(
            id=self.cmd_id,
            error_type=error_type,
            message=message,
            recoverable=recoverable,
            context=dict(context or {}),
            file=file,
        ))

    def warning(
        self,
        warning_type: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.on_event(WarningEvent(
            id=self.cmd_id,
            warning_type=warning_type,
            message=message,
            context=dict(context or {}),
        ))


class NullReporter(Reporter):
    """No-op reporter. CLI mode uses this so pipeline code can call
    reporter.* unconditionally."""

    def on_event(self, event: Any) -> None:
        pass


# Shared instance so pipeline code can do `reporter or NULL_REPORTER`.
NULL_REPORTER = NullReporter()


class CallbackReporter(Reporter):
    """Routes every event to a callable sink. The daemon passes its
    `emit(event)` here; tests pass a list.append to capture events in
    order.

    A sink that raises is logged and swallowed — pipeline code must never
    fail because telemetry failed.
    """

    def __init__(
        self,
        callback: Callable[[Any], None],
        cmd_id: str | None = None,
    ) -> None:
        super().__init__(cmd_id=cmd_id)
        self._callback = callback

    def on_event(self, event: Any) -> None:
        try:
            self._callback(event)
        except Exception:  # noqa: BLE001 — telemetry must never fail pipeline
            log.exception("reporter callback raised on %r", event)
