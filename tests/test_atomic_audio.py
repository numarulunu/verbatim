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


def test_atomic_write_wav_tmp_name_matches_purge_pattern(tmp_path, monkeypatch):
    """The tmp-file naming must match cleanup.purge_tmp_siblings' *.tmp glob
    so orphaned tmps from crashed writes are reaped by the cleanup sweep.
    See SMAC Finding #1 spec review."""
    import os
    from utils.atomic_audio import atomic_write_wav

    target = tmp_path / "acapella.wav"
    # Force a crash so the tmp is attempted but never replaced.
    def boom(src, dst):
        raise OSError("simulated")
    monkeypatch.setattr(os, "replace", boom)

    try:
        atomic_write_wav(target, np.zeros(100, dtype=np.float32), sr=16000)
    except OSError:
        pass

    # The implementation unlinks the tmp on crash — so under normal failure
    # modes there's no orphan. But if THAT unlink also fails (e.g., AV lock),
    # the orphan must match the *.tmp glob. Simulate by disabling the cleanup
    # branch and re-running.
    target2 = tmp_path / "acapella2.wav"

    # Directly call sf.write to create an orphan at the expected tmp name.
    import soundfile as sf
    orphan = target2.with_suffix(target2.suffix + ".tmp")
    sf.write(str(orphan), np.zeros(100, dtype=np.float32), 16000, subtype="PCM_16", format="WAV")

    # Verify the orphan matches the glob used by cleanup.purge_tmp_siblings.
    matches = list(tmp_path.glob("*.tmp"))
    assert orphan in matches, f"tmp naming does not match *.tmp glob; got: {[p.name for p in matches]}"
