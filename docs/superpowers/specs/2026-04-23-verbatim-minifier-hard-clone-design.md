# Verbatim Minifier Hard-Clone Renderer Design

Date: 2026-04-23
Status: Approved in conversation, pending written-spec review

## Goal

Replace the current Verbatim renderer shell with a near-literal clone of the Minifier desktop UI so the product matches Minifier's proportions, spacing, density, and visual hierarchy one-to-one, while keeping Verbatim's transcription behavior underneath.

## User Direction

The user explicitly approved the strongest-fidelity path:

- treat Minifier as the source UI, not loose inspiration
- copy the whole front end and then edit it for Verbatim-specific settings and labels
- preserve Minifier's exact desktop density even if some Verbatim controls live lower in the right rail and require scrolling
- prefer screenshot-level alignment over trying to improve or reinterpret the Minifier layout

## Primary References

Reference screenshot pair in this repo:

- current Verbatim shell: `frontend/{B11249A5-BB76-45AD-93DE-67AB050FC788}.png`
- target Minifier shell: `frontend/{98D111A1-D3B7-4C62-A1E7-4C948FAD4B38}.png`

Source UI reference from the Converter project:

- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\App.jsx`
- `...\components\TopBar.jsx`
- `...\components\LeftPane.jsx`
- `...\components\RightPane.jsx`
- `...\components\BottomBar.jsx`
- `...\components\FolderPickers.jsx`
- `...\components\FileQueue.jsx`
- `...\components\ProfileDropdown.jsx`
- `...\components\sections\VideoSection.jsx`

## Non-Goals

- no backend protocol rewrite
- no Electron main-process redesign beyond any minor renderer support needed for the visual clone
- no attempt to preserve the current Verbatim shell's softer spacing or bespoke card layout
- no feature expansion beyond what is needed to map Verbatim settings into the cloned shell
- no second alternate layout mode

## Fidelity Standard

This pass is not Minifier-inspired. It is a hard-clone pass.

Success means:

- title bar height, icon box size, text offsets, and window-control placement visually match Minifier
- top folder strip row height, field height, browse button width, refresh button size, and divider placement match Minifier
- left queue region, including header band, row height, text scale, checkbox placement, class badge size, size/status column spacing, and totals footer, matches Minifier's table rhythm
- right rail width, dropdown height, impact card padding, stat tile sizing, section gaps, field widths, toggle rhythm, and scroll behavior match Minifier
- bottom bar height, left action block width, center status stack, link placement, and progress treatment match Minifier

Functional text and controls may differ because Verbatim is not a compressor, but the shell proportions and UI mass should read as a carbon copy.

## Current Gap Versus Target

The current Verbatim renderer is structurally close but still visibly off:

- title bar is taller and more card-like than Minifier
- top strip is too padded and the utility actions float too loosely
- queue area uses a more componentized empty state and different table rhythm
- right rail is too wide in feel because of larger cards and chunkier internal spacing
- bottom bar is visually heavier and split differently from Minifier's flatter, denser footer
- generic Verbatim UI primitives still carry a softer, rounder look than the target app

This redesign removes those deviations instead of tuning around them.

## Architecture Decision

### Decision

Use Minifier's renderer composition and spacing model as the base shell for Verbatim.

### Why

The user's request is about exact visual matching, and the current Verbatim shell already proved that close is insufficient. Retaining the current shell as the styling base would keep missing the target's proportions even if the layout remains semantically similar.

### Effect

- Verbatim's shell CSS becomes Minifier-derived instead of Verbatim-derived
- component boundaries should map to Minifier's layout boundaries first
- Verbatim behavior is adapted into that shell rather than the shell being adapted around the current Verbatim implementation

## Top-Level Layout

The renderer should mirror Minifier's composition directly:

1. `TopBar`-equivalent custom title bar
2. `LeftPane` equivalent containing folder strip + queue table
3. `RightPane` equivalent containing preset dropdown + impact card + stacked controls
4. `BottomBar` equivalent containing start/stop block + status body + output link

The shell remains a single primary workspace only. `Registry` and `Redo` stay secondary tools, but they must live inside the same right-side visual language rather than feeling like separate applications.

## Detailed Component Mapping

### Title Bar

Verbatim should inherit Minifier's exact chrome pattern:

- same overall height and horizontal padding
- same left logo box scale and brand label offset
- same right-side control cluster spacing and button hit area
- same flat dark strip with thin border line and no extra ornamental mass

Allowed differences:

- Verbatim iconography instead of Minifier iconography
- `Verbatim` naming and subtitle text

Not allowed:

- taller title bar
- larger logo tile
- softer or rounder window controls than Minifier uses

### Left Pane

The left pane must follow Minifier's structure exactly:

- folder strip at the top with two rows only
- each row uses Minifier's four-column layout logic: compact label, long field, browse button, optional trailing utility button
- queue table fills the remaining height
- totals footer stays attached to the table bottom just like Minifier

For Verbatim:

- `Input` row remains folder picker
- `Output` row remains folder picker
- trailing utility button maps to refresh/re-scan behavior using Minifier's same compact square button treatment

The action links currently floating to the right of the folder strip should be reduced and repositioned so the whole strip reads like Minifier first and Verbatim second.

### Queue Table

The queue must be rebuilt to behave visually like Minifier's file queue:

- same header band height
- same uppercase tiny header typography
- same dense row rhythm and divider cadence
- same checkbox offset from the left edge
- same compact class badge sizing
- same numeric column tightness
- same bottom totals strip treatment

Verbatim-specific mapping:

- `Filename` remains first visible column
- `Class` can map to audio/media type or a compact transcription-class marker
- `Size` stays numeric
- `Status` maps to queued/running/done/failed transcription state

If additional transcription detail is needed, it should fit into Minifier's status cell or hover/secondary text pattern instead of adding new structural columns that break the clone.

### Empty State

The current Verbatim empty state is too decorative and too centered as a standalone card. The replacement should behave like a Minifier-style quiet queue placeholder:

- flatter treatment
- denser spacing
- less ornamental border styling
- sized relative to the queue container the way Minifier does

### Right Pane

The right pane should keep Minifier's sequence and spacing rhythm:

1. top profile/preset dropdown
2. impact card
3. stacked sections beneath with consistent section shells, labels, hints, and controls

Verbatim content mapping:

- top dropdown can remain `Custom` for now or later map to Verbatim presets
- impact card shows queue selection and run-impact information using Minifier's stat density and horizontal meter style
- stacked controls map Verbatim's run options such as model, language, polish mode, isolation, diarization, and any required advanced settings

The visual rule is strict:

- if Minifier uses a 40px dropdown, Verbatim should not use a larger one
- if Minifier's card padding is tight, Verbatim cards must not become roomier
- if Minifier uses long-scroll stacked sections, Verbatim should do the same rather than spreading controls into larger cards

### Registry And Redo Placement

`Registry` and `Redo` stay available, but should be visually absorbed into the right-pane system.

That means:

- their launchers belong in the stacked settings region, not as oversized special panels
- their buttons or rows should share Minifier's control language and scale
- their opened surfaces can remain modal/drawer based, but the entry points should feel like native parts of the cloned right rail

### Bottom Bar

The bottom bar should match Minifier's exact composition:

- wide left action slab for `Start` / `Stop`
- flatter central content block with status headline and technical detail line
- output-folder link sitting in the same body region rather than detached visually
- subtle top progress line instead of a heavier custom progress treatment

Verbatim mapping:

- primary action remains transcription start/stop
- headline reflects scan/run readiness and progress
- technical line uses CPU/RAM/GPU or run summary as space allows

The footer should be judged against the Minifier screenshot first, not against generic usability preferences.

## Styling Rules

### Shell Tokens

The current renderer tokens should be replaced or tightened so they align with Minifier's look:

- darker, flatter base surfaces
- thinner border contrast
- tighter border radii
- smaller default typography in headers and labels
- denser vertical spacing throughout
- less accent spread outside the primary action and key meters

### Primitive Components

Existing Verbatim primitives likely need resizing so the clone can hold:

- `Button`
- `Input`
- `Select`
- `Toggle`
- any segmented-control equivalent used in the right rail

These components should be adjusted to Minifier-like control heights and border treatments so the shell does not drift back toward the current Verbatim style.

### Scroll Behavior

The right rail should preserve Minifier's scroll-first behavior. If the viewport cannot show all transcription controls, the rail scrolls rather than expanding cards or adding large gaps.

## Functional Preservation

The redesign changes the renderer shell, not the backend contract.

The following behaviors remain intact:

- Electron custom window controls
- folder picking and open-path actions
- scan flow
- queue selection logic
- start/cancel transcription flow
- progress updates from daemon events
- settings load/save
- updater banner and toasts
- registry management
- redo flow

Where functional behavior and clone fidelity conflict, the renderer should preserve behavior but express it inside the cloned Minifier shell.

## Files Likely Affected

Primary Verbatim files:

- `verbatim/renderer/src/App.tsx`
- `verbatim/renderer/src/index.css`
- `verbatim/renderer/src/components/shell/TitleBar.tsx`
- `verbatim/renderer/src/components/shell/WorkspaceHeader.tsx`
- `verbatim/renderer/src/components/shell/QueuePane.tsx`
- `verbatim/renderer/src/components/shell/SettingsRail.tsx`
- `verbatim/renderer/src/components/shell/BottomActionBar.tsx`
- `verbatim/renderer/src/components/shell/RegistryPanel.tsx`
- `verbatim/renderer/src/components/shell/RedoPanel.tsx`
- `verbatim/renderer/src/components/batch/FileList.tsx`
- `verbatim/renderer/src/components/batch/FileRow.tsx`
- `verbatim/renderer/src/components/ui/Button.tsx`
- `verbatim/renderer/src/components/ui/Input.tsx`
- `verbatim/renderer/src/components/ui/Select.tsx`
- `verbatim/renderer/src/components/ui/Toggle.tsx`

Reference-only Minifier files:

- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\App.jsx`
- `...\components\TopBar.jsx`
- `...\components\LeftPane.jsx`
- `...\components\RightPane.jsx`
- `...\components\BottomBar.jsx`
- `...\components\FolderPickers.jsx`
- `...\components\FileQueue.jsx`
- `...\components\ProfileDropdown.jsx`
- `...\components\sections\VideoSection.jsx`

## Verification Standard

Verification is evidence-based, not visual guesswork.

Required checks after implementation:

- targeted renderer/layout tests for the shell composition and custom chrome hooks
- `npm test --silent`
- `npm run renderer:build --silent`
- `npm run build-win --silent`

Visual verification standard:

- compare the rebuilt Verbatim shell directly against the Minifier screenshot in this repo
- inspect title bar height, folder-strip density, queue row rhythm, right-rail width, impact-card mass, and bottom-bar proportions as primary acceptance criteria

## Risks And Tradeoffs

### Risk: Verbatim Has Different Settings Content

Minifier's right rail is compression-focused, while Verbatim's controls are transcription-focused.

Handling rule:

- keep Minifier's shell and control density
- allow deeper scroll in the right rail
- do not enlarge cards or widen the rail just to fit more Verbatim controls above the fold

### Risk: Existing Verbatim Components Reintroduce Drift

Generic Verbatim primitives and queue components may carry styles that fight the clone.

Handling rule:

- tune or replace those primitives so they inherit Minifier-like metrics
- do not keep current dimensions just because the component already exists

### Risk: Empty-State And Status Details Add Extra UI Mass

Verbatim exposes transcription-specific metadata that Minifier does not show.

Handling rule:

- compress those details into existing Minifier-like cells, subtitles, or status rows
- avoid adding new visible shell regions unless behavior would otherwise break

## Decision Summary

Verbatim should stop being a custom shell that resembles Minifier and become a Minifier-shell clone with Verbatim behavior and settings mapped into it. The source of truth for proportions, density, and visual hierarchy is Minifier's renderer and screenshots.
