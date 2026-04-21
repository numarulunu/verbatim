"""
atomic_write_wav must be crash-safe: a simulated failure mid-write must
leave the target untouched (never half-written).
"""
import numpy as np
import pytest
import soundfile as sf
from pathlib import Path


def test_atomic_write_wav_leaves_tmp_on_crash(tmp_path, monkeypatch):
    from utils.atomic_audio import atomic_write_wav

    target = tmp_path / "out.wav"
    # Pre-populate target with known-good content.
    # Use FLOAT subtype so round-trip is lossless and np.allclose (default tol) holds.
    good = np.ones(16000, dtype=np.float32)
    sf.write(str(target), good, 16000, subtype="FLOAT")

    # Patch os.replace to raise — simulates crash between write and rename.
    import os
    original_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)

    new = np.zeros(16000, dtype=np.float32)
    with pytest.raises(OSError, match="simulated crash"):
        atomic_write_wav(target, new, sr=16000)

    # Target MUST still hold the original content (not corrupted / zeroed).
    restore = sf.read(str(target), dtype="float32")[0]
    assert np.allclose(restore, good), "target was overwritten on a crashed atomic_write"

    # Exception handler must also clean up the tmp so no orphan lingers.
    tmp_sibling = target.with_suffix(target.suffix + ".tmp")
    assert not tmp_sibling.exists(), "atomic_write_wav must unlink its .tmp on crash"


def test_atomic_write_wav_happy_path(tmp_path):
    from utils.atomic_audio import atomic_write_wav

    target = tmp_path / "out.wav"
    audio = np.linspace(-1, 1, 8000, dtype=np.float32)
    atomic_write_wav(target, audio, sr=16000)

    assert target.exists()
    assert not (tmp_path / "out.wav.tmp").exists(), "tmp sibling must be removed after success"
    readback, sr = sf.read(str(target), dtype="float32")
    assert sr == 16000
    assert readback.shape == audio.shape


def test_atomic_write_wav_tmp_name_matches_purge_pattern(tmp_path):
    """The tmp-file naming must be reaped by cleanup.purge_tmp_siblings
    (which globs *.tmp). Verified by directly running the cleanup pass over
    an orphan tmp file written at the expected path. See SMAC Finding #1."""
    import soundfile as sf
    from utils.atomic_write import purge_tmp_siblings

    target = tmp_path / "acapella.wav"
    # Create an orphan at the tmp path the atomic writer uses.
    orphan = target.with_suffix(target.suffix + ".tmp")
    sf.write(str(orphan), np.zeros(100, dtype=np.float32), 16000,
             subtype="PCM_16", format="WAV")
    assert orphan.exists()

    removed = purge_tmp_siblings(tmp_path)

    assert removed >= 1
    assert not orphan.exists(), "purge_tmp_siblings did not reap the orphan tmp"
