# Transcriptor v2

Local-first transcription and document processing pipeline. Uses faster-whisper for GPU-accelerated audio/video transcription, Tesseract OCR for images, and PyMuPDF for PDFs — with a Flask web interface for batch processing and real-time progress tracking.

## Requirements

- Python 3.10+
- FFmpeg (for audio/video processing)
- Tesseract OCR (for image text extraction)
- CUDA-capable GPU recommended (CPU fallback available)
- Dependencies: see `requirements.txt`

## Quick Start

```bash
pip install -r requirements.txt
cd backend
python api_server.py
# Open http://localhost:5000 in browser
```
