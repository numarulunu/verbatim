"""
load_embedder must ensure huggingface_hub.hf_hub_download accepts the
deprecated `use_auth_token=` kwarg before pyannote is imported. Otherwise
redo-mode runs (which skip stage 2 / load_diarizer) crash with
TypeError: hf_hub_download() got an unexpected keyword argument 'use_auth_token'.
"""
import sys

import pytest


def test_hf_compat_patch_accepts_use_auth_token():
    """The shim must translate use_auth_token= to token= without raising."""
    from utils.hf_compat import patch_hf_hub_use_auth_token
    patch_hf_hub_use_auth_token()

    import huggingface_hub
    # Call the patched hf_hub_download with the deprecated kwarg. We expect
    # any exception OTHER than the TypeError (the shim should have forwarded
    # it as token=). Network errors are fine — they prove the kwarg was
    # accepted.
    try:
        huggingface_hub.hf_hub_download(
            repo_id="hf-internal-testing/tiny-random-gpt2",
            filename="config.json",
            use_auth_token=None,
            local_files_only=True,
        )
    except TypeError as e:
        if "use_auth_token" in str(e):
            pytest.fail(f"shim did not translate kwarg: {e}")
    except Exception:
        # Any other error is fine — kwarg accepted.
        pass


def test_load_embedder_invokes_hf_compat(monkeypatch):
    """load_embedder must call patch_hf_hub_use_auth_token before touching pyannote,
    so redo-mode (which doesn't load the diarizer) still works."""
    called = {"patch": False, "pretrained": False}

    def fake_patch():
        called["patch"] = True

    class FakeEmbedder:
        def __init__(self, *args, **kwargs):
            called["pretrained"] = True
            # Ensure patch ran BEFORE this constructor was called.
            assert called["patch"], "patch must run before PretrainedSpeakerEmbedding"

    import types
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        device=lambda name: f"device({name})",
    )
    fake_pyannote_verif = types.SimpleNamespace(PretrainedSpeakerEmbedding=FakeEmbedder)

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "pyannote", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pyannote.audio", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pyannote.audio.pipelines", types.SimpleNamespace(speaker_verification=fake_pyannote_verif))
    monkeypatch.setitem(sys.modules, "pyannote.audio.pipelines.speaker_verification", fake_pyannote_verif)

    # Reload embedder fresh so _model singleton is cleared.
    sys.modules.pop("persons.embedder", None)
    sys.modules.pop("utils.hf_compat", None)

    # Install a fake hf_compat with our spy patch.
    fake_hf_compat = types.SimpleNamespace(patch_hf_hub_use_auth_token=fake_patch)
    monkeypatch.setitem(sys.modules, "utils.hf_compat", fake_hf_compat)

    # Also stub HF_TOKEN so load_embedder doesn't raise on empty.
    import config
    monkeypatch.setattr(config, "HF_TOKEN", "dummy-token")

    from persons import embedder
    embedder.load_embedder()

    assert called["patch"], "load_embedder must call patch_hf_hub_use_auth_token"
    assert called["pretrained"], "load_embedder must instantiate PretrainedSpeakerEmbedding"
