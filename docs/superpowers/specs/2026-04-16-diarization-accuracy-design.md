# Diarization Accuracy Fixes Design

## Goal

Fix three approved diarization issues in a safe order:
1. remove the hidden exact-2-speaker Electron default
2. stop weak or ambiguous evidence from becoming confident labels
3. add regression coverage around the heuristic changes

## Scope

Only the three approved buckets are in scope. Lower-confidence SMAC items are out of scope.

## Design

### Electron defaults

Add one small shared Electron helper for diarization defaults and select-value mapping.

- default remains `diarize=true`
- default speaker policy becomes `auto` via `diarizeSpeakers=0`
- `main.js` and `app.js` both use the same helper
- the UI shows `Auto-detect` as the default option

### Backend heuristics

Replace confidence-inflating speaker assignment rules with overlap-based rules.

- word mapping scores overlap across the full word span
- weak evidence or near ties stay `Unknown`
- segment fallback requires meaningful coverage before assigning a speaker
- transcript formatting preserves `Unknown` instead of renumbering it

### Live/resume parity

Remove the live/resume smoothing split and use the same assignment policy in both paths.

## Files

- modify `electron/main.js`
- modify `electron/resources/index.html`
- modify `electron/resources/app.js`
- add `electron/resources/settings_state.js`
- add `electron/tests/settings_state.test.js`
- modify `backend/core/diarizer.py`
- add `backend/tests/test_diarizer.py`
- modify `backend/tests/test_process_v2.py`

## Verification

- `node --test electron/tests/settings_state.test.js`
- `pytest backend/tests/test_diarizer.py backend/tests/test_process_v2.py -v`
- `pytest backend/tests -v`