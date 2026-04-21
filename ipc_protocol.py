"""
Verbatim engine daemon IPC protocol.

Line-delimited JSON over stdin/stdout. This module is the single source of
truth for command + event shapes.

- Python side uses the dataclasses below directly.
- Electron side consumes `verbatim/ipc-protocol.json`, generated
  by running `python ipc_protocol.py` at the repo root.

Commands flow Electron → Python (stdin). Events flow Python → Electron
(stdout). Every event produced by a command handler carries the originating
command's `id` for correlation. Spontaneous events (`ready`, `shutting_down`)
have no `id`.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Enums (exported to JS side via export_schema)
# ---------------------------------------------------------------------------

PHASE_NAMES: tuple[str, ...] = (
    "isolation", "vad", "decode", "asr", "alignment",
    "diarization", "identification", "verification",
    "polish", "corpus_update",
)
TOTAL_PHASES = len(PHASE_NAMES)

ERROR_TYPES: tuple[str, ...] = (
    "audio_corrupt",
    "hf_token_missing",
    "gpu_oom",
    "claude_api_rate_limited",
    "claude_cli_not_found",
    "disk_full",
    "voiceprint_collision",
    "diarization_3rd_speaker",
    "polish_schema_drift",
    "daemon_crash",
    "engine_lock_held",
    "unknown_command",
    "invalid_command_payload",
    "ffmpeg_missing",
)

WARNING_TYPES: tuple[str, ...] = (
    "low_confidence_bootstrap",
    "drift_detected",
    "overlap_high",
    "language_mismatch",
)


# ---------------------------------------------------------------------------
# Commands (Electron -> Python, on stdin)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PingCommand:
    id: str | None = None
    cmd: str = "ping"


@dataclass(frozen=True)
class ShutdownCommand:
    # No `id` — this is the terminal command.
    cmd: str = "shutdown"


@dataclass(frozen=True)
class DetectCommand:
    id: str | None = None
    cmd: str = "detect"


@dataclass(frozen=True)
class ListPersonsCommand:
    id: str | None = None
    cmd: str = "list_persons"


@dataclass(frozen=True)
class RegisterPersonCommand:
    id: str | None = None
    person: dict[str, Any] = field(default_factory=dict)
    cmd: str = "register_person"


@dataclass(frozen=True)
class InspectPersonCommand:
    id: str | None = None
    person_id: str = ""
    cmd: str = "inspect_person"


@dataclass(frozen=True)
class EditPersonCommand:
    id: str | None = None
    person_id: str = ""
    updates: dict[str, Any] = field(default_factory=dict)
    cmd: str = "edit_person"


@dataclass(frozen=True)
class RenamePersonCommand:
    id: str | None = None
    old_id: str = ""
    new_id: str = ""
    cmd: str = "rename_person"


@dataclass(frozen=True)
class MergePersonsCommand:
    id: str | None = None
    source_id: str = ""
    target_id: str = ""
    cmd: str = "merge_persons"


@dataclass(frozen=True)
class ScanFilesCommand:
    id: str | None = None
    input_dir: str = ""
    probe_duration: bool = True
    cmd: str = "scan_files"


@dataclass(frozen=True)
class ProcessBatchCommand:
    id: str | None = None
    files: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    cmd: str = "process_batch"


@dataclass(frozen=True)
class RedoBatchCommand:
    id: str | None = None
    filter: dict[str, Any] = field(default_factory=dict)
    cmd: str = "redo_batch"


@dataclass(frozen=True)
class CancelBatchCommand:
    id: str | None = None
    cmd: str = "cancel_batch"


@dataclass(frozen=True)
class GetCorpusSummaryCommand:
    id: str | None = None
    cmd: str = "get_corpus_summary"


_COMMANDS: dict[str, type] = {
    "ping": PingCommand,
    "shutdown": ShutdownCommand,
    "detect": DetectCommand,
    "list_persons": ListPersonsCommand,
    "register_person": RegisterPersonCommand,
    "inspect_person": InspectPersonCommand,
    "edit_person": EditPersonCommand,
    "rename_person": RenamePersonCommand,
    "merge_persons": MergePersonsCommand,
    "scan_files": ScanFilesCommand,
    "process_batch": ProcessBatchCommand,
    "redo_batch": RedoBatchCommand,
    "cancel_batch": CancelBatchCommand,
    "get_corpus_summary": GetCorpusSummaryCommand,
}


class UnknownCommand(ValueError):
    """Raised when parse_command sees a cmd string not in the registry."""


class InvalidCommand(ValueError):
    """Raised when parse_command's JSON payload is malformed or has unknown fields."""


def parse_command(line: str | bytes):
    """Parse one newline-terminated JSON line into the corresponding Command dataclass."""
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    line = line.strip()
    if not line:
        raise InvalidCommand("empty line")
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise InvalidCommand(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidCommand(
            f"command must be a JSON object; got {type(data).__name__}"
        )
    cmd_name = data.get("cmd")
    if not isinstance(cmd_name, str):
        raise InvalidCommand("command missing required `cmd` field")
    cls = _COMMANDS.get(cmd_name)
    if cls is None:
        raise UnknownCommand(cmd_name)
    kwargs = {k: v for k, v in data.items() if k != "cmd"}
    valid_fields = {f.name for f in fields(cls)}
    unknown = set(kwargs) - valid_fields
    if unknown:
        raise InvalidCommand(
            f"{cmd_name}: unknown fields {sorted(unknown)}"
        )
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise InvalidCommand(f"{cmd_name} payload invalid: {exc}") from exc


# ---------------------------------------------------------------------------
# Events (Python -> Electron, on stdout)
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    """UTC ISO-8601 with millisecond precision, 'Z' suffix."""
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# Lifecycle

@dataclass(frozen=True)
class ReadyEvent:
    engine_version: str = ""
    models_loaded: list[str] = field(default_factory=list)
    timestamp: str | None = None
    id: str | None = None  # spontaneous — always None
    type: str = "ready"


@dataclass(frozen=True)
class PongEvent:
    id: str | None = None
    timestamp: str | None = None
    type: str = "pong"


@dataclass(frozen=True)
class ShuttingDownEvent:
    timestamp: str | None = None
    id: str | None = None
    type: str = "shutting_down"


@dataclass(frozen=True)
class CancelAcceptedEvent:
    id: str | None = None
    timestamp: str | None = None
    type: str = "cancel_accepted"


# Detect

@dataclass(frozen=True)
class SystemInfoEvent:
    id: str | None = None
    cpu: dict[str, Any] = field(default_factory=dict)
    gpu: dict[str, Any] = field(default_factory=dict)
    cuda: bool = False
    hf_token: bool = False
    anthropic_api_key: bool = False
    disk_free_gb: float = 0.0
    timestamp: str | None = None
    type: str = "system_info"


# Person management

@dataclass(frozen=True)
class PersonsListedEvent:
    id: str | None = None
    persons: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str | None = None
    type: str = "persons_listed"


@dataclass(frozen=True)
class PersonRegisteredEvent:
    id: str | None = None
    person_id: str = ""
    record: dict[str, Any] = field(default_factory=dict)
    timestamp: str | None = None
    type: str = "person_registered"


@dataclass(frozen=True)
class PersonInspectedEvent:
    id: str | None = None
    person: dict[str, Any] = field(default_factory=dict)
    voiceprint_files: list[str] = field(default_factory=list)
    timestamp: str | None = None
    type: str = "person_inspected"


@dataclass(frozen=True)
class PersonRenamedEvent:
    id: str | None = None
    old_id: str = ""
    new_id: str = ""
    timestamp: str | None = None
    type: str = "person_renamed"


@dataclass(frozen=True)
class PersonMergedEvent:
    id: str | None = None
    source_id: str = ""
    target_id: str = ""
    timestamp: str | None = None
    type: str = "person_merged"


@dataclass(frozen=True)
class CollisionDetectedEvent:
    id: str | None = None
    pair: list[str] = field(default_factory=list)  # [id_a, id_b]
    cosine: float = 0.0
    timestamp: str | None = None
    type: str = "collision_detected"


# Scan

@dataclass(frozen=True)
class FilesScannedEvent:
    id: str | None = None
    files: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str | None = None
    type: str = "files_scanned"


# Batch processing

@dataclass(frozen=True)
class BatchStartedEvent:
    id: str | None = None
    file_count: int = 0
    options: dict[str, Any] = field(default_factory=dict)
    timestamp: str | None = None
    type: str = "batch_started"


@dataclass(frozen=True)
class FileStartedEvent:
    id: str | None = None
    file: str = ""
    index: int = 0
    total: int = 0
    timestamp: str | None = None
    type: str = "file_started"


@dataclass(frozen=True)
class PhaseStartedEvent:
    id: str | None = None
    file_index: int = 0
    phase: str = ""
    phase_index: int = 0
    total_phases: int = TOTAL_PHASES
    timestamp: str | None = None
    type: str = "phase_started"


@dataclass(frozen=True)
class PhaseProgressEvent:
    id: str | None = None
    file_index: int = 0
    phase: str = ""
    phase_progress: float = 0.0  # 0..1
    timestamp: str | None = None
    type: str = "phase_progress"


@dataclass(frozen=True)
class PhaseCompleteEvent:
    id: str | None = None
    file_index: int = 0
    phase: str = ""
    elapsed_s: float = 0.0
    timestamp: str | None = None
    type: str = "phase_complete"


@dataclass(frozen=True)
class FileCompleteEvent:
    id: str | None = None
    file_index: int = 0
    output_path: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    timestamp: str | None = None
    type: str = "file_complete"


@dataclass(frozen=True)
class BatchCompleteEvent:
    id: str | None = None
    total_files: int = 0
    successful: int = 0
    failed: int = 0
    total_elapsed_s: float = 0.0
    failures: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str | None = None
    type: str = "batch_complete"


# Corpus summary

@dataclass(frozen=True)
class CorpusSummaryEvent:
    id: str | None = None
    session_count: int = 0
    persons: dict[str, Any] = field(default_factory=dict)
    total_hours: float = 0.0
    timestamp: str | None = None
    type: str = "corpus_summary"


# Diagnostics

@dataclass(frozen=True)
class ErrorEvent:
    error_type: str = ""
    message: str = ""
    recoverable: bool = False
    id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    file: str | None = None
    timestamp: str | None = None
    type: str = "error"


@dataclass(frozen=True)
class WarningEvent:
    warning_type: str = ""
    message: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    timestamp: str | None = None
    type: str = "warning"


_EVENTS: tuple[type, ...] = (
    ReadyEvent, PongEvent, ShuttingDownEvent, CancelAcceptedEvent,
    SystemInfoEvent,
    PersonsListedEvent, PersonRegisteredEvent, PersonInspectedEvent,
    PersonRenamedEvent, PersonMergedEvent, CollisionDetectedEvent,
    FilesScannedEvent,
    BatchStartedEvent, FileStartedEvent,
    PhaseStartedEvent, PhaseProgressEvent, PhaseCompleteEvent,
    FileCompleteEvent, BatchCompleteEvent,
    CorpusSummaryEvent,
    ErrorEvent, WarningEvent,
)


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

def encode_event(event) -> str:
    """
    Serialize a frozen-dataclass event to a JSON line terminated with '\\n'.

    Auto-fills `timestamp` with UTC now if not set on the event.
    """
    d = asdict(event)
    if d.get("timestamp") is None:
        d["timestamp"] = _utcnow_iso()
    # Drop id=None for spontaneous events to keep wire shape compact.
    if d.get("id") is None:
        d.pop("id", None)
    return json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n"


# ---------------------------------------------------------------------------
# Schema export (for the Electron side)
# ---------------------------------------------------------------------------

def _schema_for_class(cls) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(cls):
        type_name = getattr(f.type, "__name__", None)
        if type_name is None:
            type_name = str(f.type)
        entry: dict[str, Any] = {"type": type_name}
        if f.default is not f.default_factory and f.default is not _MISSING:
            entry["default"] = f.default
        out[f.name] = entry
    return out


# dataclasses._MISSING sentinel — import indirectly because it's private.
from dataclasses import MISSING as _MISSING  # noqa: E402


def export_schema() -> dict[str, Any]:
    """
    Return the protocol spec as a plain dict suitable for JSON export.
    Electron side loads this at build time as `ipc-protocol.json`.
    """
    return {
        "protocol_version": PROTOCOL_VERSION,
        "phase_names": list(PHASE_NAMES),
        "total_phases": TOTAL_PHASES,
        "error_types": list(ERROR_TYPES),
        "warning_types": list(WARNING_TYPES),
        "commands": {
            name: _schema_for_class(cls) for name, cls in _COMMANDS.items()
        },
        "events": {
            # Each event type's discriminator is the default of `type` field.
            next(f.default for f in fields(cls) if f.name == "type"): _schema_for_class(cls)
            for cls in _EVENTS
        },
    }


def write_schema(path: Path) -> None:
    """Write `export_schema()` as pretty JSON to `path`."""
    payload = json.dumps(export_schema(), indent=2, ensure_ascii=False, default=str)
    path.write_text(payload + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI — `python ipc_protocol.py [output_path]`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        out_path = Path(sys.argv[1])
    else:
        out_path = Path(__file__).resolve().parent / "verbatim" / "ipc-protocol.json"
    write_schema(out_path)
    print(f"wrote protocol schema to {out_path}", file=sys.stderr)
