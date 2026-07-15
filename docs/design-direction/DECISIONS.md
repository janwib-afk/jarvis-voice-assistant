# Designentscheidungen — „Warm Analog Intelligence"

## Nachtrag Phase 3 (UX, 2026-07-11)

1. **ui-ux-pro-max-Gegenprobe:** Die `--design-system`-Empfehlung der Skill-Datenbank („Dark Mode OLED" #020617, Grün-Akzent, Orbitron/JetBrains Mono, Cyberpunk/HUD-Mood) kollidiert frontal mit den Auftrags-Anti-Mustern — Phase-2-Richtung bleibt verbindlich; Skill wurde für UX-Guidelines (99er-Katalog) und Checklisten §1–§3 genutzt, nicht für Stil.
2. **Kein `--persist`:** hätte `design-system/MASTER.md` an die Repo-Wurzel geschrieben (außerhalb erlaubter Phase-3-Pfade und redundant zu DESIGN.md).
3. **UX-Entscheidungen** (Details `docs/ux/`): Aktions-Dedupe (volle Historie nur KZ, laufende Aktion in Statuszeile) · Klartext-Statuszeile + Dot-Semantik ok=Moos · nicht-visuelle Monitor-Zuweisung per Selects (gleichwertiger Weg B) · Stop-Button stoppt IMMER direkt, nur Esc durchläuft die Abbruch-Kaskade · Fehlerzeilen reservieren Platz (mousedown-blur-Layout-Shift verschluckte Klicks — real reproduziert) · Skip-Link-Ziel je Modus · Begrüßung weicht nach erster Interaktion.
4. **Frischer Reviewer-Subagent** fand 8 Befunde (u. a. Fußleiste außerhalb des Frames in allen Modi, Kaskade am Stop-Button, fehlende Banner-Pfade, Panel-Zusagen gebrochen, Drei-Kanal-Widerspruch Statuszeile/Orb/Fußleiste) — alle behoben, je mit neuem Regressions-Check in `docs/ux/tools/capture_ux.py` (34/34 grün).

---

# Designentscheidungen Phase 2 — „Warm Analog Intelligence" (2026-07-11)

Protokoll der wichtigsten Entscheidungen, Verworfenes und offene Punkte. Verbindliche Richtung: [`DESIGN.md`](DESIGN.md).

## Skill-Prozess (frontend-design)

- **Pass 1 (Design-Plan):** Subjekt verankert („Instrument im Arbeitszimmer EINES Menschen", nicht Dashboard); Kernpalette 6 benannte Werte (Espresso `#19120c`, Pergament `#e7ddc8`, Bernstein `#e7a854`, Messing `#9d865b`, Kupfer `#bd7452`, Moos/Ziegel-Paar); Typo-Trio Fraunces/Plex Sans/Plex Mono; Layout „Instrument über Journal, Werkbank im Kontrollzentrum"; Signature = Orb in Messing-Lünette.
- **Pass 2 (Anti-Default-Review) — vorgenommene Revisionen:**
  1. Lünetten-Skala **ohne Zahlen** (Striche only) — Auftrags-Anti-Muster „zufällige technische Nummern".
  2. Kontrollzentrum von „Karten" auf **Buchten + Lichtkanten** umgestellt — gegen Rundkarten-Einerlei und Rahmen-Tapete.
  3. Fraunces von Überschriften-überall auf **nur Gesprächsstimme/Begrüßung** verknappt — gegen Editorial-Kippen.
  4. Skill-Default #2 („near-black + ein Akzent") aktiv entschärft: Canvas eindeutig braun, **vier funktionsgebundene Akzentfamilien** im Prototyp nachweisbar (Kupfer-Links, Moos-Ok-Dots, Ember-Warnbanner, Bernstein-Aktivität).
- **Selbstkritik am Screenshot (2 Revisionsrunden):**
  1. `hidden`-Attribut verlor gegen `display:flex` → `[hidden]{display:none !important}` (Kontrollzentrum war unsichtbar — im ersten Capture entdeckt).
  2. Jarvis-Serife rendert zu schwer → Gewicht 350 + `opsz 17`; Begrüßung 340.
  3. Listening-Orb las sich als massive Goldkugel → Kern-Falloff auf 60 % + tieferer Innenschatten („Licht im Glas").
  4. Profil-Aktionen kollidierten bei 1000px mit der Apps-Spalte → `flex-wrap` in der Profilzeile.
  5. Chanel-Regel angewandt: angedachte zweite Skalen-Gravur am Modus-Schalter ersatzlos gestrichen (eine Gravur = die Lünette).

## Verworfene Alternativen (mit Grund)

| Verworfen | Grund |
|---|---|
| Uppercase-HUD beibehalten (Ist-Identität) | Hauptquelle der heutigen Sterilität; Auftrag verbietet Versalien-Tapete |
| Reines System-Font-Set (Segoe-only) | keine unverwechselbare Stimme möglich; Wärme-Anteil hängt an der Serife |
| McIntosh-/Röhren-Blau als Zweitakzent | Auftrag verbietet kaltes Blau; bricht die warme Temperatur |
| Foto-/Volltextur-Material (Holz, Leder, gebürstetes Metall als Bild) | Anti-Muster; Performance; kippt in Steampunk-Kostüm |
| Chat-Bubbles fürs Transcript | Messenger-Anmutung statt Journal; Auftrag: „hochwertiges Gesprächsprotokoll" |
| Glow-Rahmen um aktive Karten (heutiges Muster) | Licht wäre Dekoration; Prinzip „Licht ist Information" |
| Zweite Signature (Messing-Zeiger im Modus-Schalter) | Boldness an genau einer Stelle; gestrichen in Pass 2 |
| Fraunces „WONK"-Achse aktivieren | zu verspielt für Präzisionsanspruch |

## Bewusst eingegangene Risiken

1. **Drei-Stimmen-Typografie** (Serifen-Rede im dunklen UI) — Begründung in DESIGN.md §1; Absicherung: Verknappung + Mono-Gegengewicht; Prototyp-Beleg wirkt journal-, nicht magazinhaft.
2. **Dot-Semantik-Wechsel** (Ok wandert von Gold zu Moos; Bernstein = nur noch Aktivität) — semantisch sauberer, aber Umlernen für Jan; Phase 4 sollte die Legende in der Statusfußzeile 1:1 mitliefern (Klartext steht ohnehin daneben).
3. **Hellere Canvas-Fläche** (#19120c statt #0d0b09) — mehr Wärme/Zeichnung, minimal weniger „Kino"; Lampen-Glow kompensiert.

## Offene technische Fragen (für Phase 3/4)

1. Fraunces variable im WebView2 des pywebview-Launchers: `font-variation-settings`-Support gilt als gegeben (Chromium), realer Gerätetest steht aus.
2. `error-brick`-Fließtextkontrast 4.2:1 → Entscheidung in Phase 4: Titel-only-Regel (wie Prototyp) oder Wert auf ≥4.5 anheben (Orb-error-Paar dann mitziehen).
3. Transcript-Markup: Sprecher als eigenes Element erfordert minimalen `main.js`-Eingriff (renderTranscript) — in Phase 4 einplanen, Invarianten unberührt.
4. Fenster-Punkte (–/×) von Typografie auf 1.6px-SVG umstellen (Icon-Konsistenz §11).
5. Monitor-Label bricht in schmalen Buchten zweizeilig (Fokus-Modus) — akzeptiert; alternativ Kurzform „links · 1920×1080" prüfen.
6. Statisch nah beieinander: listening vs. thinking — Differenzierung übernimmt in Phase 5 primär die Pulsfrequenz; falls nötig thinking-Hue weiter Richtung 90 ziehen.

## Lizenzen & Assets

| Asset | Lizenz | Quelle | Ort |
|---|---|---|---|
| Fraunces (variable, roman) | SIL OFL 1.1 | Undercase Type, bezogen via Google Fonts | `prototype/assets/fonts/fraunces-*.woff2` + `OFL-Fraunces.txt` |
| IBM Plex Sans 400/500/600 | SIL OFL 1.1 | Google Fonts (IBM) | `plex-sans-*.woff2` + `OFL-IBMPlexSans.txt` |
| IBM Plex Mono 400/500 | SIL OFL 1.1 | Google Fonts (IBM) | `plex-mono-*.woff2` + `OFL-IBMPlexMono.txt` |
| Körnung/Messing/Skala | — (CSS/Inline-SVG, generiert) | dieses Repo | `prototype.css` |

Gesamtgewicht Fonts: 403 KB (12 woff2, latin+latin-ext). Keine weiteren Bild-/Texturassets. Keine Laufzeit-Netzabhängigkeit.

## Browser-Validierung (Evidenz)

18 Screenshots unter [`screenshots/`](screenshots/) (Playwright, `tools/capture_prototype.py`, file://): drei Modi × Gespräch/Kontrollzentrum, Orb ×6, vier Meldungsfamilien, Formular inkl. Disabled/Loading, Musik, Leerzustand, Hover ×3, Tastaturfokus, reduced-motion, Kleinhöhen-Stress 1280×640, langes Kompositum im Lauftext. Fonts geladen (`document.fonts.check` 3×true), 0 Konsolenfehler, 0 unbeabsichtigte horizontale Überläufe. Die 10 Bewertungsfragen des Auftrags: alle positiv beantwortet (Begründungen in DESIGN.md §1–§13; kritische Restpunkte oben unter „Offene Fragen").
