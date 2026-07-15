# Jarvis — Designrichtung „Warm Analog Intelligence" (Phase 2, 2026-07-11)

**Verbindliche gestalterische Quelle ab Phase 3.** Erarbeitet mit dem Skill `frontend-design` (Zwei-Pass-Prozess, Anti-Default-Review, Selbstkritik am Screenshot). Validiert am isolierten Prototyp [`prototype/`](prototype/) — Belege unter [`screenshots/`](screenshots/). Alle Farb-/Typo-Werte sind **vorgeschlagene Zielwerte**; die produktive Migration erfolgt in Phase 4 (Tokens in `frontend/design-tokens.css` bleiben bis dahin unverändert).

---

## 1. Designthese

Jarvis ist kein Dashboard und keine Website — es ist **ein Instrument im Arbeitszimmer eines einzelnen Menschen**. Die Oberfläche verkörpert das, was ein hochwertiges Studiogerät der analogen Ära verkörperte: Ein mattes, dunkles Gehäuse aus warmem Espresso, in dem genau ein Ding lebt — ein warm glühender Kern in einer gedrehten Messing-Fassung. Alles andere ist ruhige, präzise Beschriftung. Die Zukunft steckt nicht in Neonlinien, sondern darin, dass dieses Instrument zuhört, denkt und antwortet.

Die emotionale Wirkung: **Abendlicht statt Serverraum.** Man setzt sich zu Jarvis wie an einen guten Schreibtisch — das Licht ist warm, die Schrift hat eine Stimme, nichts blinkt um Aufmerksamkeit. Vertrauen entsteht durch Ruhe und Präzision zugleich: Pergamenttext mit Buchsatz-Anmutung für das Gespräch, Millimeter-genaue Mono-Werte für die Technik.

Vintage und Futurismus verbinden sich über **Material und Licht, nicht über Kostüm**: Die Fassung ist Messing, aber aus CSS-Licht gedreht, nicht fotografiert; die Skala trägt Striche, keine nostalgischen Ziffern; der Kern glüht wie Röhrenelektronik, reagiert aber wie ein Zustandsautomat. Gemütlich wird das Ganze durch die Farbtemperatur (alles zwischen Espresso und Bernstein), durch Serifenwärme in Jarvis' Stimme und durch das eine Lampenlicht am Rand — nicht durch aufgeklebte Texturen.

**Das bewusst eingegangene Risiko: die Drei-Stimmen-Typografie.** Jarvis antwortet in einer Serife (Fraunces), Jan schreibt in einer humanistischen Sans (IBM Plex Sans), die Maschine notiert in Mono (IBM Plex Mono) — eine Serifen-Stimme im dunklen Interface ist unüblich und könnte ins Editoriale kippen. Sie passt zum Produkt, weil Jarvis' Kern das gesprochene Wort ist: Die Antwort des Assistenten ist der emotionale Mittelpunkt und darf als einzige Fläche literarische Wärme tragen. Gehalten wird das Risiko durch strenge Verknappung (Serife NUR für Jarvis-Rede, Begrüßung und Galerie-Titel) und durch die Mono-Präzision drumherum.

## 2. Zielwirkung

warm · ruhig · intelligent · hochwertig · persönlich · präzise · charakteristisch · langlebig · funktional · atmosphärisch — konkret: „ein Gerät, das man behalten möchte", nicht „eine App, die man benutzt".

## 3. Designprinzipien (verbindlich)

1. **Licht ist Information.** Glühen existiert nur an Zustandsträgern (Orb, Status-Dots, laufende Aktionen). Eine Fläche, die nichts meldet, leuchtet nicht.
2. **Ein Instrument, viele Beschriftungen.** Es gibt genau EIN inszeniertes Element — den gefassten Orb. Alles andere ist Beschriftung und Werkbank und bleibt flach und leise.
3. **Drei Stimmen, drei Schriften.** Jarvis spricht Serife, der Mensch Sans, die Maschine Mono. Keine Schrift übernimmt die Rolle einer anderen.
4. **Wärme kommt aus Farbtemperatur, Typografie und gerichtetem Licht** — nie aus Textur-Bildern, Ornamenten oder Antik-Effekten.
5. **Struktur durch Flächen und Lichtkanten, nicht durch Rahmen.** Borders sind Interaktionssignale (Hover/Fokus/Auswahl), keine Layoutwerkzeuge.
6. **Das Gespräch schlägt die Instrumentierung.** Das Journal ist immer die größte, ruhigste Fläche; Verwaltung ordnet sich unter.
7. **Mixed Case als Grundton.** Versalien sind seltene Gravur (nichts im Fließtext); Labels sprechen Deutsch in Satzschreibung, aktiv und konkret.
8. **Seltene Momente dürfen glänzen.** Begrüßung, Modus-Wechsel und Fehlerfall dürfen inszeniert sein; Routine (Hover, Tippen) reagiert unmittelbar und unspektakulär.

## 4. Anti-Prinzipien

Kein Neon-Cyan/kaltes Blau/Violett-Verlauf · kein Dauerglühen · kein Glassmorphism · keine identischen Rundkarten-Raster · keine Rahmen-Tapete · kein dekoratives Gold (Bernstein/Messing sind IMMER funktional: Leben/Struktur) · keine Zahnräder, Nieten, Alterspatina · keine Foto-Texturen (Holz/Leder) · keine Versalien-Tapete · keine Zufallslinien, -nummern, Deko-Diagramme · keine unruhigen Hintergrundanimationen · kein Gaming-HUD, kein Steampunk, kein generisches KI-Dashboard (Skill-Kalibrierung: bewusst KEIN „Near-Black + ein Akzent" — nachweisbarer Mehrklang aus vier funktionsgebundenen Akzentfamilien).

## 5. Farbpalette (Zielwerte für Phase 4)

Kanonische Quelle: [`tools/oklch_palette.py`](tools/oklch_palette.py) (OKLCH → Hex, deterministisch; vollständige Tabelle in [`tools/palette_table.md`](tools/palette_table.md)). Kernwerte:

| Token | OKLCH | Hex | Zweck |
|---|---|---|---|
| `--bg-canvas` | `oklch(0.190 0.016 62)` | `#19120c` | Canvas — dunkles Espresso (sichtbar braun, nicht schwarz) |
| `--bg-surface` | `oklch(0.225 0.018 64)` | `#221a13` | primäre Oberfläche (Journal, Module) |
| `--bg-raised` | `oklch(0.265 0.020 66)` | `#2c231b` | erhöht (Banner, Chips) |
| `--bg-inset` | `oklch(0.155 0.014 60)` | `#110b07` | eingelassen (Bucht, Eingaben, Orb-Bett) |
| `--text-primary` | `oklch(0.900 0.030 84)` | `#e7ddc8` | Haupttext — Pergament |
| `--text-secondary` | `oklch(0.730 0.035 78)` | `#b4a590` | Sekundärtext, Labels |
| `--text-muted` | `oklch(0.565 0.030 72)` | `#817363` | Zeitstempel, Nebeninfo |
| `--accent-amber` | `oklch(0.775 0.125 72)` | `#e7a854` | **Bernstein = Stimme/Leben**: Orb, laufende Aktivität, Primäraktion |
| `--accent-amber-deep` | `oklch(0.640 0.125 62)` | `#c17930` | gedrückt/aktive Kante |
| `--brass` | `oklch(0.630 0.065 82)` | `#9d865b` | **Messing = Struktur**: Fassung, ruhige Metallkanten |
| `--brass-bright` | `oklch(0.740 0.085 84)` | `#c4a76b` | **Fokusring + Auswahlkante** |
| `--copper` | `oklch(0.630 0.105 45)` | `#bd7452` | **Kupfer = Sekundär-Interaktion**: Links, Verweise |
| `--success-moss` | `oklch(0.630 0.075 128)` | `#7c9261` | Erfolg, „bereit/verbunden" |
| `--warning-ember` | `oklch(0.700 0.130 55)` | `#dc8748` | Warnung |
| `--error-brick` | `oklch(0.585 0.125 30)` | `#ba5c4e` | Fehler, Gefahr, Stumm-Ring |
| `--info-copper` | `oklch(0.680 0.085 48)` | `#c4886a` | Information |
| Orb-Paare | s. Tabelle | s. Tabelle | idle/listening/thinking/speaking/muted/error je core+edge |
| Alpha-Familie | — | — | `border-subtle` (Messing 0.22) · `border-strong` (0.55) · `edge-light` (Pergament 0.07) · `selection-bg` (Bernstein 0.14) · `focus-halo` (0.30) · `glow-amber/-error` (0.35) · `shadow-soft/-inset` (0.35/0.55) |

**Akzenthierarchie (verbindlich):** Bernstein nur für Leben/Aktivität/Primäraktion · Messing für Struktur/Auswahl/Fokus · Kupfer für sekundäre Interaktion/Links/Info · Moos/Ember/Ziegel ausschließlich Status. Gold-Deko ohne Funktion ist verboten.

**Kontrast (gemessen, `oklch_palette.py`):** Haupttext 13.7:1 (Canvas) / 12.7:1 (Surface) / 14.5:1 (Inset) · Sekundär 7.7:1 · Muted 4.0:1 (nur Nebeninfo) · Bernstein 8.9:1 · brass-bright 8.0:1 · Warn 6.7:1 · Info 6.3:1 · Moos 5.4:1 · Ziegel 4.2:1 (für Fließtext-Fehler die Banner-Titelgröße 12.5px/600 verwenden oder heller ziehen — Phase-4-Hinweis). **0 Fails** gegen die Ziele.

**Hover/Fokus/Disabled-Regeln:** Hover = Aufhellen innerhalb der Familie (`border-subtle→strong`, Text `secondary→primary`, Primärbutton `amber→#f0b569`); Fokus = IMMER 2px `brass-bright` Outline (+ optional `focus-halo`), nie nur Farbwechsel; Disabled = Opacity 0.4–0.45, keine Grau-Umfärbung (bleibt warm); Active/Pressed = `amber-deep` bzw. `border-strong`.

## 6. Typografiesystem

| Rolle | Schrift | Schnitte | Einsatz |
|---|---|---|---|
| Display/Charakter | **Fraunces** (variable, opsz 9–144, wght 300–700) | 340 (Begrüßung), 350 + `opsz 17` (Jarvis-Rede) | NUR: Jarvis-Antworten, Begrüßung, große Panel-Antwort, Galerie-/Bereichstitel |
| UI & Gespräch (Mensch) | **IBM Plex Sans** | 400/500/600 | Fließtext, Labels, Buttons, Navigation, Nutzer-Nachrichten |
| Technik | **IBM Plex Mono** | 400/500 | Zeitstempel, Systemwerte, Monitor-Maße, Platzierungen, Tastatur-Hinweise |

Alle drei: SIL OFL 1.1, **lokal gebündelt als woff2** (latin+latin-ext, zusammen 403 KB — kein Laufzeit-Webfont; Lizenztexte in `prototype/assets/fonts/`). Deutsch inkl. Umlauten/ß geprüft (Prototyp-Inhalte), Plex-Zahlen tabellenfest. Fallbacks: `Georgia, serif` · `'Segoe UI', system-ui, sans-serif` · `Consolas, monospace`.

**Stufen:** 11 (Mono-Meta) · 12 (Labels) · 12.5 (Meldungen) · 13.5 (UI-Fließtext) · 14 (Panel-Antwort) · 15.5 (Jarvis-Rede) · 20/21 (Formular-/Galerietitel) · 27 (Begrüßung). Zeilenhöhen: 1.25 Display · 1.55 UI · 1.62 Jarvis-Rede. Laufweite: neutral; Mono minimal offen; **kein `text-transform: uppercase` außer maximal einzelner Mikro-Gravuren** (im Prototyp: keine). Zeitstempel immer Mono/`text-muted`; Buttons Plex Sans 500 in Satzschreibung mit aktiven Verben („Speichern", „Öffnen", „Alles kopieren").

## 7. Spacing und Proportionen

8er-Grundraster mit halben Stufen: 4/8/12/16/24/32/48 (`--s-1…7`). Radien: **6 / 8 / 12 px + rund** (`--r-ctl/-field/-panel`) — drei Stufen statt heute fünf. Proportionen: Orb-Instrument 196px (Vollbild) / 132 (Fokus) / 92 (Panel) / 104 (CC-Spalte); Journal max 660px (Lesemaß ~75 Zeichen für Serife); Kontrollzentrum-Spalten 300 / flexibel / 264.

## 8. Oberflächen und Materialität

- **Matte Flächen:** `bg-canvas` mit hauchfeiner SVG-Körnung (Inline-Data-URI, ~0.5 KB, Opacity 0.028) — NUR auf dem Canvas, nie auf Bedienflächen.
- **Gerichtetes warmes Licht:** jede erhöhte Fläche trägt `inset 0 1px 0 edge-light` (Lichtkante oben) + `shadow-soft` nach unten; genau ein Lampen-Glow unten rechts (Erbe der Ist-Identität, halbierte Intensität).
- **Erhöht vs. eingelassen:** `bg-raised` + Wurfschatten für Meldungen/Chips; `bg-inset` + `shadow-inset` für Instrumentenflächen (Monitor-Bucht, Eingabefelder, Orb-Bett, Modus-Schale). Diese Zweiteilung ersetzt Karten-Dekor.
- **Messing-Detail:** ausschließlich an der Lünette (konischer Verlauf + Strichskala) und als 2px-Unterstreichung aktiver Tabs. Keine weiteren Metallzierden.
- **Bewusst flach:** Canvas selbst, Journal-Einträge (keine Bubbles!), Heute-Blöcke, System-/Aktionslisten, Formular-Umgebung.
- **Trennlinien:** 1px `border-subtle` nur an Spalten-/Sektionsgrenzen; Scrollbereiche schmal (`scrollbar-width: thin`, Messing-Alpha).
- **Fokusindikator:** 2px `brass-bright`-Outline, Offset 2px — global, sichtbar, verhandelbar ist nur der Halo.

## 9. Komponentenidentität

- **Navigation/Seitenwechsel:** Text-Tabs mit 2px-Messing-Unterstreichung (aktiv) bzw. `border-subtle` (Hover); Wortmarke „Jarvis." mit Bernstein-Punkt. Keine Boxen in der Kopfleiste.
- **Größenmodus-Schalter:** eingelassene Schale (`bg-inset`), aktiver Modus als erhöhter Stein (`bg-raised` + Lichtkante). Liest sich als Geräteschalter.
- **Transcript = Journal:** Marginalspalte mit Mono-Zeit, Sprecherzeile (Du/Jarvis), Rede in der jeweiligen Stimme; Kopieren erscheint bei Hover UND Tastaturfokus; Suche als eingelassenes Feld im Journalkopf; Quellen als Kupfer-Links; leerer Zustand lädt zum Handeln ein („Sag ‚Jarvis' — oder schreib unten die erste Nachricht."); Scroll innerhalb der Journalfläche.
- **Kontrollzentrum = Werkbank:** links Gesprächsspalte (Mini-Instrument + Journalausschnitt), Mitte Profil-Leiste (Text-Tabs + leise Aktionen, Löschen in Ziegel-Kontur) über der **Monitor-Bucht** (eingelassen, Mono-Beschriftung, 3×3-Zonen mit Chips), darunter „Heute" (drei flache Blöcke, Messing-Spiegelstriche, Leerzustände mit Kupfer-Handlung); rechts Apps (erhöhte Module: Name+Badge, Öffnen, Bernstein-Schalter, Mono-Platzierung), Aktionen (Dot+Mono-Zeit+Label+Detail), System (Mono-Liste mit Status-Dots).
- **Formulare:** eingelassene Felder mit Messing-Fokus, Labels Plex 500/12, Hinweise `muted`, Radios mit Bernstein-Akzent; Primärbutton Bernstein mit dunkler Schrift (`#1d1409`), Sekundär Kontur, Quiet-Buttons für Werkbank-Aktionen; Disabled 0.4; Loading mit kleinem Ring.
- **Badges/Statuspunkte:** Mono-Badges (App/URL) mit `border-subtle`; **Dot-Semantik neu: Moos = ok/bereit · Bernstein (+Glow) = läuft · Ziegel = Fehler · Muted = aus** — Bernstein wird damit vom Ok-Zustand entkoppelt (heute Gold=ok) und meint ausschließlich Aktivität.
- **Meldungen:** erhöhte Fläche, 3px-Statuskante links, Titel 600 in Statusfarbe, Text Pergament, Hinweis sekundär, ×-Schließen; vier Familien (Fehler/Erfolg/Warnung/Info) — Belege: `galerie--meldungen.png`.

## 10. Orb-Konzept (Signature)

**Aufbau (rein CSS):** gedrehte Messing-Lünette (konischer Verlauf) → gravierte Strichskala (repeating-conic, maskiert, OHNE Zahlen) → eingelassenes Fassungsbett (`bg-inset` + Innenschatten) → Glaskern (radialer Verlauf `core→edge` bei 60 %, Innen-Reflex oben, Tiefenschatten unten, Zustands-Glow außen).

| Zustand | Charakter | Kern/Rand | Glow |
|---|---|---|---|
| idle | glimmende Kohle — anwesend, nicht fordernd | `#53361f / #160d07` | keiner |
| listening | ruhiges Bernstein — „ich bin bei dir" | `#e4a250 / #542c07` | amber |
| thinking | helles Arbeitslicht, minimal gelber | `#ebc160 / #674600` | amber |
| speaking | warmes Sprechlicht, orange-lebendig | `#f0944e / #622b0c` | amber |
| muted | erloschen + matter Ziegel-Ring (2px) | `#251c15 / #0d0805` | keiner |
| error | Ziegelglut | `#8f392a / #2b0e0a` | error |

Die Fassung bleibt in ALLEN Zuständen identisch ruhig — nur das Licht im Glas ändert sich (Prinzip 1). Bewegung folgt in Phase 5 (`emil-design-eng`); statische Konzept-Belege: `galerie--orb-zustaende.png`, `vollbild--jarvis-*.png`.

> **Phase-5-Präzisierung (nachgezogen in Phase 7):** Eine einzige bewusste Ausnahme wurde in Phase 5 ergänzt — ein sehr zurückhaltender, umlaufender Highlight-Sweep auf der Lünetten-Skala **ausschließlich während `action-running`** (Fortschrittscharakter am Instrument, reduced-motion-sicher; siehe `docs/motion/MOTION_SYSTEM.md` §6/§10). In allen anderen Zuständen bleibt die Fassung ruhig wie hier beschrieben.

## 11. Icon- und Bildsprache

- **Eigene Icon-Sprache: ja, minimal.** Inline-SVG, Strich 1.6px, runde Kappen/Ecken (warm-technisch), NIE gefüllt; nur funktional (Mikrofon, Stopp, Schließen ×, Suche implizit, Kopieren als Wort). **Text vor Icon**, wo Platz ist („Alles kopieren", „Öffnen").
- Statussymbole = farbige Dots (7px) mit semantischem Glow, keine Icon-Metaphern.
- Dekorative Symbole existieren nicht — einzige „Zier" ist die funktionslose(?) Nein: die Lünetten-Skala gehört zum Signature-Instrument und bleibt die EINZIGE Gravur.
- Kein Emoji-/Unicode-Mix; ×/– in den Fensterpunkten sind typografisch und werden in Phase 4 durch SVG ersetzt (offener Punkt).
- **Neue Assets:** keine Bild-/Texturdateien empfohlen; Körnung und Messing sind CSS/SVG-inline. Einzige Binärassets: die 12 Font-woff2 (dokumentiert, OFL).

## 12. Responsive Modi

| | Panel (420×560) | Fokus (1000×800) | Vollbild |
|---|---|---|---|
| Rolle | intimes Taschen-Instrument, sprachzentriert | konzentrierter Arbeitsplatz | volle Atmosphäre + Werkbank |
| Sichtbar | Wortmarke, Nav, Instrument 92px, letzte Antwort (Serife), Eingabe, Mini-Aktionen (3), Status-Dots, Stopp/Mute | wie Vollbild, Instrument 132px, Begrüßung kompakt | alles, Instrument 196px, Begrüßung inszeniert |
| Entfällt | Journal, Suche, Begrüßung, Moduswechsel-Schalter, Fußzeilen-Texte (nur Dots) | nichts (kompaktere Maße) | — |
| Rollenwechsel | Antwort ersetzt Journal; Aktionen werden Puls-Zeile | Kontrollzentrum: Bucht+Heute verdichten, Profile-Zeile bricht um | Kontrollzentrum in voller Breite |

Kontrakt: identische Klassenlogik wie produktiv (`mode-fullscreen/-focus/-panel`); Panel erzwingt Gesprächsseite (wie heute). Degradationsgrenzen für Phase 4: <700px Breite (Aktionsspalte weg) und <650px Höhe (Heute-Strip weg) übernehmen die bestehenden Invarianten.

## 13. Zustände

Vollständig im Prototyp belegt: Orb ×6 · Nav/Tabs aktiv+hover+fokus · Buttons normal/hover/fokus/active/disabled/loading · Felder normal/fokus/placeholder/disabled · Schalter an/aus/disabled · Chips normal/selected/hover · Module normal/selected/hover/fokus · Dots ok/läuft/fehler/aus · Meldungen ×4 · Leerzustände (Journal, Vault) · Suche · Kopieren (hover+fokus). Screenshots: `zustand--*.png`, `galerie--*.png`.

## 14. Motion-Absicht (Ausarbeitung: Phase 5)

- **Ruhig atmen:** ausschließlich der Orb-Kern (listening langsam ~2s, thinking konzentriert ~0.9s, speaking sprechrhythmisch ~0.65s — Frequenz-Semantik der Ist-Identität übernehmen); Bernstein-„läuft"-Dots pulsieren leise.
- **Mechanisch reagieren (sofort, <150ms):** Buttons, Tabs, Schalter, Chips — Zustandswechsel fühlt sich wie Schalterklick an, keine Delays.
- **Licht folgt Status:** Orb-Übergänge blenden Kern+Glow ~0.5s; Status-Dots wechseln mit kurzem Glow-Anstieg.
- **Inszenierte Übergänge (sparsam):** Begrüßungsmoment beim Start (ein Aufglimmen des Instruments), Moduswechsel (kurzes Umsetzen), Fehler (zwei Ziegel-Pulse, dann statisch — wie heute).
- **Niemals dauerhaft animiert:** Fassung/Skala (Phase-5-Ausnahme: dezenter Lünetten-Sweep **nur** bei laufender Aktion, sonst ruhig), Körnung, Lampenlicht, Listenflächen, Banner nach Einflug.
- **`prefers-reduced-motion`:** Puls & Einflüge entfallen komplett; Zustands-FARBWECHSEL bleiben (Information), Übergänge werden Sprünge. Vollabdeckung ist Phase-5-Pflicht (heutige Lücke ist dokumentiert).

## 15. Accessibility-Regeln

1. Fokus IMMER sichtbar: 2px `brass-bright`, Offset 2 (belegt: `zustand--tastaturfokus.png`).
2. Kontraste gemäß §5-Messung; `text-muted` nie für notwendige Information; Fehler-Fließtext nicht in `error-brick` unter 12.5px/600.
3. Kopieren & Co. per Tastatur erreichbar (Fokus macht sichtbar, was Hover zeigt).
4. Semantik: echte Buttons/Tabs/Switches mit `aria-*` (Prototyp vorgelebt); Statusflächen `aria-live` (Übernahme aus Ist-System).
5. Reduced Motion = vollständig (§14); keine reine Farb-Codierung: Status-Dots stehen immer neben Klartext.
6. Deutsch in Satzschreibung; Fehlermeldungen sagen, was passiert ist und was zu tun ist (Skill-Schreibregeln).

## 16. Do / Don't

**Do:** Bernstein zeigen, wenn etwas LEBT (läuft/spricht/hört) · Auswahl mit Messing-Kante + ruhigem Halo · Verweise in Kupfer mit Unterstreichung · Instrumentenflächen einlassen, Meldungen erheben · Jarvis-Worte in Fraunces, Zahlen in Mono · Leerzustände als Einladung formulieren.
**Don't:** Bernstein als Ok-Häkchen oder Deko-Rahmen (Ok = Moos) · zweite Lünette/Skala irgendwo sonst · Versalien-Labels · Karten mit Border UND Schatten UND Glow · Serife für Bedienelemente · kalte Grautöne mischen · neue Leucht-Effekte ohne Statusbedeutung.

## 17. Implementierungshinweise für Phase 3/4

1. **Token-Mapping:** Die Phase-1-Tokens (`frontend/design-tokens.css`) behalten Namen, bekommen Zielwerte aus §5; neue Tokens: `--bg-raised/-inset`, `--copper`, `--info-copper`, `--warning-ember`, `--edge-light`, `--focus-halo`, Dot-Semantik (`--color-dot-ok` → Moos!). Mapping-Tabelle alt→neu in Phase 3 erstellen; `--color-state-warning` erhält endlich einen eigenen Wert.
2. **Fonts:** woff2 + OFL aus `prototype/assets/fonts/` nach `frontend/assets/fonts/` übernehmen; `@font-face` vor den Tokens laden; Fallback-Stacks aus §6.
3. **Strukturelle Punkte mit JS-Berührung (Phase 4, minimal-invasiv):** Sprecher-Zeile im Transcript (heute „Du:"-Präfix im Text → eigenes Element), Kopieren-Button fokusierbar machen, Statusfußzeile Mixed Case, Fenster-Buttons SVG. Keine Änderungen an WS-/Sprach-/Launcher-Logik.
4. **Invarianten:** alle aus `docs/design-baseline/BASELINE.md` §8 gelten unverändert (Klassen-Kontrakt, Escape/Stop/Mute, Strg+Enter, max 20 Einträge, Reconnect-Verhalten …).
5. **Vergleichswerkzeug:** Nach Migration `capture_baseline.py --freeze` gegen neue Referenz; Prototyp-Screenshots sind die Soll-Optik.
6. **Ziegel-Fließtext-Kontrast** (4.2:1) beachten: Fehlertexte in Pergament, nur Titel/Kanten in Ziegel — oder `error-brick` in Phase 4 auf ≥4.5 anheben und Orb-error-Paar mitziehen.
