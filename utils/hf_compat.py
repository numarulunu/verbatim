"""
Compatibility shim for huggingface_hub >=1.x after pyannote 3.3.2.

pyannote.audio 3.3.2 still passes the deprecated `use_auth_token=` kwarg
down to `huggingface_hub.hf_hub_download`. huggingface_hub 1.x dropped that
alias. We translate it transparently by rebinding every `hf_hub_download`
reference already imported across `sys.modules`, plus the source module.

Call this BEFORE any code path that loads pyannote (diarizer, embedder).
Idempotent — safe to call many times.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

_patched = False


def patch_hf_hub_use_auth_token() -> None:
    """Install the use_auth_token -> token translation shim. Idempotent."""
    global _patched
    if _patched:
        return
    import huggingface_hub

    orig = huggingface_hub.hf_hub_download

    def _shim(*args, **kwargs):
        if "use_auth_token" in kwargs:
            kwargs.setdefault("token", kwargs.pop("use_auth_token"))
        return orig(*args, **kwargs)

    replaced = 0
    huggingface_hub.hf_hub_download = _shim
    replaced += 1
    try:
        import huggingface_hub.file_download as fd
        if getattr(fd, "hf_hub_download", None) is orig:
            fd.hf_hub_download = _shim
            replaced += 1
    except ImportError:
        pass
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            if getattr(mod, "hf_hub_download", None) is orig:
                mod.hf_hub_download = _shim
                replaced += 1
        except Exception:  # noqa: BLE001 - some modules raise on attr access
            continue
    _patched = True
    log.info("hf_compat: patched hf_hub_download (use_auth_token -> token) in %d module(s)", replaced)
