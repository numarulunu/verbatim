"""
Polish engine dispatcher.

Two backends:
  cli  — spawns Claude Code CLI subprocess, uses Max subscription (free).
         ~2s overhead per call.
  api  — Anthropic SDK async calls, pay-per-token, higher parallelism.

Both receive a per-language glossary and a chunk of segments; return the
same-shape chunk with optional corrections. Schema drift (timestamp or
speaker change) invalidates a polish and the raw JSON is retained.

Segments with avg_logprob > POLISH_SKIP_AVG_LOGPROB skip polish entirely.
"""
from __future__ import annotations

from pathlib import Path


def polish_chunks(segments: list[dict], language: str) -> list[dict]:
    """Chunk segments, send to configured engine, merge boundaries."""
    raise NotImplementedError


def polish_chunk_cli(chunk: list[dict], language: str, glossary: dict) -> list[dict]:
    """Spawn Claude Code CLI; capture JSON response."""
    raise NotImplementedError


def polish_chunk_api(chunk: list[dict], language: str, glossary: dict) -> list[dict]:
    """Async Anthropic call."""
    raise NotImplementedError


def load_glossary(language: str) -> dict:
    """Load glossaries/glossary_<lang>.json."""
    raise NotImplementedError


def validate_chunk(original: list[dict], polished: list[dict]) -> bool:
    """Reject polish if timestamps or speaker_id drifted vs original."""
    raise NotImplementedError


def should_skip(segment: dict) -> bool:
    """True if avg_logprob > POLISH_SKIP_AVG_LOGPROB."""
    raise NotImplementedError
