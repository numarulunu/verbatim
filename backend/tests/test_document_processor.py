"""Tests for document_processor.py — format routing, TXT/CSV extraction, error handling."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.document_processor import (
    DocumentProcessor,
    DocumentProcessingError,
    UnsupportedFormatError,
    MissingDependencyError,
)


# ── Format routing ──────────────────────────────────────────────────────────


class TestFormatRouting:
    """Test extract_text dispatches to the right handler."""

    def test_unsupported_extension_raises(self, tmp_path):
        (tmp_path / "file.xyz").touch()
        proc = DocumentProcessor()
        with pytest.raises(UnsupportedFormatError, match="Unsupported format"):
            proc.extract_text(str(tmp_path / "file.xyz"))

    def test_missing_file_raises(self):
        proc = DocumentProcessor()
        with pytest.raises(FileNotFoundError):
            proc.extract_text("/nonexistent/path/file.txt")

    def test_is_supported_true_for_known_formats(self):
        proc = DocumentProcessor()
        for ext in (".docx", ".xlsx", ".xls", ".pptx", ".txt", ".rtf", ".csv"):
            assert proc.is_supported(f"file{ext}") is True

    def test_is_supported_false_for_unknown(self):
        proc = DocumentProcessor()
        assert proc.is_supported("file.zip") is False
        assert proc.is_supported("file.exe") is False
        assert proc.is_supported("file.pdf") is False  # PDF handled separately


# ── TXT extraction ──────────────────────────────────────────────────────────


class TestTxtExtraction:
    """Test plain text file reading with encoding fallback."""

    def test_utf8_file(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("hello world", encoding="utf-8")

        proc = DocumentProcessor()
        text = proc.extract_text(str(f))
        assert text == "hello world"

    def test_latin1_file(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_bytes("caf\xe9".encode("latin-1"))

        proc = DocumentProcessor()
        text = proc.extract_text(str(f))
        assert "caf" in text

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")

        proc = DocumentProcessor()
        text = proc.extract_text(str(f))
        assert text == ""


# ── CSV extraction ──────────────────────────────────────────────────────────


class TestCsvExtraction:
    """Test CSV text extraction."""

    def test_basic_csv(self, tmp_path):
        f = tmp_path / "data.csv"
        with open(f, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Name", "Score"])
            writer.writerow(["Alice", "95"])
            writer.writerow(["Bob", "87"])

        proc = DocumentProcessor()
        text = proc.extract_text(str(f))
        assert "Alice" in text
        assert "Bob" in text
        assert "95" in text

    def test_csv_uses_pipe_separator(self, tmp_path):
        f = tmp_path / "data.csv"
        with open(f, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["A", "B"])

        proc = DocumentProcessor()
        text = proc.extract_text(str(f))
        assert "|" in text

    def test_empty_csv(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("", encoding="utf-8")

        proc = DocumentProcessor()
        text = proc.extract_text(str(f))
        assert text == ""


# ── Metadata ────────────────────────────────────────────────────────────────


class TestMetadata:
    """Test basic metadata extraction."""

    def test_metadata_returns_filename_and_size(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content here", encoding="utf-8")

        proc = DocumentProcessor()
        meta = proc.get_metadata(str(f))
        assert meta["filename"] == "test.txt"
        assert meta["extension"] == ".txt"
        assert meta["size_bytes"] > 0
