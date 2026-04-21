"""
Stage 3 — identification, verification, polish, voiceprint update, corpus write.

Takes the cluster-labeled segments from stage 2 (each segment tagged with
`cluster_label` like 'SPEAKER_00') and the raw acapella audio, and produces
a fully-populated polished transcript ready to write to POLISHED_DIR.

Phase 8:  person identification  (matcher + bootstrap)
Phase 8b: verification pass      (short-turn reassignment)
Phase 9:  polish                 (CLI or API engine)
Phase 10: voice-library update + corpus append

Every output is stamped with `processed_at_db_state` so `--redo` can tell
which files were processed against a stale DB.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from config import (
    COLLISION_THRESHOLD,
    NEW_PERSON_CONFIDENCE_GATE,
    PIPELINE_VERSION,
    POLISH_ENGINE,
    RECENT_BUFFER_SIZE,
    REGION_LABELS,
    SPEAKER_VERIFICATION_ENABLED,
    UPDATE_REJECTION_THRESHOLD,
    VOICE_LIB_MIN_REGION_SECONDS,
    DRIFT_WARNING_THRESHOLD,
)
from persons import corpus as corpus_module
from persons import registry
from persons.matcher import (
    assign_clusters,
    bootstrap_new_person,
    check_collisions,
)
from persons.schema import PersonRecord, render_display, total_sessions

if TYPE_CHECKING:
    from filename_parser import SessionMeta

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 8 — identification
# ---------------------------------------------------------------------------

def identify_speakers(
    segments: list[dict],
    cluster_embeddings: dict[str, "np.ndarray"],
    acapella: "np.ndarray",
    sr: int,
    meta: "SessionMeta",
) -> tuple[list[dict], dict[str, PersonRecord]]:
    """
    Map pyannote cluster labels to participant ids. Returns:
      - segments with speaker_id/name/role/confidence/matched_region attached
      - {cluster_label: PersonRecord} lookup used downstream
    """
    teacher = _load_or_none(meta.teacher_id)
    student = _load_or_none(meta.student_id)

    assignments = assign_clusters(cluster_embeddings, teacher, student)

    # Unregistered participants -> bootstrap them from orphan clusters. Both
    # teacher AND student may need bootstrapping on a first-ever run (no prior
    # library for either), so we handle them in sequence, not if/elif.
    assigned_labels = set(assignments.keys())
    unassigned_labels = list(set(cluster_embeddings.keys()) - assigned_labels)

    if teacher is None and unassigned_labels:
        bootstrap_label = unassigned_labels.pop(0)
        new = bootstrap_new_person(
            cluster_embeddings[bootstrap_label],
            id_=meta.teacher_id,
            display_name=meta.teacher_id,   # correctable via `enroll.py edit`
            default_role="teacher",
            first_seen=meta.date,
        )
        teacher = new
        # Bootstrap confidence is 1.0 by construction — the cluster IS this
        # person (we just sampled it). The first-3-sessions gate still applies
        # on future runs when prior library exists.
        assignments[bootstrap_label] = (new.id, 1.0, "universal")
        log.warning(
            "bootstrapped new teacher %r from cluster %s; "
            "first 3 sessions require confidence > %.2f or manual confirm",
            new.id, bootstrap_label, NEW_PERSON_CONFIDENCE_GATE,
        )

    if student is None and unassigned_labels:
        bootstrap_label = unassigned_labels.pop(0)
        new = bootstrap_new_person(
            cluster_embeddings[bootstrap_label],
            id_=meta.student_id,
            display_name=meta.student_id,
            default_role="student",
            first_seen=meta.date,
        )
        student = new
        assignments[bootstrap_label] = (new.id, 1.0, "universal")
        log.warning(
            "bootstrapped new student %r from cluster %s; "
            "first 3 sessions require confidence > %.2f or manual confirm",
            new.id, bootstrap_label, NEW_PERSON_CONFIDENCE_GATE,
        )

    # Build {cluster_label: PersonRecord} lookup.
    label_to_person: dict[str, PersonRecord] = {}
    for label, (pid, _, _) in assignments.items():
        try:
            label_to_person[label] = registry.load(pid)
        except registry.PersonNotFoundError:
            log.error("assignment references missing person %r", pid)

    # Attach speaker metadata onto each segment.
    out: list[dict] = []
    for seg in segments:
        label = seg.get("cluster_label")
        attr = assignments.get(label) if label else None
        new_seg = dict(seg)
        if attr is None:
            new_seg.update(
                speaker_id=None,
                speaker_name=None,
                speaker_role=None,
                speaker_confidence=None,
                matched_region=None,
            )
            out.append(new_seg)
            continue
        pid, conf, region = attr
        person = label_to_person.get(label)
        role = (
            "teacher" if pid == meta.teacher_id
            else "student" if pid == meta.student_id
            else (person.default_role if person else None)
        )
        new_seg.update(
            speaker_id=pid,
            speaker_name=render_display(person) if person else pid,
            speaker_role=role,
            speaker_confidence=float(conf),
            matched_region=region or None,
        )
        out.append(new_seg)

    return out, label_to_person


def _load_or_none(person_id: str) -> PersonRecord | None:
    try:
        return registry.load(person_id)
    except registry.PersonNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Phase 8b — verification pass
# ---------------------------------------------------------------------------

def run_verification(
    segments: list[dict],
    cluster_embeddings: dict[str, "np.ndarray"],
    label_to_person: dict[str, PersonRecord],
    audio: "np.ndarray",
    sr: int,
) -> list[dict]:
    """
    Short-turn reassignment. After verifier flips cluster_labels, we re-derive
    speaker_id/name/role from the new cluster mapping.
    """
    if not SPEAKER_VERIFICATION_ENABLED:
        return segments
    from persons.embedder import embed
    from persons.verifier import verify_transcript

    def _embed_fn(clip, _sr):
        return embed(clip)

    flipped = verify_transcript(
        segments, cluster_embeddings, _embed_fn, audio, sr,
    )
    # Re-derive speaker fields for any segment whose cluster_label changed.
    out: list[dict] = []
    for seg in flipped:
        if not seg.get("_verifier_flipped"):
            out.append(seg)
            continue
        label = seg["cluster_label"]
        person = label_to_person.get(label)
        if person is None:
            out.append(seg)
            continue
        new = dict(seg)
        new["speaker_id"] = person.id
        new["speaker_name"] = render_display(person)
        # Role stays whatever it was for that cluster in this session.
        new.pop("_verifier_flipped", None)
        out.append(new)
    return out


# ---------------------------------------------------------------------------
# Phase 9 — polish
# ---------------------------------------------------------------------------

def polish(segments: list[dict], language: str) -> list[dict]:
    """Dispatch to persons.polish_engine (cli or api)."""
    from persons.polish_engine import polish_chunks
    return polish_chunks(segments, language)


# ---------------------------------------------------------------------------
# Phase 10 — voice library update + corpus write
# ---------------------------------------------------------------------------

def update_voice_libraries(
    segments: list[dict],
    label_to_person: dict[str, PersonRecord],
    acapella: "np.ndarray",
    sr: int,
    meta: "SessionMeta",
    is_redo: bool = False,
) -> None:
    """
    Per-person region-aware running-mean centroid update.

    For each person appearing in `segments`, group their segments by
    matched_region and compute a new per-region centroid from the concatenated
    audio. Running-mean-blend into the existing centroid on disk. Reject if
    confidence < UPDATE_REJECTION_THRESHOLD.
    """
    from persons.embedder import embed
    from persons.matcher import person_dir  # flag_collision lives in registry, not matcher

    per_person_confidences: dict[str, list[float]] = {}
    per_person_regions: dict[str, dict[str, list[np.ndarray]]] = {}
    per_person_durations: dict[str, float] = {}

    for seg in segments:
        pid = seg.get("speaker_id")
        if not pid:
            continue
        per_person_confidences.setdefault(pid, []).append(
            float(seg.get("speaker_confidence") or 0.0)
        )
        duration = float(seg["end"]) - float(seg["start"])
        per_person_durations[pid] = per_person_durations.get(pid, 0.0) + duration
        region = seg.get("matched_region") or "speaking"
        # `universal` and `recent` are library-lookup aggregates, not real
        # vocal regions — we can't accumulate against them here (recent.npy is
        # (N, 512), shape-incompatible with per-region running mean). Fold them
        # back to "speaking" for accumulation.
        if region not in REGION_LABELS:
            region = "speaking"
        start = max(0, int(float(seg["start"]) * sr))
        end = min(len(acapella), int(float(seg["end"]) * sr))
        if end - start < sr // 2:
            continue
        per_person_regions.setdefault(pid, {}).setdefault(region, []).append(
            acapella[start:end]
        )

    for pid, region_clips in per_person_regions.items():
        avg_conf = (
            sum(per_person_confidences.get(pid, [])) / max(1, len(per_person_confidences.get(pid, [])))
        )
        # Hard rejection: below-floor confidence never updates.
        if avg_conf < UPDATE_REJECTION_THRESHOLD:
            log.warning(
                "voice library update rejected for %s: avg confidence %.2f < %.2f",
                pid, avg_conf, UPDATE_REJECTION_THRESHOLD,
            )
            continue
        person = label_to_person.get(_first_label_for_pid(pid, label_to_person)) or _load_or_none(pid)
        if person is None:
            continue
        # First-3-sessions poisoning guard (SMAC Finding #6). Bootstrap session 1
        # has confidence=1.0 by construction (cluster IS this person). For the
        # NEXT 2 sessions (bootstrap_sessions_remaining in {2, 1}), require
        # real match confidence above NEW_PERSON_CONFIDENCE_GATE.
        if (
            0 < person.bootstrap_sessions_remaining < 3
            and avg_conf < NEW_PERSON_CONFIDENCE_GATE
        ):
            log.warning(
                "first-3-sessions gate: skipping update for %s (avg conf %.2f < %.2f); "
                "run `enroll.py confirm %s <session_id>` to approve manually",
                pid, avg_conf, NEW_PERSON_CONFIDENCE_GATE, pid,
            )
            continue
        did_update = _update_one_person(person, region_clips, per_person_durations[pid], meta, is_redo=is_redo)
        # Decrement trust counter ONLY when a real (non-redo) update actually
        # wrote a centroid — a silent no-op (no region had enough audio)
        # must not burn down the bootstrap guard.
        if did_update and person.bootstrap_sessions_remaining > 0 and not is_redo:
            person.bootstrap_sessions_remaining -= 1
            registry.save(person)

    # Collision sweep after any updates.
    for a, b, score in check_collisions():
        log.warning("collision: %r <-> %r cos=%.3f (> %.2f)", a, b, score, COLLISION_THRESHOLD)
        registry.flag_collision(a, b)


def _first_label_for_pid(pid: str, label_to_person: dict[str, PersonRecord]) -> str | None:
    for label, p in label_to_person.items():
        if p.id == pid:
            return label
    return None


def _update_one_person(
    person: PersonRecord,
    region_clips: dict[str, list[np.ndarray]],
    total_duration_s: float,
    meta: "SessionMeta",
    is_redo: bool = False,
) -> bool:
    from persons.embedder import embed
    from persons.matcher import person_dir as _pdir

    pdir = _pdir(person.id)
    pdir.mkdir(parents=True, exist_ok=True)
    updated_regions: list[str] = []

    # Per-region running-mean.
    active_centroids: list[np.ndarray] = []
    from config import DECODE_SAMPLE_RATE
    for region, clips in region_clips.items():
        concat = np.concatenate(clips).astype(np.float32)
        if len(concat) / DECODE_SAMPLE_RATE < VOICE_LIB_MIN_REGION_SECONDS:
            continue
        new_centroid = embed(concat)
        existing_path = pdir / f"{region}.npy"
        if is_redo:
            if not existing_path.exists():
                # No prior save for this region — nothing to reconstruct on
                # redo. Skip so the universal rollup doesn't end up derived
                # from a region centroid that has no corresponding .npy /
                # region_session_counts entry.
                continue
            # Redo: this session's audio is ALREADY folded into the existing
            # centroid. Re-blending would double-weight it.
            blended = np.load(existing_path)
        elif existing_path.exists():
            prior = np.load(existing_path)
            n_prior = person.region_session_counts.get(region, 0)
            blended = (prior * n_prior + new_centroid) / (n_prior + 1)
            blended = blended / (np.linalg.norm(blended) + 1e-9)
            # Drift warning
            drift = 1.0 - float(np.dot(prior, blended) / (np.linalg.norm(prior) * np.linalg.norm(blended) + 1e-9))
            if drift > DRIFT_WARNING_THRESHOLD:
                log.warning("drift for %s.%s: %.3f > %.3f", person.id, region, drift, DRIFT_WARNING_THRESHOLD)
        else:
            blended = new_centroid
        if not is_redo:
            np.save(existing_path, blended)
            person.region_session_counts[region] = person.region_session_counts.get(region, 0) + 1
            if region not in person.observed_regions:
                person.observed_regions.append(region)
            updated_regions.append(region)
        if region in REGION_LABELS:
            active_centroids.append(blended)

    # Universal = weighted mean of active region centroids.
    if active_centroids:
        universal = np.mean(np.stack(active_centroids, axis=0), axis=0)
        universal = universal / (np.linalg.norm(universal) + 1e-9)
        np.save(pdir / "universal.npy", universal)
        _push_recent(pdir / "recent.npy", universal)

    if not is_redo:
        # Role + session counts.
        if meta.teacher_id == person.id:
            person.n_sessions_as_teacher += 1
        elif meta.student_id == person.id:
            person.n_sessions_as_student += 1
        person.total_hours += total_duration_s / 3600.0
        person.last_updated = meta.date
        if person.first_seen is None:
            person.first_seen = meta.date
        registry.save(person)
    log.info(
        "updated voice library for %r: regions=%s sessions=%d redo=%s",
        person.id, updated_regions, total_sessions(person), is_redo,
    )
    return bool(active_centroids) or is_redo


def _push_recent(path: Path, universal: np.ndarray) -> None:
    if path.exists():
        ring = np.load(path)
        if ring.ndim != 2:
            ring = universal.reshape(1, -1)
        else:
            ring = np.vstack([universal.reshape(1, -1), ring])
            ring = ring[:RECENT_BUFFER_SIZE]
    else:
        ring = universal.reshape(1, -1)
    np.save(path, ring)


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------

def stamp_db_state(transcript: dict) -> dict:
    """Attach processed_at_db_state snapshot + processed_at timestamp."""
    from persons.redo import current_db_snapshot
    transcript["processed_at"] = datetime.now(tz=timezone.utc).isoformat()
    transcript["processed_at_db_state"] = current_db_snapshot()
    transcript["pipeline_version"] = PIPELINE_VERSION
    transcript["polish_engine"] = POLISH_ENGINE
    return transcript


def finalize(transcript: dict, out_path: Path) -> None:
    """Write polished JSON atomically + append session to corpus.json."""
    from utils.atomic_write import atomic_write_json
    atomic_write_json(out_path, transcript)
    entry = corpus_module.session_entry_from(transcript)
    corpus_module.replace_session(transcript["file_id"], entry)
