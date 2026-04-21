"""
Reporter abstraction: pipeline code calls `reporter.phase_started(...)`,
reporter constructs the matching ipc_protocol event and hands it to a sink.

- NullReporter: pipeline.py in CLI mode — no-op.
- CallbackReporter: daemon wires emit() as the callback; every event lands
  on stdout as a JSON line.

Invariant: every event carries the `id` the reporter was constructed with
(originating command id, from ProcessBatchCommand or RedoBatchCommand).
"""
from __future__ import annotations

from utils.reporter import (
    CallbackReporter,
    NullReporter,
    NULL_REPORTER,
    Reporter,
)
from ipc_protocol import (
    BatchStartedEvent,
    BatchCompleteEvent,
    ErrorEvent,
    FileCompleteEvent,
    FileStartedEvent,
    PhaseCompleteEvent,
    PhaseProgressEvent,
    PhaseStartedEvent,
    WarningEvent,
)


def test_null_reporter_swallows_every_call():
    r = NULL_REPORTER
    # Should be callable without side effects. Repeat to confirm idempotency.
    for _ in range(3):
        r.batch_started(file_count=2, options={"skip_disk_check": True})
        r.file_started(file="x.mp4", index=0, total=2)
        r.phase_started(file_index=0, phase="vad", phase_index=1)
        r.phase_progress(file_index=0, phase="vad", phase_progress=0.5)
        r.phase_complete(file_index=0, phase="vad", elapsed_s=0.1)
        r.file_complete(file_index=0, output_path="out.json", stats={})
        r.batch_complete(total_files=2, successful=2, failed=0,
                         total_elapsed_s=1.0, failures=[])
        r.error(error_type="daemon_crash", message="x")
        r.warning(warning_type="drift_detected", message="y")


def test_null_reporter_is_a_reporter_subclass():
    assert isinstance(NULL_REPORTER, NullReporter)
    assert isinstance(NULL_REPORTER, Reporter)


def test_callback_reporter_routes_events_in_order():
    captured: list = []
    r = CallbackReporter(captured.append, cmd_id="cmd-123")

    r.batch_started(file_count=2, options={"skip_disk_check": True})
    r.file_started(file="x.mp4", index=0, total=2)
    r.phase_started(file_index=0, phase="vad", phase_index=1)
    r.phase_progress(file_index=0, phase="vad", phase_progress=0.5)
    r.phase_complete(file_index=0, phase="vad", elapsed_s=0.1)
    r.file_complete(file_index=0, output_path="out.json", stats={"ok": True})
    r.batch_complete(total_files=2, successful=2, failed=0,
                     total_elapsed_s=1.0, failures=[])

    assert [type(e) for e in captured] == [
        BatchStartedEvent,
        FileStartedEvent,
        PhaseStartedEvent,
        PhaseProgressEvent,
        PhaseCompleteEvent,
        FileCompleteEvent,
        BatchCompleteEvent,
    ]


def test_callback_reporter_auto_fills_cmd_id_on_every_event():
    captured: list = []
    r = CallbackReporter(captured.append, cmd_id="cmd-ABC")

    r.batch_started(file_count=1, options={})
    r.phase_started(file_index=0, phase="asr", phase_index=3)
    r.error(error_type="daemon_crash", message="boom")
    r.warning(warning_type="drift_detected", message="drifted")

    for event in captured:
        assert event.id == "cmd-ABC", f"event {type(event).__name__} lost id"


def test_callback_reporter_without_cmd_id_leaves_id_none():
    captured: list = []
    r = CallbackReporter(captured.append)  # no cmd_id

    r.batch_started(file_count=1, options={})
    assert captured[0].id is None


def test_phase_started_populates_total_phases_from_protocol():
    from ipc_protocol import TOTAL_PHASES
    captured: list = []
    r = CallbackReporter(captured.append)

    r.phase_started(file_index=0, phase="asr", phase_index=3)
    assert captured[0].total_phases == TOTAL_PHASES


def test_error_event_fields_pass_through():
    captured: list = []
    r = CallbackReporter(captured.append, cmd_id="c-1")

    r.error(
        error_type="daemon_crash",
        message="kaboom",
        recoverable=False,
        context={"stage": "stage2"},
        file="abc.mp4",
    )
    evt = captured[0]
    assert isinstance(evt, ErrorEvent)
    assert evt.error_type == "daemon_crash"
    assert evt.message == "kaboom"
    assert evt.recoverable is False
    assert evt.context == {"stage": "stage2"}
    assert evt.file == "abc.mp4"
    assert evt.id == "c-1"


def test_warning_event_fields_pass_through():
    captured: list = []
    r = CallbackReporter(captured.append)
    r.warning(
        warning_type="drift_detected",
        message="0.3 cosine drift on vasquez",
        context={"person_id": "vasquez"},
    )
    evt = captured[0]
    assert isinstance(evt, WarningEvent)
    assert evt.warning_type == "drift_detected"
    assert evt.context == {"person_id": "vasquez"}


def test_callback_raises_do_not_corrupt_reporter_state():
    """A crashing sink must not prevent subsequent calls (operator may
    install a bad sink — pipeline integrity > event delivery)."""

    def flaky(event):
        if isinstance(event, FileStartedEvent):
            raise RuntimeError("sink broke")

    r = CallbackReporter(flaky, cmd_id="x")
    r.batch_started(file_count=1, options={})  # fine
    r.file_started(file="a.mp4", index=0, total=1)  # sink raises, swallowed
    r.batch_complete(total_files=1, successful=1, failed=0,
                     total_elapsed_s=0.1, failures=[])  # fine


def test_reporter_base_is_abstract():
    """The base Reporter should not be instantiable directly — only its
    concrete subclasses have a meaningful on_event."""
    import pytest
    base = Reporter()
    # on_event raises NotImplementedError by default.
    with pytest.raises(NotImplementedError):
        base.batch_started(file_count=0, options={})
