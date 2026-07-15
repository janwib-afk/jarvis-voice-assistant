# Phase 5 — Motion-Implementierung (2026-07-12)

Baseline vor Beginn: 471 Tests / Smoke Exit 0. Skill `emil-design-eng` formal invoziert (Erstantwort-Ritual honoriert); Audit: [MOTION_AUDIT.md](MOTION_AUDIT.md), System: [MOTION_SYSTEM.md](MOTION_SYSTEM.md).

## Geänderte Dateien

- `frontend/design-tokens.css` — Motion-Token-Block (Dauern/Kurven/Distanz/Press) + Remap der Alt-Dauer-Tokens (hover 180ms, fade 200ms, orb 200ms, listen 2.6s …).
- `frontend/style.css` — Alt-Puls-Keyframes entfernt (pulse-listen/-think/-speak), `flash-error` auf transform-only, `banner-in` auf 8px/ease-enter; statische Orb-Glows aus den box-shadows gelöst; **Phase-5-Block**: `#orb::after`-Glow-Layer, 4 Kern- + 3 Glow-Keyframes, `run-dot`, Lünetten-`sweep`, Press-Feedback-Gruppe, `enter-fade` (View/msg-new/Pill/dirty/confirm), Ghost-Kurve; **neuer gezielter Reduced-Motion-Block** (ersetzt den Alt-Block).
- `frontend/index.html` — ein Kind `.luenette-sweep` (aria-hidden) im Orb-Container.
- `frontend/main.js` — `playViewEnter()` (Nav-Handler), `.msg-new`-Tagging in `addTranscript`, `action-running`-Containerklasse in `addActionEntry`, `removeBanner()` (WAAPI-Exit mit Fallback).
- `tests/test_frontend.py` — additive `MotionTests` (Tokens, Glow-Layer, Keyframe-Ablösung, Reduced-Abdeckung, JS-Hooks).

## Entfernte / ersetzte Animationen

`pulse-listen`/`pulse-think`/`pulse-speak` (box-shadow-Puls, Alt-Farben) → `orb-*` + `glow-*` (transform/opacity, Token-Farben, beruhigte Frequenzen 2.6/1.15/0.7s — bewusste Abweichung von 1.8/0.85/0.65s gemäß Leitidee „ruhiges Instrument", Charakter-Reihenfolge unverändert). `ae.run`-Reuse → `run-dot` (opacity-only). Orb-Übergang 500ms → 200ms/160ms. Banner 12px/ease → 8px/starke Kurve + 120ms-Exit.

## Bewusste Nicht-Animationen

Esc/Stop-Wirkung, Strg+Enter, Tab/Fokus/Skip-Link, Suche-Filterung, Fenstermodus-Größe (pywebview nativ), Skeletons, Ok-/System-Dots (Licht = nur Aktivität), muted/degraded-Orb, Bestandsnachrichten, Hover (reiner Farbwechsel).

## Performance-Entscheidungen

Glow als `::after`-Opacity statt Shadow-Repaint; ausschließlich transform/opacity in neuen Keyframes; Sweep = maskierte Conic-Fläche mit transform-Rotation; WAAPI nur Banner-Exit; keine neuen Timer/Listener-Leaks (`animationend` once); Ausnahmen dokumentiert: Ghost-Geometrie (klein, Raster-Preview), Toggle-Knob-`left` (12px, 120ms reduced).

## Abweichungen von Phase 2/3

Nur die Puls-Dauern (s. o., begründet); `--duration-orb` 500→200ms (Stop-Sichtbarkeit vor Eleganz, STATE_MODEL „stopping <1s"). Keine Farb-/Typo-/Verhaltensänderungen.

## Verifikation (frisch)

- `docs/motion/tools/verify_phase5.py` → **13/13** (Zustandsmatrix exakter Animationsnamen, error endet statisch, Wechsel ersetzt sofort, Sweep an/aus, **Esc unterbricht speaking/thinking <600ms**, 6×-Mute-Spam ohne Queue, View-Enter selbstaufräumend + Fokus korrekt, msg-new einmalig, Banner-WAAPI-Exit, **Reduced: 0 Animationen + statischer Glow 0.7**), 0 Konsolenfehler; drei FAILs des Erstlaufs waren Test-Setup (Mute-Flag), dokumentiert.
- Suite (inkl. neuer Guards) Exit 0 · Smoke Exit 0.
- Evidence: `evidence/sequenz--zustaende-stop-error-wechsel.webm` (973 KB; idle→listening→thinking→speaking→action-running→Esc→error→Erholung→Seitenwechsel) + `normal--listening-glow.png` / `reduced--listening-static.png`.

## Bekannte Einschränkungen / Phase 6

- Sweep-/Glow-Feinabstimmung auf echtem 120Hz-/HDR-Gerät prüfen (Launcher-Start durch Jan; nicht per Browser gegen echten Server).
- `speaking` ohne Amplitudenkopplung (bewusst — keine falsche Audio-Sync-Behauptung); echte Pegelkopplung wäre ein Phase-6+-Feature (AnalyserNode).
- Panel-Mini-Aktionsliste erbt run-dot — ok; ggf. Phase-6-Politur der Dichte.
- Phase 6 (Kritik-/Polish-Pass): frische-Augen-Review (Skill: „next day"), Frame-by-Frame-Sichtung der Übergänge, Mikro-Abstimmung Glow-Opazitäten, evtl. `@starting-style`-Migration der Enter-Effekte.
