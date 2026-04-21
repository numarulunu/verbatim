"""
Daemon command handlers — Gate 5C low-risk surface.

Each handler is a pure function `(cmd, emit) -> None` that:
- does the requested work by calling existing persons.*/corpus/* modules
- emits exactly one response event via the injected `emit(event)` callable
- catches its own exceptions and converts them into an `ErrorEvent` so the
  daemon never dies from a handler failure

Batch handlers (process_batch / redo_batch / cancel_batch's real work) live
in Gate 5D; this module covers the non-pipeline commands only.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from ipc_protocol import (
    CancelAcceptedEvent,
    CorpusSummaryEvent,
    ErrorEvent,
    FilesScannedEvent,
    PersonInspectedEvent,
    PersonMergedEvent,
    PersonRegisteredEvent,
    PersonRenamedEvent,
    PersonsListedEvent,
    SystemInfoEvent,
)
from utils import cancellation

log = logging.getLogger(__name__)

Emit = Callable[[Any], None]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _emit_error(
    emit: Emit,
    cmd_id: str | None,
    error_type: str,
    message: str,
    recoverable: bool = True,
    context: dict | None = None,
) -> None:
    emit(ErrorEvent(
        id=cmd_id,
        error_type=error_type,
        message=message,
        recoverable=recoverable,
        context=dict(context or {}),
    ))


def _person_to_dict(record) -> dict:
    from persons.schema import to_dict
    return to_dict(record)


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def handle_detect(cmd, emit: Emit) -> None:
    """Report system capabilities: CPU, GPU, CUDA, HF+Anthropic presence,
    free disk on the voiceprint drive."""
    import platform

    cpu_info: dict[str, Any] = {
        "name": platform.processor() or platform.machine(),
        "logical_cores": os.cpu_count() or 0,
    }
    try:
        import psutil
        cpu_info["physical_cores"] = psutil.cpu_count(logical=False) or 0
    except Exception:  # noqa: BLE001 — psutil optional here
        cpu_info["physical_cores"] = 0

    gpu_info: dict[str, Any] = {}
    cuda_available = False
    try:
        import torch
        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            gpu_info = {
                "name": torch.cuda.get_device_name(0),
                "total_memory_gb": round(
                    torch.cuda.get_device_properties(0).total_memory / 1e9, 1
                ),
            }
    except Exception as exc:  # noqa: BLE001 — torch may be absent on pure-dev machines
        log.debug("detect: torch probe failed (%s)", exc)

    hf_token = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN"))
    anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    disk_free_gb = 0.0
    try:
        from config import VOICEPRINT_DIR
        target = Path(VOICEPRINT_DIR)
        target.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(target)
        disk_free_gb = round(usage.free / 1e9, 2)
    except Exception as exc:  # noqa: BLE001
        log.debug("detect: disk probe failed (%s)", exc)

    emit(SystemInfoEvent(
        id=cmd.id,
        cpu=cpu_info,
        gpu=gpu_info,
        cuda=cuda_available,
        hf_token=hf_token,
        anthropic_api_key=anthropic_key,
        disk_free_gb=disk_free_gb,
    ))


# ---------------------------------------------------------------------------
# list_persons
# ---------------------------------------------------------------------------

def handle_list_persons(cmd, emit: Emit) -> None:
    from persons import registry
    try:
        records = registry.list_all()
    except Exception as exc:  # noqa: BLE001
        log.exception("list_persons failed")
        _emit_error(emit, cmd.id, "daemon_crash", f"list_persons: {exc}")
        return
    emit(PersonsListedEvent(
        id=cmd.id,
        persons=[_person_to_dict(r) for r in records],
    ))


# ---------------------------------------------------------------------------
# register_person
# ---------------------------------------------------------------------------

def handle_register_person(cmd, emit: Emit) -> None:
    from persons import registry

    payload = dict(cmd.person or {})
    id_ = payload.get("id")
    display_name = payload.get("display_name")
    default_role = payload.get("default_role", "student")
    if not id_ or not display_name:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            "register_person requires `id` and `display_name`",
        )
        return
    try:
        record = registry.register_new(
            id_=id_,
            display_name=display_name,
            default_role=default_role,
            disambiguator=payload.get("disambiguator"),
            voice_type=payload.get("voice_type"),
            fach=payload.get("fach"),
            first_seen=payload.get("first_seen"),
        )
    except registry.DuplicateDisplayNameError as exc:
        _emit_error(emit, cmd.id, "invalid_command_payload", str(exc))
        return
    except ValueError as exc:
        _emit_error(emit, cmd.id, "invalid_command_payload", str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("register_person failed")
        _emit_error(emit, cmd.id, "daemon_crash", str(exc))
        return

    emit(PersonRegisteredEvent(
        id=cmd.id,
        person_id=record.id,
        record=_person_to_dict(record),
    ))


# ---------------------------------------------------------------------------
# inspect_person
# ---------------------------------------------------------------------------

_EDITABLE_FIELDS = frozenset({
    "display_name",
    "disambiguator",
    "default_role",
    "voice_type",
    "fach",
})


def handle_inspect_person(cmd, emit: Emit) -> None:
    from persons import registry

    if not cmd.person_id:
        _emit_error(emit, cmd.id, "invalid_command_payload", "person_id required")
        return
    try:
        record = registry.load(cmd.person_id)
    except registry.PersonNotFoundError:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            f"person not found: {cmd.person_id!r}",
        )
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("inspect_person failed")
        _emit_error(emit, cmd.id, "daemon_crash", str(exc))
        return

    pdir = registry.person_dir(record.id)
    files: list[str] = []
    if pdir.exists():
        for p in sorted(pdir.iterdir()):
            if p.suffix == ".npy":
                files.append(p.name)

    emit(PersonInspectedEvent(
        id=cmd.id,
        person=_person_to_dict(record),
        voiceprint_files=files,
    ))


# ---------------------------------------------------------------------------
# edit_person
# ---------------------------------------------------------------------------

def handle_edit_person(cmd, emit: Emit) -> None:
    from persons import registry

    if not cmd.person_id:
        _emit_error(emit, cmd.id, "invalid_command_payload", "person_id required")
        return
    updates = dict(cmd.updates or {})
    unknown = set(updates) - _EDITABLE_FIELDS
    if unknown:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            f"edit_person: unknown / immutable fields {sorted(unknown)}; "
            f"id rename goes through rename_person",
        )
        return
    try:
        record = registry.load(cmd.person_id)
    except registry.PersonNotFoundError:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            f"person not found: {cmd.person_id!r}",
        )
        return

    for key, value in updates.items():
        setattr(record, key, value)
    try:
        registry.save(record)
    except Exception as exc:  # noqa: BLE001
        log.exception("edit_person save failed")
        _emit_error(emit, cmd.id, "daemon_crash", str(exc))
        return

    emit(PersonInspectedEvent(
        id=cmd.id,
        person=_person_to_dict(record),
        voiceprint_files=[
            p.name for p in sorted(registry.person_dir(record.id).iterdir())
            if p.suffix == ".npy"
        ] if registry.person_dir(record.id).exists() else [],
    ))


# ---------------------------------------------------------------------------
# rename_person
# ---------------------------------------------------------------------------

def handle_rename_person(cmd, emit: Emit) -> None:
    from persons import registry

    if not cmd.old_id or not cmd.new_id:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            "rename_person requires both `old_id` and `new_id`",
        )
        return
    try:
        registry.rename(cmd.old_id, cmd.new_id)
    except registry.PersonNotFoundError:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            f"person not found: {cmd.old_id!r}",
        )
        return
    except ValueError as exc:
        _emit_error(emit, cmd.id, "invalid_command_payload", str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("rename_person failed")
        _emit_error(emit, cmd.id, "daemon_crash", str(exc))
        return

    emit(PersonRenamedEvent(
        id=cmd.id,
        old_id=cmd.old_id,
        new_id=cmd.new_id,
    ))


# ---------------------------------------------------------------------------
# merge_persons
# ---------------------------------------------------------------------------

def handle_merge_persons(cmd, emit: Emit) -> None:
    from persons import registry

    if not cmd.source_id or not cmd.target_id:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            "merge_persons requires both `source_id` and `target_id`",
        )
        return
    if cmd.source_id == cmd.target_id:
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            "source_id and target_id must differ",
        )
        return
    try:
        registry.merge(cmd.source_id, cmd.target_id, keep=cmd.target_id)
    except registry.PersonNotFoundError as exc:
        _emit_error(emit, cmd.id, "invalid_command_payload", str(exc))
        return
    except ValueError as exc:
        _emit_error(emit, cmd.id, "invalid_command_payload", str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("merge_persons failed")
        _emit_error(emit, cmd.id, "daemon_crash", str(exc))
        return

    emit(PersonMergedEvent(
        id=cmd.id,
        source_id=cmd.source_id,
        target_id=cmd.target_id,
    ))


# ---------------------------------------------------------------------------
# scan_files
# ---------------------------------------------------------------------------

_AUDIO_EXTS = (".mp4", ".m4a", ".mp3", ".wav", ".webm", ".flac", ".ogg")


def _probe_duration(path: Path) -> float | None:
    try:
        import subprocess
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
        return float(out.strip())
    except Exception:  # noqa: BLE001 — ffprobe absent / unreadable file
        return None


def handle_scan_files(cmd, emit: Emit) -> None:
    from filename_parser import parse as parse_filename
    from run import needs_processing

    if not cmd.input_dir:
        _emit_error(emit, cmd.id, "invalid_command_payload", "input_dir required")
        return
    root = Path(cmd.input_dir)
    if not root.exists() or not root.is_dir():
        _emit_error(
            emit, cmd.id, "invalid_command_payload",
            f"input_dir does not exist or is not a directory: {root}",
        )
        return

    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _AUDIO_EXTS:
            continue
        try:
            meta = parse_filename(path)
            meta_status: dict[str, Any] = {
                "date": meta.date,
                "language": meta.language,
                "teacher_id": meta.teacher_id,
                "student_id": meta.student_id,
                "parse_ok": True,
            }
        except Exception as exc:  # noqa: BLE001 — filename-parser errors are user-facing
            meta_status = {"parse_ok": False, "parse_error": str(exc)}

        entry: dict[str, Any] = {
            "path": str(path),
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "meta": meta_status,
            "needs_processing": bool(needs_processing(path)) if meta_status.get("parse_ok") else True,
        }
        if cmd.probe_duration:
            entry["duration_s"] = _probe_duration(path)
        entries.append(entry)

    emit(FilesScannedEvent(id=cmd.id, files=entries))


# ---------------------------------------------------------------------------
# get_corpus_summary
# ---------------------------------------------------------------------------

def handle_get_corpus_summary(cmd, emit: Emit) -> None:
    from persons import corpus, registry

    try:
        entries = corpus.load()
        records = registry.list_all()
    except Exception as exc:  # noqa: BLE001
        log.exception("get_corpus_summary failed")
        _emit_error(emit, cmd.id, "daemon_crash", str(exc))
        return

    persons_summary = {
        r.id: {
            "display_name": r.display_name,
            "sessions_as_teacher": r.n_sessions_as_teacher,
            "sessions_as_student": r.n_sessions_as_student,
            "total_hours": round(r.total_hours, 2),
            "observed_regions": list(r.observed_regions),
        }
        for r in records
    }
    total_hours = sum(r.total_hours for r in records)

    emit(CorpusSummaryEvent(
        id=cmd.id,
        session_count=len(entries),
        persons=persons_summary,
        total_hours=round(total_hours, 2),
    ))


# ---------------------------------------------------------------------------
# cancel_batch
# ---------------------------------------------------------------------------

def handle_cancel_batch(cmd, emit: Emit) -> None:
    """Light the cooperative-cancel flag and ack.

    The actual interrupt happens inside the batch loop's `cancel_check()`
    calls (Gate 5D). This handler only signals — it's safe to call with no
    batch running (it just primes the flag for the next one, though the
    next handler should reset it; see Gate 5D).
    """
    cancellation.request_cancel()
    emit(CancelAcceptedEvent(id=cmd.id))
