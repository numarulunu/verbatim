"""
Speaker embedding — pyannote/embedding.

Brief §3 prescribes INT8 quantization via CTranslate2. That path is deferred:
pyannote/embedding is a small SincNet+TDNN model (~17 MB), inference on a
handful of 3-second clips per session is sub-second on CPU at FP32, and
CTranslate2 does not provide a drop-in quantizer for arbitrary PyTorch
architectures. Re-evaluate once the pipeline is running and a real profile
shows this is a bottleneck. Until then: torch, FP32, GPU when available.

L2 normalization is applied at save time so downstream cosine math is a
plain dot product.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import DECODE_SAMPLE_RATE, EMBEDDING_MODEL, HF_TOKEN

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)

_model = None
_device = None


def load_embedder():
    """Lazy-instantiate PretrainedSpeakerEmbedding. Singleton."""
    global _model, _device
    if _model is not None:
        return _model
    if not HF_TOKEN:
        raise RuntimeError(
            "HUGGINGFACE_TOKEN / HF_TOKEN must be set to load pyannote/embedding"
        )
    import torch
    from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding

    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _model = PretrainedSpeakerEmbedding(
        EMBEDDING_MODEL,
        device=_device,
        use_auth_token=HF_TOKEN,
    )
    log.info("loaded pyannote/embedding on %s", _device)
    return _model


def embed(audio: "np.ndarray") -> "np.ndarray":
    """Return L2-normalized 512-dim embedding for 1-D 16 kHz PCM."""
    import numpy as np
    import torch

    if audio.ndim != 1:
        raise ValueError(f"embed expects 1-D audio, got shape {audio.shape}")
    if audio.size < DECODE_SAMPLE_RATE // 2:
        # <0.5s is below what pyannote/embedding reliably handles.
        raise ValueError(f"audio too short for embedding ({audio.size} samples)")

    model = load_embedder()
    # pyannote expects (batch, channel, samples). Float32.
    wav = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0).unsqueeze(0)
    with torch.no_grad():
        emb = model(wav)  # returns (1, dim) numpy array
    vec = np.asarray(emb[0], dtype=np.float32)
    norm = float(np.linalg.norm(vec)) + 1e-9
    return vec / norm


def embed_turn(audio: "np.ndarray", start_s: float, end_s: float) -> "np.ndarray":
    """Slice a turn from audio at start_s:end_s and embed it."""
    sr = DECODE_SAMPLE_RATE
    start_idx = max(0, int(start_s * sr))
    end_idx = min(len(audio), int(end_s * sr))
    if end_idx <= start_idx:
        raise ValueError(f"invalid turn span [{start_s}, {end_s}]")
    return embed(audio[start_idx:end_idx])


def cosine(a: "np.ndarray", b: "np.ndarray") -> float:
    """Cosine similarity of two pre-normalized vectors (plain dot product)."""
    import numpy as np
    a_n = a / (np.linalg.norm(a) + 1e-9)
    b_n = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a_n, b_n))


def teardown() -> None:
    """Release the embedder model and its VRAM. Safe to call multiple times."""
    global _model, _device
    if _model is None:
        return
    _model = None
    _device = None
    try:
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
