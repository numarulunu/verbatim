# Diarization Accuracy Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the hidden two-speaker Electron default, replace confidence-inflating diarization heuristics with accuracy-first overlap rules, and lock the behavior in with regression tests.

**Architecture:** Add a small shared Electron settings helper for testable diarization defaults, then update backend speaker assignment to preserve ambiguity instead of smoothing it away. Cover the behavior with direct diarizer tests plus one live/resume integration regression.

**Tech Stack:** Electron, plain browser JavaScript, Python, pytest, Node built-in test runner

---

### Task 1: Electron diarization defaults

**Files:**
- Create: `electron/resources/settings_state.js`
- Create: `electron/tests/settings_state.test.js`
- Modify: `electron/main.js`
- Modify: `electron/resources/app.js`
- Modify: `electron/resources/index.html`

- [ ] **Step 1: Write the failing Electron tests**
- [ ] **Step 2: Run `node --test electron/tests/settings_state.test.js` and verify FAIL**
- [ ] **Step 3: Add the shared helper and wire it into `main.js` and `app.js`**
- [ ] **Step 4: Run `node --test electron/tests/settings_state.test.js` and verify PASS**

### Task 2: Diarizer ambiguity and short-turn rules

**Files:**
- Modify: `backend/core/diarizer.py`
- Create: `backend/tests/test_diarizer.py`

- [ ] **Step 1: Write failing diarizer tests for ambiguity, short turns, weak coverage, and Unknown formatting**
- [ ] **Step 2: Run `pytest backend/tests/test_diarizer.py -v` and verify FAIL**
- [ ] **Step 3: Implement overlap-based assignment with explicit `Unknown` handling**
- [ ] **Step 4: Run `pytest backend/tests/test_diarizer.py -v` and verify PASS**

### Task 3: Live/resume parity regression

**Files:**
- Modify: `backend/process_v2.py`
- Modify: `backend/tests/test_process_v2.py`

- [ ] **Step 1: Write a failing regression for live vs resume diarization policy parity**
- [ ] **Step 2: Run `pytest backend/tests/test_process_v2.py -k diarize -v` and verify FAIL**
- [ ] **Step 3: Remove the smoothing split and use the same assignment path in both flows**
- [ ] **Step 4: Run `pytest backend/tests/test_process_v2.py -k diarize -v` and verify PASS**

### Task 4: Final verification

**Files:**
- Modify only the planned diarization/default/test files above

- [ ] **Step 1: Run `node --test electron/tests/settings_state.test.js`**
- [ ] **Step 2: Run `pytest backend/tests/test_diarizer.py backend/tests/test_process_v2.py -v`**
- [ ] **Step 3: Run `pytest backend/tests -v`**
- [ ] **Step 4: Run `git diff -- backend/core/diarizer.py backend/process_v2.py backend/tests/test_diarizer.py backend/tests/test_process_v2.py electron/main.js electron/resources/app.js electron/resources/index.html electron/resources/settings_state.js electron/tests/settings_state.test.js`**