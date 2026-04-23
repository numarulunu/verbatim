# Verbatim Screenshot-Source Shell Design

Date: 2026-04-23
Status: Approved in conversation, pending written-spec review

## Goal

Replace Verbatim's current renderer shell with a near-literal clone of the new screenshot in the repo root so the app reads visually like that source UI at a glance, while keeping Verbatim-specific settings, queue semantics, and Electron behavior.

## Source Of Truth

Primary visual source:

- `C:\Users\Gaming PC\Desktop\Transcriptor v2\{47D30056-5EED-40EF-BFF5-3CC7D99D858A}.png`

Supporting code references from the Converter project:

- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\TopBar.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\FolderPickers.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\FileQueue.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\BottomBar.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\RightPane.jsx`
- `C:\Users\Gaming PC\Desktop\Claude\Convertor\_bolt_frontend\src\components\ProfileDropdown.jsx`

This screenshot supersedes the earlier hard-clone target wherever they differ.

## User Direction

The user approved these rules in conversation:

- treat the new screenshot as the full replacement source of truth for the shell
- keep Verbatim-specific settings and behavior, but make the UI design match the screenshot as closely as possible
- keep the top-left brand structure and spacing from the screenshot, but label it `Verbatim` and include a compact Verbatim logo
- keep `Registry`, `Redo`, and advanced settings out of the main visual shell as much as possible; expose them as small low-emphasis entries in the right rail that open secondary popups

## Non-Goals

- no backend protocol rewrite
- no Electron main-process redesign beyond renderer support already in place
- no attempt to preserve current Verbatim-specific header/footer embellishments that do not exist in the screenshot
- no extra navigation modes, tabs, or alternate layouts

## Fidelity Standard

This is a screenshot-first shell replacement, not a loose restyle.

Success means:

- title bar mass, spacing, control placement, and logo/name alignment read like the screenshot
- header shows only the two folder rows visible in the screenshot, with no extra right-side action cluster
- left pane reads like a dense table-first file queue, not a card list
- right rail begins with the same preset dropdown and impact card pattern as the screenshot and keeps the same spacing rhythm
- footer keeps the same flat start slab and center-body layout as the screenshot

Allowed differences are content-only:

- `Verbatim` branding instead of `Minifier`
- a Verbatim logo instead of the source product logo
- transcription-specific column/state wording and settings content

## Architecture Decision

### Decision

Use the screenshot as the renderer shell source of truth and treat Verbatim behavior as content mapped into that shell.

### Why

The user explicitly wants the UI to match the screenshot, not the earlier approximation. Continuing to optimize toward older interpretations would keep visual drift alive.

### Effect

- existing shell work is valid only insofar as it increases screenshot fidelity
- future changes should be judged against the screenshot first, not against prior intermediate designs
- Verbatim-only tools should live behind low-emphasis rail entries or secondary popups so the main shell stays visually clean

## Layout Mapping

### Title Bar

The title bar should mirror the screenshot's structure and density:

- same flat 48px strip feel
- same left-aligned brand cluster geometry
- same compact control cluster on the right
- no subtitle line

Verbatim-specific adaptation:

- keep the screenshot's brand slot and spacing
- replace the source name with `Verbatim`
- keep a compact Verbatim logo in the same slot

### Header

The header should contain only the two visible picker rows:

1. input field + browse button
2. output field + browse button + one compact refresh or re-scan utility button

Rules:

- no separate right-side actions cluster
- fields and buttons should match the screenshot's density and spacing
- actions removed from the header must either move elsewhere intentionally or disappear if redundant

### Left Queue Pane

The left pane should remain dominant and table-first:

- compact table header
- dense rows with minimal visual decoration
- quiet empty state anchored inside the table area
- totals strip attached to the bottom edge like the screenshot

Verbatim mapping:

- keep transcription file states and selection behavior
- map media class, size, and run state into the screenshot's denser row rhythm
- preserve queue interaction, but remove any presentation that feels more ornate than the screenshot

### Right Rail

The right rail should follow the screenshot's sequence and spacing:

1. preset dropdown
2. impact card
3. stacked settings sections below

Verbatim-only rule:

- `Registry`, `Redo`, and advanced settings should appear as low-emphasis entries inside the rail and open secondary popups
- they should not blow up the main rail into a visibly different layout from the screenshot

### Footer

The footer should keep the screenshot's flat composition:

- left start or stop slab
- central status body with concise readiness or run copy
- output-folder affordance inside the body region

Allowed Verbatim behavior:

- active progress line may remain subtle when a run is in progress
- running copy may show transcription progress details
- idle copy should stay neutral and must not imply live telemetry if the numbers are stale

## Control Surface Policy

Controls that are visible in the screenshot stay inline.

Controls that are necessary for Verbatim but not visible in the screenshot should be de-emphasized:

- small rail entries for secondary tools
- secondary popup surfaces for those tools when opened

This keeps the primary shell visually faithful while still preserving functionality.

## Testing And Verification

Keep verification lightweight and shell-focused:

- retain `verbatim/tests/shell-layout.test.js` as the structural guardrail test
- retain `npm run renderer:build --silent` as the renderer compile check
- evaluate remaining UI passes by screenshot fidelity first, not by generic design cleanup preferences

## Implementation Impact

The existing hard-clone plan remains usable as execution scaffolding, but its target should now be interpreted through this screenshot-first spec.

Practical consequence:

- current and future UI passes should tighten toward this screenshot whenever an earlier plan detail conflicts with it
- queue, right rail, and footer work should be judged by visual match to this screenshot, not by older approximations
