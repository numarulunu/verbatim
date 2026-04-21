"""
Guard: requirements.txt must pin every runtime dep Gate 5 discovered.

Without these pins, a fresh machine install will break at stage 2 (cuDNN
DLL missing). See docs/smac-reports/2026-04-21-*.md Finding #3.
"""
from pathlib import Path

REQUIRED_PINS = (
    "nvidia-cuda-runtime-cu12",
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu11",
    "speechbrain",
)


def test_requirements_contains_gate5_pins():
    text = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text(encoding="utf-8")
    missing = [p for p in REQUIRED_PINS if p not in text]
    assert not missing, f"requirements.txt is missing Gate-5 pins: {missing}"


def test_speechbrain_pinned_below_1_0():
    text = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text(encoding="utf-8")
    assert "speechbrain" in text
    assert "speechbrain<1.0" in text or 'speechbrain<"1.0"' in text or "speechbrain~=0.5" in text, (
        "speechbrain must be pinned <1.0 — 1.x lazy-imports k2_fsa which crashes under "
        "pytorch-lightning stack walks. See SMAC Finding #3."
    )


def test_cudnn_pinned_to_8_x():
    text = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text(encoding="utf-8")
    # CTranslate2 4.x needs cuDNN 8 specifically
    assert "nvidia-cudnn-cu11<9" in text or "nvidia-cudnn-cu11==8" in text
