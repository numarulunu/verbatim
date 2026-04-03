"""
Configuration Loader - Load and validate pipeline settings

Features:
- Load from .pipeline_settings.json
- Validate all settings
- Provide sensible defaults
- Type checking
- Model name validation

Supports configuration for:
- Input/output directories
- Model selection
- File type filters
- Processing options
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

from .quiet import quiet_print


@dataclass
class PipelineConfig:
    """
    Pipeline configuration

    All pipeline settings with type hints and defaults
    """

    # Directories
    source_directory: str = "Material"
    output_directory: str = "Transcriptions"

    # Processing Options
    process_audio: bool = True
    process_videos: bool = True
    process_pdf: bool = True
    process_docx: bool = True
    process_xlsx: bool = True
    process_pptx: bool = True
    process_images: bool = True
    process_txt: bool = True
    process_csv: bool = True
    process_rtf: bool = True

    # Whisper Settings
    whisper_model: str = "base"  # tiny, base, small, medium, large
    whisper_device: str = "auto"  # auto, cuda, cpu
    whisper_language: str = ""  # e.g. "ro", "en" — empty = auto-detect (costs ~30s per file)
    whisper_beam_size: int = 1  # 1 = greedy (fast), 5 = beam search (slower, slightly better)
    whisper_diarize: bool = False  # Tag different speakers (requires pyannote.audio)
    whisper_diarize_speakers: int = 0  # Expected speaker count (0 = auto-detect, 2 = faster for 2-person recordings)

    # Performance
    max_parallel_workers: int = 3
    enable_caching: bool = True
    enable_deduplication: bool = True
    enable_checkpointing: bool = True

    # Advanced
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Checkpoint
    checkpoint_file: str = "pipeline_checkpoint.json"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineConfig':
        """Create from dictionary"""
        # Filter out keys that don't exist in dataclass
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigLoader:
    """
    Load and validate pipeline configuration

    Loads from .pipeline_settings.json and validates all settings
    """

    VALID_WHISPER_MODELS = {
        "tiny", "base", "small", "medium", "large", "large-v2", "large-v3"
    }

    VALID_LOG_LEVELS = {
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    }

    def __init__(self, config_file: str = ".pipeline_settings.json"):
        """
        Initialize config loader

        Args:
            config_file: Path to config file
        """
        self.config_file = Path(config_file)

    def load(self) -> PipelineConfig:
        """
        Load configuration

        Returns:
            PipelineConfig with validated settings
        """
        # Start with defaults
        config = PipelineConfig()

        # Load from file if exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                config = PipelineConfig.from_dict(data)
                quiet_print(f" Loaded config from {self.config_file}")

            except Exception as e:
                quiet_print(f"Warning Failed to load config: {e}")
                quiet_print("  Using default configuration")

        # Validate and fix issues
        config = self._validate(config)

        # Override with environment variables
        config = self._apply_env_overrides(config)

        return config

    def _validate(self, config: PipelineConfig) -> PipelineConfig:
        """
        Validate configuration and fix issues

        Args:
            config: Configuration to validate

        Returns:
            Validated configuration
        """
        # Validate Whisper model
        if config.whisper_model not in self.VALID_WHISPER_MODELS:
            quiet_print(f"Warning: Invalid Whisper model '{config.whisper_model}', using 'base'")
            config.whisper_model = "base"

        # Validate log level
        if config.log_level not in self.VALID_LOG_LEVELS:
            quiet_print(f"Warning: Invalid log level '{config.log_level}', using 'INFO'")
            config.log_level = "INFO"

        # Validate directories exist (create if not)
        if config.source_directory:
            source_path = Path(config.source_directory)
            if not source_path.exists():
                quiet_print(f"Warning: Source directory '{config.source_directory}' doesn't exist, using current directory")
                config.source_directory = "."

        # Create output directory if it doesn't exist
        output_path = Path(config.output_directory)
        output_path.mkdir(parents=True, exist_ok=True)

        # Validate numeric ranges
        if config.max_parallel_workers < 1:
            quiet_print(f"Warning: Invalid max_parallel_workers={config.max_parallel_workers}, using 3")
            config.max_parallel_workers = 3

        return config

    def _apply_env_overrides(self, config: PipelineConfig) -> PipelineConfig:
        """
        Apply environment variable overrides

        Env vars take precedence over config file

        Args:
            config: Base configuration

        Returns:
            Configuration with env overrides
        """
        # Log level override
        if os.getenv('LOG_LEVEL'):
            level = os.getenv('LOG_LEVEL').upper()
            if level in self.VALID_LOG_LEVELS:
                config.log_level = level

        return config

    def save(self, config: PipelineConfig):
        """
        Save configuration to file

        Args:
            config: Configuration to save
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2)

            quiet_print(f" Saved config to {self.config_file}")

        except Exception as e:
            quiet_print(f"Warning Failed to save config: {e}")


# Convenience functions
def load_config(config_file: str = ".pipeline_settings.json") -> PipelineConfig:
    """
    Load pipeline configuration

    Args:
        config_file: Path to config file

    Returns:
        Validated configuration
    """
    loader = ConfigLoader(config_file)
    return loader.load()


def save_config(config: PipelineConfig, config_file: str = ".pipeline_settings.json"):
    """
    Save pipeline configuration

    Args:
        config: Configuration to save
        config_file: Path to config file
    """
    loader = ConfigLoader(config_file)
    loader.save(config)
