# Golden Fixtures

Regression anchor for the Wave 1 tuning (VAD params, initial_prompt vocab,
pyannote min_duration_off). The test `tests/test_golden.py` is skipped when
the WAV is absent so CI/devs without the asset don't fail.

## How to add the fixture

1. Record or export one ~10-min audio file that is representative of
   Ionut's real coaching workload - mixed Romanian + English, one student,
   at least one sung passage. Mono WAV, 16 kHz recommended.
2. Save it here: `backend/tests/fixtures/golden_mixed.wav`.
3. Run the current pipeline on it, hand-correct the output, and fill in
   `golden_mixed.ref.json` with:
   - `reference_text`: the corrected transcript (plain text, no timestamps).
   - `reference_speakers`: the list of distinct speakers you heard
     (for example `['Ionut', 'Luiza']`).
   - `max_wer`: the word-error-rate ceiling you're willing to tolerate
     (start with `0.25` - tighten later).

## Benchmark Pack Rules

The benchmark pack lives in `benchmark_pack/` and is the release gate for
speaker quality.

- Every `*.ref.json` in this repo must include `reference_text` and
  `reference_speakers`.
- Every token entry in a hand-labeled reference must also carry a
  `speaker_state` value.
- Use `speaker_state` to record the token-level diarization state you saw,
  not a guessed speaker name.
- Keep the tuning pack and blind holdout pack on disjoint clip IDs.
- Put pass/fail thresholds in `manifest.json` and `holdout_manifest.json`.
- If benchmark audio is not committed, the integration checks skip instead of
  failing.

## What the golden test asserts

- Whisper transcribes `golden_mixed.wav` end-to-end.
- WER(`transcript`, `reference_text`) <= `max_wer`.
- Diarization returns at least `len(reference_speakers)` distinct speakers.

One fixture. One run. Pass/fail. Do not grow this into a full regression
suite - that's a V2 item.