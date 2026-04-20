import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for module_name in ['pyannote', 'pyannote.audio']:
    if module_name not in sys.modules:
        sys.modules[module_name] = MagicMock()

from core.diarizer import (
    assign_speakers,
    assign_speakers_to_words,
    format_diarized_transcript,
)


class TestAssignSpeakersToWords:
    def test_keeps_short_real_turns(self):
        words = [
            {'word': 'A ', 'start': 0.0, 'end': 0.4},
            {'word': 'B ', 'start': 0.5, 'end': 0.9},
            {'word': 'A2', 'start': 1.0, 'end': 1.4},
        ]
        speaker_segments = [
            {'speaker': 'S1', 'start': 0.0, 'end': 0.45},
            {'speaker': 'S2', 'start': 0.45, 'end': 0.95},
            {'speaker': 'S1', 'start': 0.95, 'end': 1.5},
        ]

        tagged = assign_speakers_to_words(words, speaker_segments)

        assert [word['speaker'] for word in tagged] == ['S1', 'S2', 'S1']

    def test_preserves_ambiguous_overlap_as_unknown(self):
        words = [{'word': 'maybe', 'start': 0.0, 'end': 1.0}]
        speaker_segments = [
            {'speaker': 'S1', 'start': 0.0, 'end': 0.55},
            {'speaker': 'S2', 'start': 0.45, 'end': 1.0},
        ]

        tagged = assign_speakers_to_words(words, speaker_segments)

        assert tagged[0]['speaker'] == 'Unknown'

    def test_keeps_clear_overlap_assignment(self):
        words = [{'word': 'clear', 'start': 0.0, 'end': 0.8}]
        speaker_segments = [
            {'speaker': 'S1', 'start': 0.0, 'end': 0.75},
            {'speaker': 'S2', 'start': 0.75, 'end': 1.5},
        ]

        tagged = assign_speakers_to_words(words, speaker_segments)

        assert tagged[0]['speaker'] == 'S1'


class TestAssignSpeakers:
    def test_requires_meaningful_segment_coverage(self):
        segments = [{'text': 'line', 'start': 0.0, 'end': 10.0}]
        speaker_segments = [{'speaker': 'S1', 'start': 0.0, 'end': 1.0}]

        tagged = assign_speakers(segments, speaker_segments)

        assert tagged[0]['speaker'] == 'Unknown'


class TestFormatDiarizedTranscript:
    def test_keeps_unknown_visible(self):
        text = format_diarized_transcript(words=[
            {'word': 'Hello ', 'start': 0.0, 'end': 0.3, 'speaker': 'Unknown'},
            {'word': 'there', 'start': 0.3, 'end': 0.6, 'speaker': 'Unknown'},
        ])

        assert '[Unknown]' in text