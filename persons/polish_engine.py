"""
Polish engine dispatcher.

Two backends selected by config.POLISH_ENGINE:

  "cli"  — spawns the Claude Code CLI via subprocess. Uses the Max
           subscription (no per-token cost), adds ~2 s overhead per call.
  "api"  — AsyncAnthropic + asyncio.gather for concurrent messages.create.
           Pay-per-token but much faster when many chunks queue up.

Both receive a per-language glossary and a chunk of segments, and must
return the same-shape chunk with corrections. Schema drift (timestamp or
speaker change) invalidates a polish and the raw JSON is retained.

Segments with avg_logprob > POLISH_SKIP_AVG_LOGPROB skip polish entirely -
cuts workload ~60% on clean audio while preserving quality where it counts.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from pathlib import Path

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CLAUDE_CLI_TIMEOUT_S,
    GLOSSARY_EN,
    GLOSSARY_RO,
    POLISH_CHUNK_SIZE,
    POLISH_CHUNK_SIZE_NEW,
    POLISH_ENGINE,
    POLISH_OVERLAP,
    POLISH_SKIP_AVG_LOGPROB,
    WORD_CONFIDENCE_THRESHOLD,
)

log = logging.getLogger(__name__)

# JSON keys allowed in a polished segment — used for schema validation.
_ALLOWED_SEGMENT_KEYS = frozenset(
    ("start", "end", "speaker_id", "text", "polished", "avg_logprob")
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def polish_chunks(segments: list[dict], language: str) -> list[dict]:
    """
    Polish every segment that isn't above the confidence floor. Chunks of
    POLISH_CHUNK_SIZE with POLISH_OVERLAP overlap, merged on the way out.
    """
    if not segments:
        return []
    glossary = load_glossary(language)

    # Partition into polish-eligible and skipped segments. Preserve order.
    eligible_idx = [i for i, s in enumerate(segments) if not should_skip(s)]
    if not eligible_idx:
        log.info("polish: all %d segments above logprob floor; passing through", len(segments))
        return [dict(s, polished=False) for s in segments]

    eligible_segments = [segments[i] for i in eligible_idx]
    # Phase 4 (2026-04-24 plan): when POLISH_CHUNK_SIZE_NEW is committed by
    # Phase 1 calibration, use it. Otherwise fall back to the legacy
    # POLISH_CHUNK_SIZE so behavior is unchanged pre-calibration.
    chunk_size = POLISH_CHUNK_SIZE_NEW if POLISH_CHUNK_SIZE_NEW is not None else POLISH_CHUNK_SIZE
    chunks = _chunk(eligible_segments, chunk_size, POLISH_OVERLAP)

    if POLISH_ENGINE == "api":
        polished_chunks = asyncio.run(_polish_chunks_api(chunks, language, glossary))
    elif POLISH_ENGINE == "cli":
        polished_chunks = [
            polish_chunk_cli(chunk, language, glossary) for chunk in chunks
        ]
    else:
        raise ValueError(f"POLISH_ENGINE must be 'cli' or 'api', got {POLISH_ENGINE!r}")

    polished_eligible = _merge_overlapping(polished_chunks, POLISH_OVERLAP)

    # Merge polished eligibles back into the full ordered list.
    out: list[dict] = []
    polished_iter = iter(polished_eligible)
    eligible_set = set(eligible_idx)
    for i, seg in enumerate(segments):
        if i in eligible_set:
            try:
                new_seg = next(polished_iter)
                out.append(new_seg)
            except StopIteration:
                out.append(dict(seg, polished=False))
        else:
            out.append(dict(seg, polished=False))
    return out


def should_skip(segment: dict) -> bool:
    """True iff the segment is confident enough to skip polish.

    Phase 4 (2026-04-24 plan) routes to a word-level confidence gate when
    Phase 1 has committed WORD_CONFIDENCE_THRESHOLD: skip iff EVERY word
    in the segment scored at or above that threshold. This is a tighter
    signal than segment-mean avg_logprob, which can mask a single bad word
    inside an otherwise confident segment.

    Sung segments are routed through persons.sung_handler instead and
    reach polish only as `[SUNG: ~Xs]` markers; the word-level gate
    naturally skips them (no `words` field after sung_handler).

    Falls back to the legacy avg_logprob gate when WORD_CONFIDENCE_THRESHOLD
    is None (Phase 1 not yet calibrated) or the segment lacks a `words`
    field (e.g., tests that don't ship per-word metadata).
    """
    if segment.get("polished") and segment.get("sung"):
        return True

    if WORD_CONFIDENCE_THRESHOLD is not None:
        words = segment.get("words")
        if words:
            return all(
                (w.get("probability") or 0.0) >= WORD_CONFIDENCE_THRESHOLD
                for w in words
            )
        # No per-word metadata for this segment — fall through to legacy gate.

    logprob = segment.get("avg_logprob")
    if logprob is None:
        return False
    return float(logprob) > POLISH_SKIP_AVG_LOGPROB


# ---------------------------------------------------------------------------
# CLI backend
# ---------------------------------------------------------------------------

def polish_chunk_cli(chunk: list[dict], language: str, glossary: dict) -> list[dict]:
    """Spawn Claude Code CLI with the prompt on stdin; parse JSON response."""
    prompt = _build_prompt(chunk, language, glossary)
    cmd = ["claude", "--print", "--output-format", "text"]
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=CLAUDE_CLI_TIMEOUT_S,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.error("polish cli failed: %s - retaining raw chunk", exc)
        return [dict(s, polished=False) for s in chunk]

    if result.returncode != 0:
        log.error(
            "polish cli exited %d: %s - retaining raw chunk",
            result.returncode, result.stderr[:200],
        )
        return [dict(s, polished=False) for s in chunk]

    parsed = _extract_json(result.stdout)
    if parsed is None or not validate_chunk(chunk, parsed):
        return [dict(s, polished=False) for s in chunk]
    return _merge_polished_segments(chunk, parsed)


# ---------------------------------------------------------------------------
# API backend
# ---------------------------------------------------------------------------

async def _polish_chunks_api(
    chunks: list[list[dict]],
    language: str,
    glossary: dict,
) -> list[list[dict]]:
    """Dispatch all chunks concurrently through AsyncAnthropic."""
    from anthropic import AsyncAnthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set when POLISH_ENGINE='api'"
        )
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    tasks = [polish_chunk_api(client, c, language, glossary) for c in chunks]
    return await asyncio.gather(*tasks)


async def polish_chunk_api(
    client,
    chunk: list[dict],
    language: str,
    glossary: dict,
) -> list[dict]:
    """Async Anthropic call — returns polished chunk or falls back to raw."""
    prompt = _build_prompt(chunk, language, glossary)
    try:
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8192,
            system=_system_prompt(language),
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        log.error("polish api failed: %s - retaining raw chunk", exc)
        return [dict(s, polished=False) for s in chunk]

    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    parsed = _extract_json(text)
    if parsed is None or not validate_chunk(chunk, parsed):
        return [dict(s, polished=False) for s in chunk]
    return _merge_polished_segments(chunk, parsed)


# ---------------------------------------------------------------------------
# Glossary + prompt
# ---------------------------------------------------------------------------

def load_glossary(language: str) -> dict:
    path = {"en": GLOSSARY_EN, "ro": GLOSSARY_RO}.get(language)
    if path is None or not path.exists():
        log.warning("no glossary for language=%r", language)
        return {"language": language, "terms": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("glossary load failed (%s): %s", path, exc)
        return {"language": language, "terms": {}}


def _system_prompt(language: str) -> str:
    return (
        f"You are a transcription polishing assistant. The recording is a "
        f"vocal lesson in {language}. You will be given a JSON array of "
        f"segments and a glossary of pedagogical terms commonly misheard. "
        f"Return a JSON array of the SAME LENGTH with the SAME start/end/"
        f"speaker_id on each segment. Only change the `text` field, and only "
        f"when the glossary or context indicates a clear correction. Respond "
        f"with a single JSON array, no prose."
    )


def _build_prompt(chunk: list[dict], language: str, glossary: dict) -> str:
    minimal = [
        {
            "start": s["start"],
            "end": s["end"],
            "speaker_id": s.get("speaker_id"),
            "text": s.get("text", ""),
        }
        for s in chunk
    ]
    return (
        f"Glossary ({language}): {json.dumps(glossary.get('terms', {}), ensure_ascii=False)}\n\n"
        f"Segments to polish (return JSON array of SAME LENGTH, do not reorder, "
        f"do not change timestamps or speaker_id):\n"
        f"{json.dumps(minimal, ensure_ascii=False, indent=2)}"
    )


# ---------------------------------------------------------------------------
# Chunking + validation
# ---------------------------------------------------------------------------

def _chunk(segments: list[dict], size: int, overlap: int) -> list[list[dict]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    overlap = max(0, min(overlap, size - 1))
    if len(segments) <= size:
        return [list(segments)]
    step = size - overlap
    out: list[list[dict]] = []
    i = 0
    while i < len(segments):
        out.append(list(segments[i: i + size]))
        if i + size >= len(segments):
            break
        i += step
    return out


def _merge_overlapping(chunks: list[list[dict]], overlap: int) -> list[dict]:
    """Concatenate chunks, dropping duplicated overlap on each boundary."""
    if not chunks:
        return []
    out = list(chunks[0])
    for chunk in chunks[1:]:
        if overlap > 0 and len(chunk) > overlap:
            out.extend(chunk[overlap:])
        else:
            out.extend(chunk)
    return out


def validate_chunk(original: list[dict], polished: list[dict]) -> bool:
    """Reject if length / start / end / speaker_id drifted vs original."""
    if len(polished) != len(original):
        log.warning("polish length drift: %d -> %d", len(original), len(polished))
        return False
    for o, p in zip(original, polished):
        if not isinstance(p, dict):
            return False
        for k in ("start", "end"):
            if abs(float(o[k]) - float(p.get(k, -1))) > 0.001:
                log.warning("polish timestamp drift at segment start=%.3f", o.get("start"))
                return False
        if o.get("speaker_id") != p.get("speaker_id"):
            log.warning("polish speaker_id drift on segment start=%.3f", o.get("start"))
            return False
    return True


def _merge_polished_segments(original: list[dict], polished: list[dict]) -> list[dict]:
    """Copy original segments and apply only trusted polish output fields."""
    out: list[dict] = []
    for o, p in zip(original, polished):
        next_seg = dict(o)
        next_seg["text"] = str(p.get("text", o.get("text", "")))
        next_seg["polished"] = True
        out.append(next_seg)
    return out


def _extract_json(text: str) -> list[dict] | None:
    """Pull the first JSON array out of a response (tolerant of code fences)."""
    if not text:
        return None
    # Strip code fences first.
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end < start:
            return None
        candidate = text[start: end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        log.warning("polish response not valid JSON: %s", exc)
        return None
    if not isinstance(data, list):
        return None
    return data
