"""Tests for quiet.py — quiet mode gating and log level detection."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.quiet import is_quiet, quiet_print, set_log_callback


class TestIsQuiet:
    """Test the quiet mode environment variable check."""

    def test_quiet_when_set(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_QUIET", "1")
        assert is_quiet() is True

    def test_not_quiet_when_unset(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        assert is_quiet() is False

    def test_not_quiet_when_other_value(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_QUIET", "0")
        assert is_quiet() is False

    def test_not_quiet_when_empty(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_QUIET", "")
        assert is_quiet() is False


class TestQuietPrint:
    """Test quiet_print output suppression and callback routing."""

    def test_suppresses_output_in_quiet_mode(self, monkeypatch, capsys):
        monkeypatch.setenv("PIPELINE_QUIET", "1")
        quiet_print("this should be hidden")
        captured = capsys.readouterr()
        assert "this should be hidden" not in captured.out

    def test_prints_output_in_normal_mode(self, monkeypatch, capsys):
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        quiet_print("visible message")
        captured = capsys.readouterr()
        assert "visible message" in captured.out

    def test_error_flag_forces_print_in_quiet_mode(self, monkeypatch, capsys):
        monkeypatch.setenv("PIPELINE_QUIET", "1")
        quiet_print("fatal error", error=True)
        captured = capsys.readouterr()
        assert "fatal error" in captured.out

    def test_callback_receives_messages(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        callback = MagicMock()
        set_log_callback(callback)
        try:
            quiet_print("test message")
            callback.assert_called_once()
            args = callback.call_args[0]
            assert "test message" in args[0]
        finally:
            set_log_callback(None)

    def test_callback_error_does_not_crash(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        set_log_callback(lambda msg, lvl: 1 / 0)  # raises ZeroDivisionError
        try:
            quiet_print("should not crash")  # should not raise
        finally:
            set_log_callback(None)

    def test_error_level_detected(self, monkeypatch):
        callback = MagicMock()
        set_log_callback(callback)
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        try:
            quiet_print("[ERROR] something broke")
            args = callback.call_args[0]
            assert args[1] == "ERROR"
        finally:
            set_log_callback(None)

    def test_warn_level_detected(self, monkeypatch):
        callback = MagicMock()
        set_log_callback(callback)
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        try:
            quiet_print("Warning: low disk space")
            args = callback.call_args[0]
            assert args[1] == "WARN"
        finally:
            set_log_callback(None)

    def test_success_level_detected(self, monkeypatch):
        callback = MagicMock()
        set_log_callback(callback)
        monkeypatch.delenv("PIPELINE_QUIET", raising=False)
        try:
            quiet_print("[SUCCESS] all done")
            args = callback.call_args[0]
            assert args[1] == "SUCCESS"
        finally:
            set_log_callback(None)
