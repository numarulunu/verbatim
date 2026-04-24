/**
 * engine-manager — spawns the Python daemon and brokers stdin / stdout.
 *
 * Responsibilities:
 *   - spawn() / stop()  lifecycle with a status state machine
 *   - line-buffer stdout and deliver parsed events to subscribers
 *   - forward renderer commands to stdin (JSON line, \n-terminated)
 *   - detect crash (non-zero exit / signal) and surface it as a status
 *     change; callers decide whether to restart
 *
 * Deliberately does NOT use Electron — this is just Node. main.js wires
 * the instance into IPC. That separation makes it unit-testable via
 * `node --test` with an injected spawner.
 *
 * Not a singleton — the consumer constructs one per daemon. main.js owns
 * exactly one for the app's lifetime.
 */
'use strict';

const { spawn: realSpawn } = require('node:child_process');
const readline = require('node:readline');
const { parseEvent, encodeCommand } = require('./ipc-protocol.js');

const STATUS = Object.freeze({
  DOWN: 'down',
  SPAWNING: 'spawning',
  READY: 'ready',
  SHUTTING_DOWN: 'shutting_down',
  CRASHED: 'crashed',
});

const STDERR_TAIL_BYTES = 4096;

class EngineManager {
  /**
   * @param {object} opts
   * @param {string} opts.pythonPath — path to python executable (or packaged engine binary)
   * @param {string[]} opts.args — args to pass (e.g., ['engine_daemon.py'])
   * @param {string} [opts.cwd] — working directory
   * @param {NodeJS.ProcessEnv} [opts.env]
   * @param {Function} [opts.spawn] — child_process.spawn (for tests)
   * @param {number} [opts.readyTimeoutMs] — fail spawn if ready doesn't arrive
   * @param {number} [opts.shutdownTimeoutMs] — hard-kill if exit doesn't happen
   */
  constructor(opts) {
    if (!opts || !opts.pythonPath) {
      throw new TypeError('EngineManager: pythonPath is required');
    }
    this._opts = {
      readyTimeoutMs: 60_000,
      shutdownTimeoutMs: 30_000,
      spawn: realSpawn,
      ...opts,
    };
    this._status = STATUS.DOWN;
    this._child = null;
    this._eventSubs = new Set();
    this._statusSubs = new Set();
    this._readyPromise = null;
    this._readyResolve = null;
    this._readyReject = null;
    this._exitPromise = null;
    this._exitResolve = null;
    this._lastReady = null; // cached ready event for new subscribers
    this._lastExit = null;
    this._stderrBuf = [];       // Array<Buffer> — rolling tail of daemon stderr
    this._stderrBufBytes = 0;   // running total across _stderrBuf
  }

  /**
   * Last ~STDERR_TAIL_BYTES of daemon stderr as utf-8 text. Empty string if
   * the daemon hasn't written any stderr yet or hasn't been spawned.
   */
  get stderrTail() {
    if (this._stderrBufBytes === 0) return '';
    return Buffer.concat(this._stderrBuf, this._stderrBufBytes).toString('utf8');
  }

  /**
   * Reject the in-flight ready promise exactly once. Nulls both resolve and
   * reject handles so a subsequent exit/error/timeout does not re-reject.
   * (Finding 18: double-reject on a Promise is a no-op today but becomes a
   * crash source if _readyPromise is ever wired into a one-shot deferred or
   * an unhandledRejection logger.)
   */
  _rejectReady(err) {
    if (!this._readyReject) return;
    const reject = this._readyReject;
    this._readyResolve = null;
    this._readyReject = null;
    reject(err);
  }

  get status() {
    return this._status;
  }

  get lastReady() {
    return this._lastReady;
  }

  get lastExit() {
    return this._lastExit;
  }

  /**
   * Subscribe to every event emitted by the daemon. Returns an unsubscribe fn.
   */
  onEvent(cb) {
    this._eventSubs.add(cb);
    return () => this._eventSubs.delete(cb);
  }

  /**
   * Subscribe to status changes (one of `STATUS`). Fires on every transition.
   * Returns an unsubscribe fn.
   */
  onStatus(cb) {
    this._statusSubs.add(cb);
    return () => this._statusSubs.delete(cb);
  }

  /**
   * Start the daemon. Resolves with the `ready` event. Rejects on spawn
   * failure, crash before ready, or timeout.
   */
  spawn() {
    if (this._status !== STATUS.DOWN && this._status !== STATUS.CRASHED) {
      return Promise.reject(
        new Error(`spawn() called while status=${this._status}`),
      );
    }
    this._setStatus(STATUS.SPAWNING);
    this._stderrBuf = [];
    this._stderrBufBytes = 0;

    this._readyPromise = new Promise((resolve, reject) => {
      this._readyResolve = resolve;
      this._readyReject = reject;
    });
    this._exitPromise = new Promise((resolve) => {
      this._exitResolve = resolve;
    });

    let child;
    try {
      child = this._opts.spawn(this._opts.pythonPath, this._opts.args || [], {
        cwd: this._opts.cwd,
        env: this._opts.env,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (err) {
      this._setStatus(STATUS.CRASHED);
      this._rejectReady(err);
      return this._readyPromise;
    }
    this._child = child;

    // Line-buffer stdout. The protocol is one JSON object per line.
    const rl = readline.createInterface({ input: child.stdout });
    rl.on('line', (line) => this._onStdoutLine(line));

    // Buffer the last STDERR_TAIL_BYTES of daemon stderr so we can surface
    // Python tracebacks (CUDA OOM, HF auth, etc.) on crash. Also forward the
    // raw chunk to an optional sink so packaged builds keep a full log.
    const onStderr = this._opts.onStderr;
    child.stderr.on('data', (chunk) => {
      this._stderrBuf.push(chunk);
      this._stderrBufBytes += chunk.length;
      while (this._stderrBufBytes > STDERR_TAIL_BYTES && this._stderrBuf.length > 1) {
        this._stderrBufBytes -= this._stderrBuf.shift().length;
      }
      if (this._stderrBufBytes > STDERR_TAIL_BYTES) {
        const overflow = this._stderrBufBytes - STDERR_TAIL_BYTES;
        this._stderrBuf[0] = this._stderrBuf[0].slice(overflow);
        this._stderrBufBytes -= overflow;
      }
      if (typeof onStderr === 'function') {
        try { onStderr(chunk); } catch (_) { /* sink errors must not kill the pipe */ }
      }
    });

    child.on('error', (err) => {
      if (this._status === STATUS.SPAWNING) {
        this._rejectReady(err);
      }
      this._lastExit = {
        code: null,
        signal: 'ERROR',
        message: err.message,
        stderr_tail: this.stderrTail,
      };
      this._setStatus(STATUS.CRASHED);
    });

    child.on('exit', (code, signal) => {
      const wasShuttingDown = this._status === STATUS.SHUTTING_DOWN;
      // Merge instead of replace: the error handler (above) may have already
      // stored { message } for this same death; raw { code, signal } would
      // clobber it.
      this._lastExit = {
        ...(this._lastExit || {}),
        code,
        signal,
        stderr_tail: this.stderrTail,
      };
      this._setStatus(wasShuttingDown ? STATUS.DOWN : STATUS.CRASHED);
      if (this._status === STATUS.CRASHED) {
        this._rejectReady(new Error(
          `daemon exited before ready (code=${code}, signal=${signal})`,
        ));
      }
      if (this._exitResolve) { this._exitResolve({ code, signal }); this._exitResolve = null; }
      // Finding 17: tear down stdio wrappers so late bytes after exit do not
      // fire subscribers and the readline interface is eligible for GC.
      try { rl.close(); } catch (_) { /* stream may already be closed */ }
      try { child.stderr.removeAllListeners('data'); } catch (_) { /* ignore */ }
      this._child = null;
    });

    // Timeout failsafe.
    const readyTimer = setTimeout(() => {
      if (this._status === STATUS.SPAWNING) {
        this._rejectReady(new Error(
          `daemon did not emit ready within ${this._opts.readyTimeoutMs}ms`,
        ));
        try { child.kill(); } catch (_) { /* ignore */ }
      }
    }, this._opts.readyTimeoutMs);
    // Once ready arrives, clear the timer.
    const clearOnReady = this.onStatus((s) => {
      if (s !== STATUS.SPAWNING) {
        clearTimeout(readyTimer);
        clearOnReady();
      }
    });

    return this._readyPromise;
  }

  /**
   * Send a command to the daemon. Throws if status is not `ready`.
   */
  send(command) {
    if (this._status !== STATUS.READY) {
      throw new Error(`send() called while status=${this._status}`);
    }
    const line = encodeCommand(command);
    this._child.stdin.write(line);
  }

  /**
   * Graceful shutdown. Sends `shutdown` and waits for exit. If the daemon
   * doesn't exit within `shutdownTimeoutMs`, force-kills it.
   */
  async stop() {
    if (this._status === STATUS.DOWN || this._status === STATUS.CRASHED) {
      return;
    }
    const child = this._child;
    if (!child) return;
    this._setStatus(STATUS.SHUTTING_DOWN);
    try {
      child.stdin.write(encodeCommand({ cmd: 'shutdown' }));
    } catch (_) { /* stdin may already be closed */ }
    try {
      await Promise.race([
        this._exitPromise,
        new Promise((_, rej) => setTimeout(
          () => rej(new Error('shutdown timeout')),
          this._opts.shutdownTimeoutMs,
        )),
      ]);
    } catch (_) {
      // Hard-kill on timeout.
      try { child.kill(); } catch (_) { /* ignore */ }
      await this._exitPromise;
    }
  }

  _onStdoutLine(line) {
    if (!line || !line.trim()) return;
    let event;
    try {
      event = parseEvent(line);
    } catch (err) {
      // Unknown / malformed lines are surfaced as synthetic error events
      // so the UI can log them; the daemon should never emit these.
      event = {
        type: 'error',
        error_type: 'invalid_command_payload',
        message: `failed to parse daemon output: ${err.message}`,
        recoverable: true,
        context: { raw: line.slice(0, 200) },
      };
    }

    if (event.type === 'ready') {
      this._lastReady = event;
      this._setStatus(STATUS.READY);
      if (this._readyResolve) {
        this._readyResolve(event);
        this._readyResolve = null;
        this._readyReject = null;
      }
    } else if (event.type === 'shutting_down') {
      this._setStatus(STATUS.SHUTTING_DOWN);
    }

    for (const cb of this._eventSubs) {
      try { cb(event); } catch (_) { /* subscriber errors must not stop others */ }
    }
  }

  _setStatus(next) {
    if (this._status === next) return;
    this._status = next;
    for (const cb of this._statusSubs) {
      try { cb(next); } catch (_) { /* swallow */ }
    }
  }
}

module.exports = { EngineManager, STATUS };
