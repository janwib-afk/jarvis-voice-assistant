# Motion-Audit (Phase 5, 2026-07-12)

Vollinventar der Bewegung vor dem Umbau. Baseline: 471 Tests / Smoke Exit 0. Quellen: `frontend/style.css` (Stand nach Phase 4), `frontend/main.js`. Empfehlungen folgen dem Animation Decision Framework des Skills `emil-design-eng`.

## Inventar

| # | Element | Auslöser | Zweck | Dauer | Easing | Props | Wdh. | Unterbrechbar | Re-Trigger | Zustandswechsel | Reduced-Alt. | Perf-Risiko | Empfehlung |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `#orb.listening` `pulse-listen` | Zustand | Ambient „hört zu" | 1.8s | ease-in-out | scale + **box-shadow (Alt-Ambers!)** | ∞ | Klassentausch ersetzt | restart | ersetzt | **fehlt** | **hoch** (Shadow-Repaint) | **anpassen**: Glow → `::after`-Opacity, Token-Farben |
| 2 | `#orb.thinking` `pulse-think` | Zustand | Ambient „denkt" | .85s | ease-in-out | scale | ∞ | ja | restart | ersetzt | **fehlt** | niedrig | **anpassen**: ruhiger (1.15s), Innenlicht statt Hektik |
| 3 | `#orb.speaking` `pulse-speak` | Zustand | Ambient „spricht" | .65s | ease-in-out | scale | ∞ | ja | restart | ersetzt | **fehlt** | niedrig | **anpassen** (.7s, Impulscharakter) |
| 4 | `#orb.idle` | Zustand | Präsenz | — | — | — | — | — | — | — | ok (statisch) | — | **ergänzen**: kaum sichtbares Atmen 6s |
| 5 | `#orb.error` `flash-error` | Fehler | Aufmerksamkeit, endet stabil | 1.1s ×2 | ease-in-out | scale + shadow | 2× | ja | restart | ersetzt | **fehlt** | mittel | **anpassen**: Shadow raus (Opacity-Layer), 2× behalten |
| 6 | `.ae.run .ae-dot` | Aktion läuft | Fortschrittssignal | 1.2s (pulse-listen-Reuse!) | ease-in-out | scale+shadow | ∞ | ja | restart | ok | alt-Block ✗ | mittel | **ersetzen**: eigene Opacity-Puls-Keyframe |
| 7 | `banner-in` | Banner-Mount | Anti-Jarring, Richtung | .25s | ease | opacity+translateX(12px) | 1× | n/a | neu | n/a | **fehlt** | niedrig | **anpassen**: 200ms ease-enter, 8px; Exit 120ms (WAAPI) |
| 8 | `map-pulse` | Zuweisung ok | Bestätigung, endet stabil | .6s | ease-out | inset-shadow | 1× | ja | restart | ok | ✓ vorhanden | mittel | **behalten** (einmalig, semantisch), Ton via Token |
| 9 | Hover/Fade-Transitions (Buttons, Tabs, Felder …) | Hover/Zustand | Feedback | 140–300ms (Tokens) | default ease | color/border/opacity/bg | — | ja (Transitions) | retarget ✓ | ✓ | teils | niedrig | **behalten**, Dauern auf Motion-Tokens mappen, `(hover:hover)`-Gate für Bewegung |
| 10 | Orb-Übergang | Zustandstausch | Anti-Jarring | .5s | ease | background+box-shadow | — | ✓ | retarget | ✓ | ok | mittel | **anpassen**: 200ms/exit-Kurve, Shadow-Transition raus |
| 11 | `.app-toggle-knob` | Toggle | Mechanik | 250ms | default | left+bg+shadow | — | ✓ | retarget | ✓ | alt-Block ✓ | niedrig | **anpassen**: `left`→ok (klein), Dauer fast, exit-Kurve |
| 12 | Ghost (`.map-ghost`) | Hover Zone | Vorschau | 150/200ms | default | opacity+Geometrie (left/top/w/h) | — | ✓ | retarget | ✓ | ✓ | mittel (Layout-Props, kleines Element) | **behalten** (bewusste Ausnahme: Geometrie folgt Zonenraster; Fläche klein, dokumentiert) |
| 13 | View-/Subview-Wechsel | Nav-Klick | — (heute hart) | 0 | — | display | — | — | — | — | — | — | **ergänzen**: Enter-Fade 240ms (nur Maus-/Klickpfad, Enter-only) |
| 14 | Neue Transcript-Nachricht | WS/Send | — (heute hart) | 0 | — | — | — | — | — | — | — | — | **ergänzen**: `.msg-new` 180ms, NUR letzter Eintrag |
| 15 | JS-Timer: `flashOrbError` 2500ms | Fehlerimpuls | Zustands-Revert | — | — | Klassen | 1× | zustandsgeprüft | ok | prüft `error` | n/a | keine | **behalten** (funktional, kein UI-Fake) |
| 16 | JS-Timer: Copy 1000ms, Busy-Feedbacks, Settings-Close 800/1000ms, Debounce 1s, Reconnect-Backoff | Feedback/Netz | Status | — | — | Klassen/Text | 1× | ok | dedupe ok | ok | n/a | keine | **behalten** (auditiert: keine UI-Zustands-Simulation, sondern echte Feedback-Fenster) |

**Negativbefunde (gesucht, nicht gefunden):** `transition: all` ✗ · Blur-/Filter-Animationen ✗ · width/height/top-Animationen (außer #12 begründet + Knob-`left` 12px) ✗ · Dauerhintergrund-Effekte ✗ (Lamp-Glow statisch) · ease-in ✗ · blockierende Übergänge ✗ · Fokus-Verzögerung ✗.

## Änderungs-Review (Skill-Pflichtformat)

| Before | After | Why |
| --- | --- | --- |
| `pulse-listen` animiert `box-shadow` mit Alt-Farben `rgba(200,130,45,…)` | Glow als `#orb::after` (statisches Radial-Bild), Keyframe animiert nur `opacity`+`scale` in Token-Farben | Nur transform/opacity laufen auf der GPU; Shadow-Puls repaintet 60×/s; Farben gehören ans Token-System |
| `.ae.run` nutzt `pulse-listen 1.2s` (Scale+Shadow am 6px-Dot) | eigene `run-dot`-Keyframe: nur `opacity .55↔1`, 1.2s | Zweck ist „läuft", nicht „hört zu"; Scale an 6px flimmert; Shadow unnötig |
| Orb-Übergang `background .5s ease, box-shadow .5s ease` | `background 200ms` + `::after`-`opacity 160ms`, starke Exit-Kurve | 500ms fühlt sich träge an (Framework: Komponenten 150–250ms); Stop muss sofort sichtbar reagieren |
| `banner-in .25s ease` translateX(12px), kein Exit | Enter 200ms `cubic-bezier(0.23,1,0.32,1)` 8px; Exit 120ms Opacity via WAAPI vor `remove()` | Exit schneller als Enter; starke ease-out-Kurve statt schwachem Built-in |
| kein `:active`-Feedback auf Buttons/Tabs/Kacheln | `transform: scale(0.97)` (Kacheln 0.985), `transition: transform 140ms` Exit-Kurve | Pressables müssen den Druck bestätigen (100–160ms-Fenster) |
| Hover-Transitions ungegated | Bewegungs-Hover hinter `@media (hover:hover) and (pointer:fine)` | Touch löst Hover fälschlich aus |
| Reduced-Motion deckt Orb/Banner/Run-Dot nicht | gezielter Block: alle Endlos-/Bewegungs-Animationen aus, Farb-/Opacity-Feedback bleibt (120ms) | „Fewer and gentler, not zero" — Zustände bleiben ohne Bewegung vollständig lesbar |
| Zustandswechsel-Keyframes starten bei Re-Trigger von 0 | akzeptiert für Ambient-Loops; alle EINMALIGEN Effekte (Enter/Press/Copy) laufen als Transitions | Transitions retargeten sauber; Loops werden per Klassentausch ohnehin ersetzt |
| kein `action-running`-Signal am Instrument | `.luenette-sweep`: konisches Highlight, `rotate` 3.6s **linear**, nur bei Container-Klasse | konstante Tätigkeit = linear; Signature-Träger (Lünette) statt zweitem Glühzentrum |
| Ansichts-/Nachrichtenwechsel hart | Enter-only Fade+4px (240/180ms), Exit sofort | Anti-Jarring mit räumlicher Ruhe; „exit faster than enter" |

**Bewusste Nicht-Animationen (Framework Stufe 1):** Esc/Stop-Wirkung, Strg+Enter-Senden, Tab-/Fokuswege, Skip-Link, Fenstermodus-Größenwechsel (pywebview nativ), Suche-Filterung (Tastatur, hochfrequent), Skeleton-Zeilen, Fokusringe.
