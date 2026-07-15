# Pixel-Diff-Report — Phase-1-Token-Migration (2026-07-11)

**Kontext:** Vergleich PRE (Arbeitsstand VOR der Token-Migration, Frozen-Capture
mit fixer Uhr + deaktivierten Animationen, temporärer Referenzordner) gegen POST
(dieser Ordner, identischer Capture-Lauf NACH Migration + Konsolidierung).
Die Determinismus-Grundlage wurde vorab bewiesen: zwei unabhängige PRE-Läufe
waren 27/27 byte-identisch. **Ergebnis: Die Token-Migration ist pixelgleich —
27/27 Screenshots ohne ein einziges abweichendes Pixel.** Zusätzlich wurde ein
Unfrozen-Lauf (Animationen aktiv) visuell gegen die Phase-0-Screenshots geprüft
(Orb-Pulse, Banner, Hover leben unverändert). Werkzeuge: `docs/design-baseline/
tools/capture_baseline.py --freeze` + `docs/design-system/tools/diff_screens.py`.

- A: PRE-Frozen-Referenz (Scratchpad, vor Migration)
- B: `docs/design-system/verification/` (dieser Ordner, nach Migration)
- Ergebnis: **27/27 identisch**

| Screenshot | Ergebnis | Details |
|---|---|---|
| control-music--focus--list.png | identisch |  |
| control-music--focus--selected.png | identisch |  |
| control-overview--focus--app-open-feedback.png | identisch |  |
| control-overview--focus--app-selected.png | identisch |  |
| control-overview--focus--default.png | identisch |  |
| control-overview--focus--keyboard-focus.png | identisch |  |
| control-overview--focus--map-hover.png | identisch |  |
| control-overview--focus--map-loading.png | identisch |  |
| control-overview--fullscreen--default.png | identisch |  |
| control-settings--focus--default.png | identisch |  |
| jarvis--focus--actions.png | identisch |  |
| jarvis--fullscreen--empty-disconnected.png | identisch |  |
| jarvis--fullscreen--error-banner.png | identisch |  |
| jarvis--fullscreen--error-forced.png | identisch |  |
| jarvis--fullscreen--hover-copy-button.png | identisch |  |
| jarvis--fullscreen--idle.png | identisch |  |
| jarvis--fullscreen--keyboard-focus.png | identisch |  |
| jarvis--fullscreen--listening-forced.png | identisch |  |
| jarvis--fullscreen--listening-ptt-real.png | identisch |  |
| jarvis--fullscreen--muted-real.png | identisch |  |
| jarvis--fullscreen--reduced-motion-listening.png | identisch |  |
| jarvis--fullscreen--speaking-forced.png | identisch |  |
| jarvis--fullscreen--thinking-forced.png | identisch |  |
| jarvis--fullscreen--transcript-multi.png | identisch |  |
| jarvis--fullscreen--transcript-search.png | identisch |  |
| jarvis--panel--answer-actions.png | identisch |  |
| jarvis--panel--muted.png | identisch |  |
