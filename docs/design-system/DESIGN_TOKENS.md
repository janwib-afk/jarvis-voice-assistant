# Jarvis Design-Tokens — Referenz (Phase 1, 2026-07-11)

Quelle der Wahrheit: [`frontend/design-tokens.css`](../../frontend/design-tokens.css) (eingebunden in `index.html` **vor** `style.css`).
Alle Werte sind unverändert aus dem Ist-Zustand extrahiert — Phase 1 hat kein Redesign durchgeführt (Beweis: `verification/DIFF_REPORT.md`, 27/27 pixel-identisch).

**Konventionen**
- Getrennte Semantik = getrennte Tokens, auch bei gleichem Startwert (`--color-state-warning` == `--color-accent-bright`; `--duration-banner` == `--duration-hover`). Phase 2 kann Rollen unabhängig umfärben.
- Drei historisch gewachsene Gold-Alpha-Familien bleiben exakt erhalten und sind je Familie benannt: **Border** rgba(200,155,70,α) · **Chrome** rgba(200,155,50,α) · **Hover/Fokus** rgba(200,150,50,α). Vereinheitlichung = Phase-2-Entscheidung.
- „Fundstellen" nennt repräsentative Selektoren (Muster), nicht jede Zeile.

## Farbe: Canvas & Flächen

| Token | Wert | Zweck | Fundstellen (repräsentativ) |
|---|---|---|---|
| `--color-bg-canvas` | `#0d0b09` | Seitenhintergrund | `body` |
| `--color-bg-input` | `rgba(255,255,255,0.02)` | Eingabe-/Kontrollflächen | Settings-Inputs, `#cc-profile-input`, Mute-/Stop-Button |
| `--color-bg-banner` | `rgba(30,16,12,0.94)` | Fehlerbanner-Fläche | `.error-banner` |
| `--color-bg-chip` | `rgba(13,11,9,0.85)` | Map-Chip-Fläche (Canvas-Alpha) | `.map-chip` |
| `--color-bg-monitor` | `rgba(200,155,70,0.03)` | Monitor-Fläche in der Map | `.map-monitor` |
| `--color-bg-monitor-label` | `rgba(200,155,70,0.04)` | Monitor-Kopfzeile | `.map-monitor-label` |
| `--color-bg-danger-soft` | `rgba(140,35,25,0.22)` | rote Kontroll-Hover-/Mutefläche | `#mute-btn.muted`, `#stop-btn:hover` |
| `--color-bg-danger-chrome` | `rgba(175,45,35,0.14)` | Schließen-Button-Hover | `#btn-close:hover` |

## Farbe: Text

| Token | Wert | Zweck | Fundstellen |
|---|---|---|---|
| `--color-text-primary` | `#c4b49a` | Primärtext | `body`, `#cc-profile-input` |
| `--color-text-secondary` | `#7a5c38` | Sekundär-/Labeltext (häufigste Farbe, 24×) | Labels, `h2/h4`, Tab-/Buttontext, `#status.active` |
| `--color-text-muted` | `#6a5030` | gedämpfte Meldungen/Details | `.ae-detail`, `#music-msg`, `#cc-map-status` |
| `--color-text-dim` | `#3a2e22` | leiseste Textstufe: Zeitstempel, Platzhalter, H3 | `.msg-time`, `::placeholder`, `#action-history h3` |
| `--color-text-faint` | `#4a3826` | Leere-Zustände, Musik-Status | `.cc-empty`, `#music-status` |
| `--color-text-soft` | `#a08060` | weicher Akzenttext/Icons | Mute-/Stop-Icon, `#mic-mode label` |
| `--color-text-tertiary` | `#8a6c46` | Inbox-Fließtext | `#cc-inbox-text` |
| `--color-text-note` | `#5a4630` | Fußnoten | `.settings-note` — *Vereinheitlichen-Kandidat (nahe faint/muted)* |
| `--color-text-user-msg` | `#3e3026` | „Du:"-Transcript-Text | `.msg.user .msg-text` |
| `--color-text-banner` | `#c4a284` | Fehlerbanner-Fließtext | `.error-banner` |
| `--color-text-banner-dim` | `#8a6050` | Banner-Schließen-Symbol | `.eb-close` |

## Farbe: Titelleisten-Chrome (Familie 200,155,50)

| Token | Wert | Zweck | Fundstellen |
|---|---|---|---|
| `--color-text-chrome` | `#2a1e12` | inaktive Chrome-Buttons | `.wm-btn`, `.pn-btn`, `#btn-min/-close` |
| `--color-text-chrome-hover` | `#8a6030` | Chrome-Hover-Text | dieselben `:hover` |
| `--color-text-chrome-active` | `#b6832f` | aktiver Chrome-Text | `.wm-btn.active`, `.pn-btn.active` |
| `--color-bg-chrome-track` | `rgba(200,155,50,0.06)` | Switch-/Nav-Hintergrundschale | `#window-mode-switch`, `#page-nav` |
| `--color-bg-chrome-hover` | `rgba(200,155,50,0.10)` | Chrome-Hover-Fläche | `.wm-btn:hover` u. a. |
| `--color-bg-chrome-active` | `rgba(200,155,50,0.16)` | aktive Chrome-Fläche | `.wm-btn.active` u. a. |

## Farbe: Akzent, Status, Dots

| Token | Wert | Zweck | Fundstellen |
|---|---|---|---|
| `--color-accent-primary` | `#b08850` | Primärakzent (Jarvis-Text, Inputs, Buttons, `accent-color`) | `.msg.jarvis`, `.app-btn`, `#panel-answer` |
| `--color-accent-bright` | `#d4a032` | heller Akzent: Hover/Aktiv/Busy | `.cc-tab:hover/.active`, `.app-btn.busy` |
| `--color-state-success` | `#8fa35c` | Erfolgsmeldung | `#settings-msg.ok` |
| `--color-state-danger` | `#c06060` | Fehlertext/-zustände | `.eb-label`, `#sc-error`, `.err`-Varianten |
| `--color-state-danger-strong` | `#c05050` | intensiver Gefahren-Hover | `#btn-close:hover` |
| `--color-state-warning` | `#d4a032` | Warnrolle (reserviert; Startwert == accent-bright) | *noch keine Fundstelle — bewusst angelegt* |
| `--color-dot-off/-ok/-run/-err` | `#3a2e22/#b08850/#d4a032/#c06060` | Statuspunkt-/Toggle-Knopf-Füllungen | `.sc-dot`, `.ae-dot`, `.cc-dot`, `.app-toggle-knob` |

## Farbe: Border-Familie (200,155,70)

`--color-grid-line` 0.03 (Map-Raster) · `--color-border-divider` 0.06 (Sektionslinien) · `--color-border-column` 0.07 (Spaltenlinien) · `--color-border-dim` 0.10 · `--color-border-subtle` 0.12 (ruhende Kontroll-Borders) · `--color-border-input` 0.14 (Inputs + Zuweisungszonen) · `--color-border-copy` 0.15 · `--color-border-button` 0.20 · `--color-border-default` 0.22 (Standard-Interaktions-Border) · `--color-border-hover-soft` 0.28 · `--color-border-chip` 0.35 · `--color-border-ok` rgba(176,136,80,0.7).

## Farbe: Hover/Fokus-Familie (200,150,50) — *Vereinheitlichen-Kandidat mit Border-Familie*

`--color-hover-bg-soft` 0.08 · `--color-hover-border-mute` 0.25 · `--color-focus-border-input` 0.35 (Input-Fokus + Copy-Hover) · `--color-hover-border-button` 0.40.

## Farbe: Interaktion/Selektion (220,170,55)

`--color-hover-border` 0.5 · `--color-hover-border-strong` 0.6 (Saving + Chip-Hover) · `--color-selected-border` 0.65 · `--color-focus-border` 0.4 (Modul-/Zonen-Fokus) · `--color-ghost-bg` 0.1 · `--color-ghost-border` 0.35 · `--color-zone-hover-bg` 0.05.

## Farbe: Gefahr-Border (190,55,45)

`--color-danger-border-soft` 0.35 (Banner) · `--color-danger-border-mute` 0.38 · `--color-danger-border-deletable` 0.5 · `--color-danger-border-strong` 0.6 (Confirm/err) · `--color-danger-border-accent` 0.8 (Banner-Leiste).

## Glows, Schatten, Scrollbar

| Token | Wert | Zweck |
|---|---|---|
| `--glow-dot-ok` | `0 0 6px rgba(200,155,70,0.4)` | Gold-Dot-Schein (ok) |
| `--glow-dot-run` | `0 0 6px rgba(220,170,55,0.5)` | laufende Aktion |
| `--glow-dot-err` | `0 0 6px rgba(190,55,45,0.4)` | Fehler-Dot |
| `--glow-selected` | `0 0 10px rgba(220,170,55,0.18)` | Auswahl-Schein (Tabs, Musik, Module) |
| `--glow-selected-strong` | `0 0 10px rgba(220,170,55,0.3)` | Chip-Auswahl |
| `--glow-busy` | `0 0 8px rgba(220,170,55,0.25)` | Busy-Button |
| `--glow-ghost` | `inset 0 0 14px …0.12, 0 0 10px …0.1` | Zonen-Ghost |
| `--shadow-chip` | `0 0 8px rgba(0,0,0,0.5)` | Chip-Abhebung |
| `--color-scrollbar` / `-thumb` | `rgba(180,130,60,0.12/0.18)` | schmale Scrollbars |

## Orb & Lamp (Identitätskern)

`--orb-<idle|listening|thinking|speaking|muted|error>-core/-edge` — die 12 Radial-Gradient-Stops des Orbs (`#2e1e0c/#130d07`, `#c07830/#6e3e12`, `#d4a032/#7c5a18`, `#c87840/#6e3e1c`, `#241a10/#100c08`, `#7c2a20/#2a0f0a`).
`--lamp-primary` `rgba(195,115,30,0.10)` · `--lamp-primary-fade` `rgba(160,85,15,0.05)` · `--lamp-ground` `rgba(180,100,20,0.05)` — Hintergrund-Atmosphäre (`body::before/::after`).
**Bewusst literal geblieben:** die mehrstufigen Orb-`box-shadow`-Stacks und Keyframe-Interna (einmalige Werte, werden in Phase 2 als Glow-System neu entschieden).

## Typografie

| Token | Wert | Zweck |
|---|---|---|
| `--font-family-base` | Systemstack (`-apple-system, …, 'Segoe UI', sans-serif`) | Fließtext |
| `--font-family-chrome` | `'Segoe UI', sans-serif` | Titelleisten-Buttons |
| `--font-weight-light/-regular/-semibold` | 300/400/600 | Grundgewicht/Labels/Banner-Label |
| `--font-size-2xs…-2xl` | 8/9/10/11/12/13/14/18 px | gesamte Größenskala (Ausnahmen: 11.5px ×4, 12.5px ×1 — literal, *Vereinheitlichen*) |
| `--line-height-tight/-list/-inbox/-panel/-body` | 1.4/1.5/1.55/1.6/1.65 | Zeilenhöhen je Kontext (*Vereinheitlichen-Kandidaten*) |
| `--tracking-label/-button/-micro/-caps-wide/-display` | 0.08/0.1/0.12/0.2/0.28 em | Laufweiten-Rollen (Kleinwerte 0.01–0.06 em + 0.14 em literal, *Prüfen*) |

## Spacing

Wertbenannte Skala `--space-2…-48` (2/3/4/5/6/7/8/9/10/12/14/16/18/20/24/28/48 px) — von der Skill-CLI-Extraktion bestätigt (gerenderte Spacing-Skala). **Migriert: alle `gap`-Werte.** Einzelne `margin`/`padding` sowie alle Kompositwerte (`padding: 4px 10px` …) bleiben in Phase 1 bewusst literal — geringes Theming-Potenzial, hohes Editrisiko; Phase 2 entscheidet das Layoutsystem neu.

## Radius

`--radius-xs/-sm/-md/-lg/-xl` = 3/4/5/6/7 px · `--radius-round` = 50 %. (1 px Webkit-Scrollbar-Thumb literal, *Prüfen*.)

## Motion

| Token | Wert | Zweck |
|---|---|---|
| `--duration-ghost` | 0.15s | Ghost-Geometrie |
| `--duration-fast` | 0.2s | Chrome-/Opacity-Wechsel |
| `--duration-hover` | 0.25s | Standard-Interaktions-Hover |
| `--duration-banner` | 0.25s | Banner-Einflug (eigene Rolle) |
| `--duration-fade` | 0.3s | Ein-/Ausblenden |
| `--duration-slow` | 0.4s | Statusfarbwechsel |
| `--duration-orb` | 0.5s | Orb-Zustandsübergang |
| `--duration-map-pulse` … `--duration-pulse-listen` | 0.6/0.65/0.85/1.1/1.2/1.8 s | benannte Animationsdauern (Map, Sprech-, Denk-, Fehler-, Aktions-, Zuhör-Puls) |
| `--ease-standard/-pulse/-exit` | ease / ease-in-out / ease-out | Easing-Rollen (unspezifizierte Transitions behalten Browser-Default `ease`) |

## Layering

`--z-chrome` 999 (Mute/Stop/Status-Center) · `--z-titlebar` 1000 (`#win-bar`) · `--z-banner` 1100 (`#error-stack`). Lokale Stapelwerte 0–3 (Map-Layer) und der Boot-Fallback (9999, inline in index.html) bleiben bewusst literal.

## Bewusste Ausnahmen (nicht tokenisiert)

1. **Inline-Boot-Style in `index.html`** — Resilienz, falls `/static` nicht lädt; referenziert keine Tokens.
2. **Orb-Schatten-Stacks + alle Keyframe-Interna** — einmalige Kompositionen, Phase-2-Glow-System.
3. **`jarvis-launcher.pyw`** — Tray-Farben `#c8922a`/`#e8b84b` (Python-Konstanten, kein CSS): bei Phase-2-Palettenwechsel manuell nachziehen.
4. **Font-Größen 11.5/12.5 px, Kompositabstände, Kleinst-Laufweiten, `line-height: 1`, `border-radius: 1px`, lokale z-index** — je mit Marker in `CURRENT_DESIGN_SYSTEM.md`.

## Skill-Extraktion (Gegenprobe)

`npx extract-design-system http://127.0.0.1:8341` (Skill `extract-design-system`, Outputs unter [`extraction/`](extraction/)): 0 Palette-Farben (dunkle, niedrig gesättigte Palette unter der Tool-Heuristik), Fonts „Segoe UI" ✓, Spacing-Skala 2–48 px ✓ (deckt sich mit `--space-*`), `cssVariables: {}` — Beleg, dass das Ist-System vor Phase 1 keinerlei CSS-Custom-Properties exponierte.
