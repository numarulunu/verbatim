"""Tests for process_v2.py — sanitize_filename, file dispatch, output paths, find_materials."""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pre-mock heavy dependencies that process_v2 imports transitively
# (numpy, torch, pyannote, faster_whisper, etc. are not available in test env)
_MOCK_MODULES = [
    "numpy", "torch", "torch.cuda",
    "faster_whisper", "faster_whisper.transcribe",
    "pyannote", "pyannote.audio", "pyannote.audio.pipelines",
    "psutil",
    "PIL", "PIL.Image",
]
for _mod_name in _MOCK_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Mock psutil specifically so process_v2 can call psutil.cpu_count()
sys.modules["psutil"].cpu_count = MagicMock(return_value=4)

from process_v2 import (
    sanitize_filename,
    AUDIO_EXTS, VIDEO_EXTS, IMAGE_EXTS, DOC_EXTS,
    MaterialProcessor,
)
from core.config_loader import PipelineConfig


# ── sanitize_filename ───────────────────────────────────────────────────────


class TestSanitizeFilename:
    """Test the filename sanitizer for cross-platform safety."""

    def test_normal_filename_unchanged(self):
        assert sanitize_filename("lecture_01") == "lecture_01"

    def test_strips_invalid_windows_chars(self):
        result = sanitize_filename('file<>:"/\\|?*name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_strips_control_characters(self):
        result = sanitize_filename("file\x00\x1fname")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_strips_leading_trailing_dots_and_spaces(self):
        assert sanitize_filename("  ..name.. ") == "name"

    def test_collapses_multiple_spaces(self):
        assert sanitize_filename("a   b   c") == "a b c"

    def test_reserved_windows_names_prefixed(self):
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("NUL") == "_NUL"
        assert sanitize_filename("COM1") == "_COM1"
        assert sanitize_filename("LPT3") == "_LPT3"

    def test_reserved_names_case_insensitive(self):
        result = sanitize_filename("con")
        assert result == "_con"

    def test_long_filename_truncated(self):
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        assert len(result) <= 240

    def test_empty_after_sanitization_returns_unnamed(self):
        assert sanitize_filename("...") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"

    def test_unicode_preserved(self):
        assert sanitize_filename("lecție_română") == "lecție_română"


# ── Extension sets ──────────────────────────────────────────────────────────


class TestExtensionSets:
    """Verify the format extension sets are complete."""

    def test_audio_includes_common_formats(self):
        for ext in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
            assert ext in AUDIO_EXTS

    def test_video_includes_common_formats(self):
        for ext in (".mp4", ".avi", ".mkv", ".mov", ".webm"):
            assert ext in VIDEO_EXTS

    def test_image_includes_common_formats(self):
        for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff"):
            assert ext in IMAGE_EXTS

    def test_doc_includes_office_formats(self):
        for ext in (".docx", ".xlsx", ".pptx", ".csv", ".txt", ".rtf"):
            assert ext in DOC_EXTS


# ── MaterialProcessor._get_output_path ──────────────────────────────────────


class TestGetOutputPath:
    """Test output path generation with folder structure preservation."""

    def _make_processor(self):
        config = PipelineConfig()
        with patch("process_v2.DocumentProcessor"), \
             patch("process_v2.EnhancedOCR"):
            proc = MaterialProcessor(config)
        return proc

    def test_flat_file_produces_txt_in_output_dir(self, tmp_path):
        proc = self._make_processor()
        proc.source_dir = None

        source = tmp_path / "lecture.mp3"
        source.touch()
        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = proc._get_output_path(source, output_dir)
        assert result.suffix == ".txt"
        assert result.parent == output_dir / "."
        assert result.stem == "lecture"

    def test_preserves_subdirectory_structure(self, tmp_path):
        proc = self._make_processor()
        source_dir = tmp_path / "Material"
        sub = source_dir / "Week1" / "Day2"
        sub.mkdir(parents=True)
        source_file = sub / "audio.mp3"
        source_file.touch()

        proc.source_dir = source_dir.resolve()
        output_dir = tmp_path / "Transcriptions"
        output_dir.mkdir()

        result = proc._get_output_path(source_file, output_dir)
        assert "Week1" in str(result)
        assert "Day2" in str(result)
        assert result.name == "audio.txt"

    def test_sanitizes_stem(self, tmp_path):
        proc = self._make_processor()
        proc.source_dir = None

        source = tmp_path / 'bad<>name.mp3'
        # Can't create file with bad chars on Windows, so test the logic directly
        # by using a mock path
        mock_path = MagicMock(spec=Path)
        mock_path.resolve.return_value = tmp_path / "badname.mp3"
        mock_path.stem = 'bad<>name'
        mock_path.suffix = '.mp3'

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = proc._get_output_path(mock_path, output_dir)
        assert "<" not in result.stem
        assert ">" not in result.stem


# ── MaterialProcessor.find_materials ────────────────────────────────────────


class TestFindMaterials:
    """Test file discovery and classification."""

    def _make_processor(self, **overrides):
        defaults = {}
        defaults.update(overrides)
        config = PipelineConfig(**defaults)
        with patch("process_v2.DocumentProcessor"), \
             patch("process_v2.EnhancedOCR"):
            proc = MaterialProcessor(config)
        return proc

    def _populate(self, tmp_path):
        """Create a small test directory with various file types."""
        (tmp_path / "lecture.mp3").touch()
        (tmp_path / "interview.wav").touch()
        (tmp_path / "talk.mp4").touch()
        (tmp_path / "slides.pdf").touch()
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "notes.docx").touch()
        (tmp_path / "data.csv").touch()
        (tmp_path / "readme.txt").touch()

    def test_finds_all_types(self, tmp_path):
        self._populate(tmp_path)
        proc = self._make_processor()
        materials = proc.find_materials(tmp_path)

        assert len(materials["audio"]) == 2
        assert len(materials["videos"]) == 1
        assert len(materials["pdfs"]) == 1
        assert len(materials["images"]) == 1
        assert len(materials["documents"]) == 3  # docx, csv, txt

    def test_respects_disabled_flags(self, tmp_path):
        self._populate(tmp_path)
        proc = self._make_processor(process_audio=False, process_videos=False)
        materials = proc.find_materials(tmp_path)

        assert len(materials["audio"]) == 0
        assert len(materials["videos"]) == 0
        # Other types still found
        assert len(materials["pdfs"]) == 1

    def test_nonexistent_directory_returns_empty(self, tmp_path):
        proc = self._make_processor()
        materials = proc.find_materials(tmp_path / "nonexistent")

        for file_list in materials.values():
            assert len(file_list) == 0

    def test_finds_files_in_subdirectories(self, tmp_path):
        sub = tmp_path / "sub1" / "sub2"
        sub.mkdir(parents=True)
        (sub / "deep.mp3").touch()

        proc = self._make_processor()
        materials = proc.find_materials(tmp_path)
        assert len(materials["audio"]) == 1

    def test_ignores_unsupported_extensions(self, tmp_path):
        (tmp_path / "archive.zip").touch()
        (tmp_path / "binary.exe").touch()
        (tmp_path / "database.db").touch()

        proc = self._make_processor()
        materials = proc.find_materials(tmp_path)
        total = sum(len(v) for v in materials.values())
        assert total == 0


# ── MaterialProcessor._dispatch_file ────────────────────────────────────────


class TestDispatchFile:
    """Test that _dispatch_file routes to the correct processor."""

    def _make_processor(self):
        config = PipelineConfig()
        with patch("process_v2.DocumentProcessor") as mock_doc, \
             patch("process_v2.EnhancedOCR") as mock_ocr:
            proc = MaterialProcessor(config)
        # Replace processors with mocks
        proc.process_audio = MagicMock(return_value={"text": "hello"})
        proc.process_video = MagicMock(return_value={"text": "world"})
        proc.process_pdf = MagicMock(return_value="pdf text")
        proc.process_image = MagicMock(return_value="image text")
        proc.process_document = MagicMock(return_value="doc text")
        return proc

    def test_dispatch_audio(self, tmp_path):
        proc = self._make_processor()
        result, text = proc._dispatch_file(Path("f.mp3"), "audio", tmp_path)
        assert result == {"text": "hello"}
        assert text is None
        proc.process_audio.assert_called_once()

    def test_dispatch_video(self, tmp_path):
        proc = self._make_processor()
        result, text = proc._dispatch_file(Path("f.mp4"), "video", tmp_path)
        assert result == {"text": "world"}
        assert text is None
        proc.process_video.assert_called_once()

    def test_dispatch_pdf(self, tmp_path):
        proc = self._make_processor()
        result, text = proc._dispatch_file(Path("f.pdf"), "pdf", tmp_path)
        assert result is None
        assert text == "pdf text"

    def test_dispatch_image(self, tmp_path):
        proc = self._make_processor()
        result, text = proc._dispatch_file(Path("f.jpg"), "image", tmp_path)
        assert result is None
        assert text == "image text"

    def test_dispatch_document(self, tmp_path):
        proc = self._make_processor()
        result, text = proc._dispatch_file(Path("f.docx"), "document", tmp_path)
        assert result is None
        assert text == "doc text"

    def test_dispatch_unknown_returns_none(self, tmp_path):
        proc = self._make_processor()
        result, text = proc._dispatch_file(Path("f.xyz"), "unknown", tmp_path)
        assert result is None
        assert text is None


# ── MaterialProcessor._transcribe_with_retry ────────────────────────────────


class TestTranscribeWithRetry:
    """Test retry logic without actual GPU/whisper."""

    def _make_processor(self):
        config = PipelineConfig()
        with patch("process_v2.DocumentProcessor"), \
             patch("process_v2.EnhancedOCR"):
            proc = MaterialProcessor(config)
        proc.whisper_pool = MagicMock()
        return proc

    def test_success_on_first_attempt(self):
        proc = self._make_processor()
        proc.whisper_pool.transcribe.return_value = {"text": "ok"}

        result = proc._transcribe_with_retry(Path("test.mp3"), max_retries=2)
        assert result == {"text": "ok"}
        assert proc.whisper_pool.transcribe.call_count == 1

    def test_retries_on_oom_then_succeeds(self):
        proc = self._make_processor()
        oom_error = RuntimeError("CUDA out of memory")
        proc.whisper_pool.transcribe.side_effect = [oom_error, {"text": "recovered"}]

        with patch("time.sleep"):  # skip the 2s wait
            result = proc._transcribe_with_retry(Path("test.mp3"), max_retries=2)
        assert result == {"text": "recovered"}
        assert proc.whisper_pool.transcribe.call_count == 2

    def test_raises_after_max_retries_on_oom(self):
        proc = self._make_processor()
        oom_error = RuntimeError("CUDA out of memory")
        proc.whisper_pool.transcribe.side_effect = oom_error

        with patch("time.sleep"), pytest.raises(RuntimeError, match="out of memory"):
            proc._transcribe_with_retry(Path("test.mp3"), max_retries=2)

    def test_non_transient_error_raises_immediately(self):
        proc = self._make_processor()
        proc.whisper_pool.transcribe.side_effect = ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            proc._transcribe_with_retry(Path("test.mp3"), max_retries=3)
        assert proc.whisper_pool.transcribe.call_count == 1


# ── MaterialProcessor._log_error / stats ────────────────────────────────────


class TestErrorTracking:
    """Test thread-safe error logging."""

    def _make_processor(self):
        config = PipelineConfig()
        with patch("process_v2.DocumentProcessor"), \
             patch("process_v2.EnhancedOCR"):
            proc = MaterialProcessor(config)
        return proc

    def test_log_error_appends(self):
        proc = self._make_processor()
        proc._log_error(Path("file.mp3"), "something broke")
        assert len(proc._errors) == 1
        assert proc._errors[0] == ("file.mp3", "something broke")

    def test_log_error_thread_safe(self):
        proc = self._make_processor()
        threads = []
        for i in range(50):
            t = threading.Thread(target=proc._log_error, args=(Path(f"f{i}.mp3"), f"err{i}"))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert len(proc._errors) == 50
