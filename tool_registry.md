# Tool Registry

| Date | Version | Tool | Area | Notes |
| --- | --- | --- | --- | --- |
| 2026-04-22 | v1.0 | Verbatim Electron Fix Wave 1 | Electron desktop app | Fixed startup gating, packaged renderer target policy, top-bar busy masking, batch path confirmation, and desktop start/publish script wiring. |
| 2026-04-22 | v1.0 | Verbatim Electron Fix Wave 2 | Electron desktop app | Synced updater replay state into the renderer, preserved daemon crash exit data in status envelopes, aligned phase order with the daemon protocol, and passed through batch completion failures plus elapsed time. |
| 2026-04-22 | v1.0 | Verbatim Renderer Asset Base Fix | Electron desktop app | Fixed the packaged React renderer blank-window bug by switching Vite to a relative asset base so `file://` installs load `./assets/...` instead of broken `/assets/...` paths. |
| 2026-04-22 | v1.0 | Verbatim Preload Bridge Hardening | Electron desktop app | Removed preload dependence on `package.json` under sandbox mode and made the renderer bridge degrade cleanly when preload is missing so the app no longer fails as a blank window at startup. |
| 2026-04-22 | v1.0 | Verbatim Minifier Shell Redesign | Electron desktop app | Replaced the tabbed renderer with a frameless single-shell workspace, wired real folder and window controls into Electron, and moved Registry plus Redo into secondary panels beside the new queue-first layout. |
| 2026-04-23 | v1.0 | Verbatim Screenshot-Source Shell | Electron desktop app | Retargeted the renderer shell to the new screenshot source of truth while keeping Verbatim-specific settings and secondary tools. |
