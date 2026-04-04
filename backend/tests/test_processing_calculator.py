"""Tests for processing_calculator.py — time estimation and formatting."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.processing_calculator import ProcessingCalculator


# ── _fmt static method ──────────────────────────────────────────────────────


class TestFmt:
    """Test the human-readable time formatter."""

    def test_seconds_format(self):
        assert ProcessingCalculator._fmt(0.5) == "30s"

    def test_minutes_only(self):
        assert ProcessingCalculator._fmt(5.0) == "5m"

    def test_minutes_and_seconds(self):
        assert ProcessingCalculator._fmt(2.5) == "2m 30s"

    def test_hours_format(self):
        result = ProcessingCalculator._fmt(90)
        assert result == "1h 30m"

    def test_zero(self):
        assert ProcessingCalculator._fmt(0) == "0s"

    def test_large_hours(self):
        result = ProcessingCalculator._fmt(180)
        assert result == "3h 0m"


# ── _estimate_whisper_time ──────────────────────────────────────────────────


class TestEstimateWhisperTime:
    """Test time estimation math (mocked GPU/batched detection)."""

    def _make_calc(self, has_gpu=False, batched=False, model="base"):
        """Create a calculator with controlled GPU/batched state."""
        with patch.dict("sys.modules", {"torch": MagicMock(), "faster_whisper": MagicMock()}):
            calc = ProcessingCalculator.__new__(ProcessingCalculator)
            calc.whisper_model = model
            calc._has_gpu = has_gpu
            calc._batched = batched
            calc._diarize = False
            calc._gpu_workers = 1 if has_gpu else 0
            calc._cpu_workers = 2
            calc._cpu_model = model
        return calc

    def test_returns_four_values(self):
        calc = self._make_calc(has_gpu=False, batched=False)
        result = calc._estimate_whisper_time(600)  # 10 minutes
        assert len(result) == 4  # (opt, con, whisper, diarize)

    def test_conservative_higher_than_optimistic(self):
        calc = self._make_calc(has_gpu=False, batched=False)
        opt, con, _, _ = calc._estimate_whisper_time(600)
        assert con > opt

    def test_conservative_is_1_4x_optimistic(self):
        calc = self._make_calc(has_gpu=False, batched=False)
        opt, con, _, _ = calc._estimate_whisper_time(600)
        assert abs(con - opt * 1.4) < 0.001

    def test_gpu_faster_than_cpu_only(self):
        calc_cpu = self._make_calc(has_gpu=False, batched=False)
        calc_gpu = self._make_calc(has_gpu=True, batched=False)

        opt_cpu, _, _, _ = calc_cpu._estimate_whisper_time(3600)
        opt_gpu, _, _, _ = calc_gpu._estimate_whisper_time(3600)
        assert opt_gpu < opt_cpu

    def test_zero_duration_returns_zero(self):
        calc = self._make_calc()
        opt, con, whisper, diarize = calc._estimate_whisper_time(0)
        assert opt == 0
        assert con == 0

    def test_diarize_tail_zero_when_disabled(self):
        calc = self._make_calc()
        calc._diarize = False
        _, _, _, diarize = calc._estimate_whisper_time(600)
        assert diarize == 0


# ── Ratio tables ────────────────────────────────────────────────────────────


class TestRatioTables:
    """Verify ratio tables are internally consistent."""

    def test_gpu_batched_faster_than_single(self):
        for model in ProcessingCalculator.WHISPER_RATIOS_GPU_BATCHED:
            batched = ProcessingCalculator.WHISPER_RATIOS_GPU_BATCHED[model]
            single = ProcessingCalculator.WHISPER_RATIOS_GPU_SINGLE[model]
            assert batched < single, f"GPU batched should be faster for {model}"

    def test_cpu_batched_faster_than_single(self):
        for model in ProcessingCalculator.WHISPER_RATIOS_CPU_BATCHED:
            batched = ProcessingCalculator.WHISPER_RATIOS_CPU_BATCHED[model]
            single = ProcessingCalculator.WHISPER_RATIOS_CPU_SINGLE[model]
            assert batched < single, f"CPU batched should be faster for {model}"

    def test_gpu_faster_than_cpu(self):
        for model in ProcessingCalculator.WHISPER_RATIOS_GPU_BATCHED:
            gpu = ProcessingCalculator.WHISPER_RATIOS_GPU_BATCHED[model]
            cpu = ProcessingCalculator.WHISPER_RATIOS_CPU_BATCHED[model]
            assert gpu < cpu, f"GPU should be faster than CPU for {model}"

    def test_larger_models_slower(self):
        order = ["tiny", "base", "small", "medium", "large"]
        gpu_ratios = ProcessingCalculator.WHISPER_RATIOS_GPU_BATCHED
        for i in range(len(order) - 1):
            assert gpu_ratios[order[i]] <= gpu_ratios[order[i + 1]], \
                f"{order[i]} should be faster than {order[i+1]}"


# ── format_estimate ─────────────────────────────────────────────────────────


class TestFormatEstimate:
    """Test the summary formatter."""

    def test_format_output_contains_file_count(self):
        calc = ProcessingCalculator.__new__(ProcessingCalculator)
        estimates = {
            "totals": {
                "total_files": 5,
                "total_time_minutes": 2.0,
                "total_time_range": (1.5, 2.5),
            }
        }
        result = calc.format_estimate(estimates)
        assert "5 files" in result

    def test_format_output_contains_time_range(self):
        calc = ProcessingCalculator.__new__(ProcessingCalculator)
        estimates = {
            "totals": {
                "total_files": 1,
                "total_time_minutes": 10.0,
                "total_time_range": (8.0, 12.0),
            }
        }
        result = calc.format_estimate(estimates)
        assert "-" in result  # contains range separator


# ── PDF / Image / Document time calc ────────────────────────────────────────


class TestSimpleTimeCalcs:
    """Test non-whisper time calculations."""

    def test_image_time_proportional_to_count(self):
        calc = ProcessingCalculator.__new__(ProcessingCalculator)
        result = calc.calculate_image_time([Path("a.jpg"), Path("b.png")])
        assert result["file_count"] == 2
        expected = 2 * ProcessingCalculator.IMAGE_SECONDS_EACH / 60.0
        assert abs(result["processing_time_minutes"] - expected) < 0.001

    def test_pdf_time_proportional_to_size(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"x" * (1024 * 1024))  # 1 MB

        calc = ProcessingCalculator.__new__(ProcessingCalculator)
        result = calc.calculate_pdf_time([f])
        assert result["file_count"] == 1
        assert abs(result["total_size_mb"] - 1.0) < 0.01

    def test_document_time_proportional_to_size(self, tmp_path):
        f = tmp_path / "notes.docx"
        f.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB

        calc = ProcessingCalculator.__new__(ProcessingCalculator)
        result = calc.calculate_document_time([f])
        assert result["file_count"] == 1
        assert abs(result["total_size_mb"] - 2.0) < 0.01
