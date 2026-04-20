"""Tests for config_loader.py — PipelineConfig and ConfigLoader."""

import json
import os
import tempfile
from pathlib import Path

import pytest

# Ensure backend/ is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config_loader import PipelineConfig, ConfigLoader


# ── PipelineConfig dataclass ────────────────────────────────────────────────


class TestPipelineConfigDefaults:
    """Verify default values are sensible."""

    def test_default_directories(self):
        c = PipelineConfig()
        assert c.source_directory == "Material"
        assert c.output_directory == "Transcriptions"

    def test_default_whisper_settings(self):
        c = PipelineConfig()
        assert c.whisper_model == "base"
        assert c.whisper_device == "auto"
        assert c.whisper_language == ""
        assert c.whisper_beam_size == 1
        assert c.whisper_diarize is False
        assert c.whisper_diarize_speakers == 0

    def test_default_processing_flags_all_true(self):
        c = PipelineConfig()
        for flag in (
            "process_audio", "process_videos", "process_pdf",
            "process_docx", "process_xlsx", "process_pptx",
            "process_images", "process_txt", "process_csv", "process_rtf",
        ):
            assert getattr(c, flag) is True, f"{flag} should default to True"

    def test_default_performance(self):
        c = PipelineConfig()
        assert c.max_parallel_workers == 3
        assert c.enable_caching is True
        assert c.enable_deduplication is True
        assert c.enable_checkpointing is True

    def test_default_log_level(self):
        c = PipelineConfig()
        assert c.log_level == "INFO"


class TestPipelineConfigSerialization:
    """Round-trip dict serialization."""

    def test_to_dict_returns_all_fields(self):
        c = PipelineConfig()
        d = c.to_dict()
        assert isinstance(d, dict)
        assert "whisper_model" in d
        assert "source_directory" in d

    def test_from_dict_round_trip(self):
        original = PipelineConfig(whisper_model="large-v3", max_parallel_workers=8)
        d = original.to_dict()
        restored = PipelineConfig.from_dict(d)
        assert restored.whisper_model == "large-v3"
        assert restored.max_parallel_workers == 8

    def test_from_dict_ignores_unknown_keys(self):
        data = {"whisper_model": "small", "nonexistent_key": 42}
        c = PipelineConfig.from_dict(data)
        assert c.whisper_model == "small"
        assert not hasattr(c, "nonexistent_key")

    def test_from_dict_partial_uses_defaults(self):
        data = {"whisper_model": "medium"}
        c = PipelineConfig.from_dict(data)
        assert c.whisper_model == "medium"
        assert c.source_directory == "Material"  # default preserved


# ── ConfigLoader ────────────────────────────────────────────────────────────


class TestConfigLoaderLoad:
    """Test loading from file, missing file, bad JSON."""

    def test_load_defaults_when_no_file(self, tmp_path):
        loader = ConfigLoader(config_file=str(tmp_path / "missing.json"))
        config = loader.load()
        assert config.whisper_model == "base"

    def test_load_from_valid_file(self, tmp_path):
        settings = {"whisper_model": "large-v2", "max_parallel_workers": 6}
        cfg_file = tmp_path / ".pipeline_settings.json"
        cfg_file.write_text(json.dumps(settings), encoding="utf-8")

        loader = ConfigLoader(config_file=str(cfg_file))
        config = loader.load()
        assert config.whisper_model == "large-v2"
        assert config.max_parallel_workers == 6

    def test_load_bad_json_falls_back_to_defaults(self, tmp_path):
        cfg_file = tmp_path / ".pipeline_settings.json"
        cfg_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

        loader = ConfigLoader(config_file=str(cfg_file))
        config = loader.load()
        assert config.whisper_model == "base"  # defaults


class TestConfigLoaderValidation:
    """Test the _validate method catches bad values."""

    def test_invalid_whisper_model_reset_to_base(self, tmp_path):
        settings = {"whisper_model": "nonexistent-v99"}
        cfg_file = tmp_path / ".pipeline_settings.json"
        cfg_file.write_text(json.dumps(settings), encoding="utf-8")

        config = ConfigLoader(config_file=str(cfg_file)).load()
        assert config.whisper_model == "base"

    def test_invalid_log_level_reset_to_info(self, tmp_path):
        settings = {"log_level": "VERBOSE"}
        cfg_file = tmp_path / ".pipeline_settings.json"
        cfg_file.write_text(json.dumps(settings), encoding="utf-8")

        config = ConfigLoader(config_file=str(cfg_file)).load()
        assert config.log_level == "INFO"

    def test_negative_workers_reset_to_default(self, tmp_path):
        settings = {"max_parallel_workers": -1}
        cfg_file = tmp_path / ".pipeline_settings.json"
        cfg_file.write_text(json.dumps(settings), encoding="utf-8")

        config = ConfigLoader(config_file=str(cfg_file)).load()
        assert config.max_parallel_workers == 3

    def test_zero_workers_reset_to_default(self, tmp_path):
        settings = {"max_parallel_workers": 0}
        cfg_file = tmp_path / ".pipeline_settings.json"
        cfg_file.write_text(json.dumps(settings), encoding="utf-8")

        config = ConfigLoader(config_file=str(cfg_file)).load()
        assert config.max_parallel_workers == 3

    def test_valid_models_accepted(self, tmp_path):
        for model in ("tiny", "base", "small", "medium", "large", "large-v2", "large-v3"):
            settings = {"whisper_model": model}
            cfg_file = tmp_path / ".pipeline_settings.json"
            cfg_file.write_text(json.dumps(settings), encoding="utf-8")

            config = ConfigLoader(config_file=str(cfg_file)).load()
            assert config.whisper_model == model


class TestConfigLoaderEnvOverride:
    """Test environment variable overrides."""

    def test_log_level_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")
        config = ConfigLoader(config_file=str(tmp_path / "missing.json")).load()
        assert config.log_level == "DEBUG"

    def test_invalid_env_log_level_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
        config = ConfigLoader(config_file=str(tmp_path / "missing.json")).load()
        assert config.log_level == "INFO"  # unchanged


class TestConfigLoaderSave:
    """Test save/reload round-trip."""

    def test_save_and_reload(self, tmp_path):
        cfg_file = tmp_path / "settings.json"
        original = PipelineConfig(whisper_model="medium", max_parallel_workers=5)

        loader = ConfigLoader(config_file=str(cfg_file))
        loader.save(original)

        loaded = loader.load()
        assert loaded.whisper_model == "medium"
        assert loaded.max_parallel_workers == 5
