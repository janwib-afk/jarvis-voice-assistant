# Phase 7 — Initial Findings (Web Interface Guidelines Audit)

- **Audit-Datum/-Zeit:** 2026-07-13 00:57 (lokal)
- **Skill:** `web-design-guidelines` v1.0.0 (vercel) — `.agents/skills/web-design-guidelines/SKILL.md`
- **Guidelines-Quelle (frisch geladen):** `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` (offiziell, kostenlos, kein Tracking — der eine dokumentierte externe Zugriff dieser Phase)
- **Untersuchte Dateien:** `frontend/index.html`, `frontend/style.css`, `frontend/design-tokens.css`, `frontend/main.js`, `frontend/settings.js`, `frontend/music.js`, `frontend/assets/fonts/*` (woff2 + OFL-Lizenzen), relevante `jarvis-launcher.pyw`-Teile; Gegenprüfung Backend: `server.py` (`_public_settings`), `config_loader.py` (`PROTECTED_KEYS`/`UI_EDITABLE_KEYS`).
- **Methode:** Statische Regel-Gegenprüfung aller WIG-Kategorien + gestütztes Harness (127.0.0.1:8341, Dummy-Keys) für Fokus-/Struktur-Evidenz. **Keine Korrekturen in diesem Dokument** (Auftrag Teil 1).
- **Direkt durch den Skill ausgelöste Aktionen:** ein WebFetch der Guidelines-Quelle (o. g.). Keine Skript-Ausführung, keine Installs, keine Pausen.

## Bereits erfüllt (Phase ≤6, verifiziert)

- `lang="de"`, Viewport ohne `user-scalable=no`, `<title>`, Landmarken (`banner`/`nav`/`main`/`footer`), Skip-Link, Heading-Hierarchie h1→h2→h3.
- **Tastaturfokus sichtbar** auf allen fokussierbaren Buttons (globaler `:focus-visible` 2px Messing-Ring — Tab-Sequenz gemessen: skip-link, pn-btn, wm-btn, btn-min/close, btn-copy-all, msg-copy, stop-btn, mute-btn = Ring sichtbar). Inputs zeigen Fokus per Rahmen+Halo.
- reduced-motion vollständig (Phase 5/6), nur `transform`/`opacity`, **kein `transition: all`**, Kontraste ≥4.5 AA, `…` statt `...` (UI), Zeiten via `toLocaleTimeString('de-DE', …)` (Intl), Label-Wrapping der Settings-Inputs, `text-wrap: balance/pretty` auf Titeln/Rede.
- **Sicherheit (Datenschutz, Priorität 1):** GET /settings baut die Antwort in `server.py::_public_settings()` ausschließlich aus `UI_EDITABLE_KEYS`; die beiden API-Keys liegen in `PROTECTED_KEYS` und sind strukturell ausgeschlossen (POST lehnt sie ab, Fehlermeldungen nennen nur Schlüsselnamen). Musik-/Command-APIs übertragen nur Datei-/Befehlsnamen, token-gesichert. **Kein Key im DOM/Form/Response.**

## Befunde (Format: Schweregrad | Datei:Zeile | Richtlinie | Problem | Auswirkung | Empfehlung)

### P0 — Kritisch
Keine.

### P1 — Wesentlich
Keine bestätigt. (Fokus sichtbar, Kernfunktionen erreichbar, Secrets geschützt, keine Tastaturfalle im geprüften Pfad.)

### P2 — Qualitätsproblem

- **P2 | frontend/index.html:2–6 (head) | Dark Mode: `color-scheme: dark`** | Fehlt auf `<html>`; die App ist reines Dark-Theme mit nativen `<select>` (Monitor/Zone, `main.js:1113`) und nativen Scrollbars. | Native Dropdown-Popups/Scrollbars/Form-Controls rendern im hellen OS-Chrome → Stilbruch und schlechtere Lesbarkeit der Auswahllisten. | `color-scheme: dark` auf `:root`/`<html>` (Inline-Boot-Style + design-tokens.css); optional `<meta name="theme-color">`.
- **P2 | frontend/style.css (body `align-items:center` + fixe `#win-bar` 38px) | Responsive Stabilität** | Im „Mitte"-Fenstermodus und bei 200 % Zoom wird `#app` höher als der Viewport; die vertikale Zentrierung schiebt die Lünette unter die fixe Titelleiste (Oberkante beschnitten). | Marken-Signature (Orb) im Mitte-Modus optisch beschnitten; kein Infoverlust (Orb `aria-hidden`, Statuswort sichtbar). | `align-items: safe center` (No-Op solange Inhalt passt) + Titelleisten-Freiraum; Fallback: Orb im Mitte-Modus leicht verkleinern. Danach verify_phase4 27/27. **[Carryover Phase 6]**
- **P2 | frontend/index.html:83–84, frontend/main.js (`.eb-close`) | A11y: Icon-only Button braucht `aria-label`** | `#btn-min` („−"), `#btn-close` („×") und der Banner-Schließer („×") haben nur `title`; der Accessible Name fällt auf das Glyph zurück. | Screenreader liest „minus"/„times" statt „Minimieren"/„Ausblenden"/„Schließen". | `aria-label` an allen drei Glyph-Buttons.
- **P2 | frontend/index.html:201–228 | Forms: `autocomplete`/`spellcheck`** | Settings-Inputs (Voice-ID, Obsidian-Pfade, Musikordner, apps) ohne `autocomplete`/`spellcheck`; `#text-form` hat `autocomplete="off"`, das Settings-Form nicht. | Passwortmanager-Popups auf technischen Feldern; rote Wellenlinien unter Pfaden/IDs. | `autocomplete="off"` am `#settings-form`; `spellcheck="false"` auf Voice-ID/Pfade/apps.

### P3 — Kosmetisch / optional

- **P3 | frontend/index.html:89, frontend/main.js (`showErrorBanner`) | A11y: Live-Region** | Fehler-Banner im `aria-live="polite"`-Container; echte Störungen (mic/ws) unterbrechen den SR nicht. | Kritische Fehler werden nicht assertiv angekündigt. | `role="alert"` für die Fehlerfamilie (polite nur für Warnungen). **[Carryover]**
- **P3 | frontend/main.js (`renderStatusCenter`/`showErrorBanner`) | Redundanz** | Gleiche Fehlermeldung erscheint gleichzeitig im Banner (oben) und in `#sc-error` (Fußleiste). | Doppelanzeige — genau das Muster, das quieter beim Zustandswort beseitigt hat. | `#sc-error` bei aktivem Banner knapp halten/unterdrücken. **[Carryover]**
- **P3 | frontend/style.css:1330–1334 (`.profile-action:focus`), ähnl. `#cc-profile-input:focus` | Fokus-Konsistenz** | `:focus { outline: none }` unterdrückt den globalen Messing-Ring; ersetzt nur durch Rahmen-/Farbwechsel (hover-gleich). | Tastaturfokus auf Profil-Aktionen weniger deutlich als auf anderen Buttons. | `outline: none` entfernen bzw. Ring über `:focus-visible` erhalten (Control-Center zu verifizieren).
- **P3 | frontend/index.html:66 (boot-fallback „lädt"), text-input-Placeholder | Typography: Ladezustand endet mit `…`** | „J.A.R.V.I.S. lädt" ohne Ellipse. | Konvention. | „lädt…"; Placeholder-Feinschliff optional.
- **P3 | frontend/index.html (kbd-hint „Strg+Enter", Fußleiste) | Typography: `&nbsp;`** | Tastenkürzel/Einheiten ohne geschütztes Leerzeichen. | Umbruch mitten im Kürzel möglich (schmal). | `&nbsp;` in „Strg+Enter" / „Esc". 
- **P3 | frontend/main.js (`renderMap` Monitor-Label) | Responsive** | Monitor-Labels in schmalen Buchten abgeschnitten. | Kosmetisch; Weg B (Selects) bleibt lesbar/bedienbar. | Kurzform/Tooltip. **[Carryover]**
- **P3 | frontend/style.css (`#device-bar`) | Responsive** | 9px H-Overflow @375px (kbd-hint `nowrap` + zwei 44px-Buttons). | Unter dem schmalsten realen Fenstermodus (Panel 420px, dort kbd-hint ausgeblendet → 0 Overflow). | `flex-wrap` am device-bar (nur bei künftigem Bedarf). **[Carryover]**
- **P3 | frontend/design-tokens.css (@font-face) | Performance** | Kein `<link rel="preload">` für den kritischen Body-Font. | Minimaler FOUT-Spielraum (lokal, `font-display: swap` gesetzt). | Optionaler Preload des Regular-Gewichts. 
- **P3 | docs/design-direction/DESIGN.md §10/§14 | Doku-Abgleich** | Wortlaut „Fassung bleibt in ALLEN Zuständen ruhig" vs. Phase-5-Lünetten-Sweep bei `action-running`. | Doku widerspricht produktiver (bewusster) Motion-Evolution. | Ausnahme in DESIGN nachziehen. **[Carryover]**

## N/A / bewusste Ausnahmen (keine Befunde)

- **URL reflects state** — Jarvis ist eine pywebview-Desktop-App ohne Routing/URLs; deep-linking/`<a>`-Multi-Click nicht anwendbar.
- **Safe-area-insets / theme-color / preconnect** — Desktop-WebView ohne Notch/CDN; `env(safe-area-*)` und `preconnect` nicht anwendbar (`theme-color` als optionaler P3 gelistet).
- **`<img>` width/height/lazy** — keine Rasterbilder im Frontend (nur CSS/SVG + woff2).
- **Inline-Hex im Boot-Style** (`index.html` `<style>`) — bewusste Resilienz-Ausnahme (muss ohne geladene CSS funktionieren; in design-tokens.css dokumentiert).
- **Konsolen-`console.warn(... '...')`** — Debug-Ausgabe, keine UI-Typografie.

## Zusammenfassung

0×P0 · 0×P1 · 4×P2 · 10×P3. Erwartete Behebung: alle P2 + risikoarme P3; verbleibende P3 begründet offen. Endgültige Schweregrade nach Browser-Verifikation (Teil 2–12) in `FINAL_FINDINGS.md`.
