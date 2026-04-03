"""
Speaker Diarization - Tag transcript segments with speaker labels

Uses pyannote.audio v4 for speaker detection, then maps speaker segments
onto Whisper transcript segments by timestamp overlap.

Requires:
  pip install pyannote.audio
  HF_TOKEN environment variable with HuggingFace access token
  Accept terms at huggingface.co/pyannote/speaker-diarization-3.1
"""

import os
import sys
import subprocess
import tempfile
import threading
import warnings
import wave
from typing import List, Dict, Optional
from pathlib import Path

import numpy as np

from .quiet import quiet_print

_PYANNOTE_AVAILABLE = False
try:
    # Suppress all pyannote warnings (torchcodec, TF32, std() degrees of freedom)
    warnings.filterwarnings("ignore", module=r"pyannote\..*")
    warnings.filterwarnings("ignore", message=".*torchcodec.*")
    warnings.filterwarnings("ignore", message=".*TensorFloat.*")
    warnings.filterwarnings("ignore", message=".*degrees of freedom.*")
    _original_warn = warnings.warn
    def _quiet_warn(message, *args, **kwargs):
        msg = str(message)
        if any(s in msg for s in ('torchcodec', 'TensorFloat', 'TF32', 'degrees of freedom', 'std()')):
            return
        _original_warn(message, *args, **kwargs)
    warnings.warn = _quiet_warn
    from pyannote.audio import Pipeline as PyannotePipeline
    _PYANNOTE_AVAILABLE = True
except ImportError:
    warnings.warn = _original_warn if '_original_warn' in dir() else warnings.warn


def is_available() -> bool:
    return _PYANNOTE_AVAILABLE


def get_hf_token() -> Optional[str]:
    return os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")


class Diarizer:
    """Speaker diarization using pyannote.audio, running on CPU to free GPU for whisper.

    Uses a Semaphore instead of Lock to allow concurrent diarizations (default: 2).
    Runs on CPU so GPU stays 100% dedicated to whisper transcription.
    """

    _instance = None
    _init_lock = threading.Lock()

    # Allow N concurrent diarizations on CPU (RAM-limited, not compute-limited)
    MAX_CONCURRENT = 2

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self, token: str = None, device: str = "auto") -> bool:
        with self._init_lock:
            if self._initialized:
                return True

            if not _PYANNOTE_AVAILABLE:
                quiet_print("Warning: pyannote.audio not installed.", error=True)
                return False

            hf_token = token or get_hf_token()
            if not hf_token:
                quiet_print("Warning: HF_TOKEN not set. Speaker diarization disabled.", error=True)
                return False

            try:
                self._pipeline = PyannotePipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=hf_token,
                )

                # Default to CPU at init (whisper owns GPU during phase 1)
                # process_v2 moves this to GPU in phase 2 after whisper is done
                import torch
                if device == "auto":
                    device = "cpu"
                self._pipeline.to(torch.device(device))

                self._semaphore = threading.Semaphore(self.MAX_CONCURRENT)
                self._initialized = True
                return True

            except Exception as e:
                quiet_print(f"Warning: Failed to load diarization model: {e}", error=True)
                return False

    def diarize(self, media_path: str, num_speakers: int = 0) -> List[Dict]:
        """Run speaker diarization on an audio/video file.

        Args:
            media_path: Path to audio/video file
            num_speakers: Expected number of speakers (0 = auto-detect, 2 = much faster)

        Returns list of segments: [{'start': float, 'end': float, 'speaker': str}, ...]
        """
        if not self._initialized:
            return []

        self._semaphore.acquire()
        try:
            import torch

            wav_path = self._extract_wav(media_path)
            if not wav_path:
                quiet_print("Warning: Could not extract audio for diarization")
                return []

            try:
                with wave.open(wav_path, 'rb') as wf:
                    sr = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                    waveform = torch.from_numpy(audio).unsqueeze(0)

                # Build pipeline kwargs
                kwargs = {}
                if num_speakers > 0:
                    kwargs['num_speakers'] = num_speakers

                result = self._pipeline({"waveform": waveform, "sample_rate": sr}, **kwargs)

                # pyannote 3.x returns Annotation directly
                # Some versions may wrap it (e.g. result.speaker_diarization)
                if hasattr(result, 'itertracks'):
                    annotation = result
                elif hasattr(result, 'speaker_diarization'):
                    annotation = result.speaker_diarization
                else:
                    annotation = result

                segments = []
                for turn, _, speaker in annotation.itertracks(yield_label=True):
                    segments.append({
                        'start': turn.start,
                        'end': turn.end,
                        'speaker': speaker,
                    })
                return segments
            finally:
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass

        except Exception as e:
            quiet_print(f"Warning: Diarization failed: {e}")
            return []
        finally:
            self._semaphore.release()

    @staticmethod
    def _extract_wav(media_path: str) -> Optional[str]:
        """Extract audio to a temporary high-quality WAV for speaker distinction."""
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp.close()
            cmd = [
                'ffmpeg', '-loglevel', 'error',
                '-i', media_path,
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',  # 16kHz — native sample rate for pyannote models
                '-y', tmp.name,
            ]
            subprocess.run(
                cmd, capture_output=True, check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            return tmp.name
        except Exception:
            return None


def assign_speakers_to_words(words: List[Dict], speaker_segments: List[Dict],
                             min_speaker_seconds: float = 3.0) -> List[Dict]:
    """Assign speaker labels to individual words by timestamp, then smooth by time.

    1. Match each word to the speaker segment covering its midpoint
    2. Words in gaps inherit the previous word's speaker (continuity)
    3. Time-based smoothing: speaker runs shorter than min_speaker_seconds
       get absorbed into the surrounding speaker. This eliminates the
       mid-conversation flips where pyannote briefly assigns the wrong speaker.
    """
    if not speaker_segments or not words:
        return words

    sorted_speakers = sorted(speaker_segments, key=lambda s: s['start'])

    # Pass 1: assign each word to a speaker by midpoint
    prev_speaker = sorted_speakers[0]['speaker'] if sorted_speakers else None
    for word in words:
        wm = (word['start'] + word['end']) / 2.0
        matched = None

        for sseg in sorted_speakers:
            if sseg['end'] < word['start'] - 0.5:
                continue
            if sseg['start'] > word['end'] + 0.5:
                break
            if sseg['start'] <= wm <= sseg['end']:
                matched = sseg['speaker']
                break

        if matched:
            word['speaker'] = matched
            prev_speaker = matched
        else:
            word['speaker'] = prev_speaker or sorted_speakers[0]['speaker']

    # Pass 2: time-based smoothing — absorb short speaker runs
    if len(words) < 2:
        return words

    # Build runs: [(speaker, start_idx, end_idx, start_time, end_time), ...]
    runs = []
    run_start = 0
    for i in range(1, len(words)):
        if words[i]['speaker'] != words[run_start]['speaker']:
            runs.append((
                words[run_start]['speaker'], run_start, i,
                words[run_start]['start'], words[i - 1]['end'],
            ))
            run_start = i
    runs.append((
        words[run_start]['speaker'], run_start, len(words),
        words[run_start]['start'], words[-1]['end'],
    ))

    # Multiple smoothing passes until stable (short runs can create new short runs)
    changed = True
    while changed:
        changed = False
        new_runs = []
        for idx, (speaker, start, end, t_start, t_end) in enumerate(runs):
            duration = t_end - t_start
            if duration < min_speaker_seconds:
                # Find the longer adjacent run and absorb into it
                prev_dur = (new_runs[-1][4] - new_runs[-1][3]) if new_runs else 0
                next_dur = (runs[idx + 1][4] - runs[idx + 1][3]) if idx < len(runs) - 1 else 0

                if prev_dur >= next_dur and new_runs:
                    # Merge into previous run
                    prev = new_runs[-1]
                    new_runs[-1] = (prev[0], prev[1], end, prev[3], t_end)
                    changed = True
                elif idx < len(runs) - 1:
                    # Merge into next run
                    nxt = runs[idx + 1]
                    runs[idx + 1] = (nxt[0], start, nxt[2], t_start, nxt[4])
                    changed = True
                else:
                    new_runs.append((speaker, start, end, t_start, t_end))
            else:
                new_runs.append((speaker, start, end, t_start, t_end))
        runs = new_runs

    # Apply smoothed labels back to words
    for speaker, start, end, _, _ in runs:
        for j in range(start, end):
            words[j]['speaker'] = speaker

    return words


def assign_speakers(whisper_segments: List[Dict], speaker_segments: List[Dict]) -> List[Dict]:
    """Fallback: map speaker labels onto whisper segments by timestamp overlap.
    Used when word-level timestamps are not available.
    """
    if not speaker_segments:
        return whisper_segments

    for wseg in whisper_segments:
        best_speaker = None
        best_overlap = 0.0
        ws, we = wseg['start'], wseg['end']
        for sseg in speaker_segments:
            overlap = max(0.0, min(we, sseg['end']) - max(ws, sseg['start']))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = sseg['speaker']
        wseg['speaker'] = best_speaker or "Unknown"

    return whisper_segments


def _fmt_ts(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_diarized_transcript(words: List[Dict] = None, segments: List[Dict] = None) -> str:
    """Format speaker-tagged words or segments into readable text with timestamps.

    Uses word-level data if available (much sharper speaker transitions).
    Falls back to segment-level if words not provided.

    Output:
        [00:00:00] [Speaker 1]
        Hello, how are you today?

        [00:00:15] [Speaker 2]
        I'm doing well, thanks for asking.
    """
    items = words if words else segments
    if not items:
        return ""

    # Normalize speaker names to sequential numbers (order of first appearance)
    speaker_map = {}
    speaker_count = 0

    lines = []
    current_speaker = None
    current_words = []

    def flush():
        nonlocal current_words
        if current_words:
            text = "".join(current_words).strip()
            if text:
                lines.append(text)
            current_words = []

    for item in items:
        speaker = item.get('speaker', 'Unknown')

        if speaker not in speaker_map:
            speaker_count += 1
            speaker_map[speaker] = f"Speaker {speaker_count}"

        label = speaker_map[speaker]

        if label != current_speaker:
            flush()
            if current_speaker is not None:
                lines.append("")
            ts = _fmt_ts(item.get('start', 0))
            lines.append(f"[{ts}] [{label}]")
            current_speaker = label

        # Word-level items have 'word', segment-level have 'text'
        text = item.get('word', item.get('text', ''))
        current_words.append(text)

    flush()
    return "\n".join(lines)


def format_timestamped_transcript(segments: List[Dict]) -> str:
    """Format whisper segments into timestamped plain text (no speaker labels).

    Output:
        [00:00:00] Hello, how are you today?
        [00:00:15] I'm doing well, thanks for asking.
    """
    if not segments:
        return ""

    lines = []
    for seg in segments:
        ts = _fmt_ts(seg.get('start', 0))
        text = seg.get('text', '').strip()
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)
