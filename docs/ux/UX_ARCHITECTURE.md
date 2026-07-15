# Jarvis UX-Architektur (Phase 3, 2026-07-11)

Verbindliche Informationsarchitektur auf Basis von `docs/design-direction/DESIGN.md` (Phase 2). Erarbeitet mit Skill `ui-ux-pro-max` (Guideline-IDs in Klammern). Geltungsbereich: Struktur & Bedienlogik — visuelle Werte bleiben Sache von DESIGN.md.

## 1. Produktprioritäten (verbindliche Entscheidungsordnung)

1. Aktuelle Jarvis-Aktivität verstehen → 2. Laufendes jederzeit stoppen → 3. Sprechen/Text senden → 4. Antwort & Aktionsresultat erfassen → 5. Navigation Jarvis⇄Kontrollzentrum → 6. Apps/Profile/Monitore verwalten → 7. Einstellungen & Musik → 8. Historie/Diagnose.
Dekoration darf nie eine höhere Priorität behindern (DESIGN-Prinzip 1/6).

## 2. Bestandsaufnahme der Ist-Oberfläche (Teil 1)

| Element | Zweck / Nutzeraufgabe | Position heute | Sichtbarkeit P/F/V | Interaktion | Prio | Abhängigkeiten | Probleme heute | Geplante Rolle |
|---|---|---|---|---|---|---|---|---|
| Orb | Zustand verkörpern | zentriert | ✓/✓/✓ | Klick=Zuhören an/aus | 1 | WS-Status | Klick-Funktion unentdeckbar; Zustand nur Farbe+Puls | Signature-Instrument; Klick bleibt, zusätzlich beschriftete Kontrollen |
| Statuszeile (#status) | Zustandswort | unter Orb | ✓/✓/✓ | — | 1 | setOrbState | Versal-Flüstertext, teils leer | Klartext-Zustand aus STATE_MODEL, immer gefüllt |
| Status-Center (Dots) | Server/Mikro/Zustand/Fehler | fixed unten links | ✓/✓/✓ | Hover | 1 | WS/Mic | Dots fast unsichtbar (opacity .45), Farbe allein, Panel nur Dots | Gerätefußleiste mit Dot+Klartext (`color-not-only`) |
| Stop/Mute | Abbrechen/Stummschalten | fixed unten rechts | ✓/✓/✓ | Klick, Esc, Sprache | 2 | WS | 34px, opacity .35 → übersehbar | ≥44px, volle Sichtbarkeit, in Fußleiste integriert (`touch-target-size`) |
| Transcript | Verlauf lesen/kopieren | Hauptspalte | ✗/✓/✓ | Scroll, Hover-Copy | 4 | WS | Copy nur Hover (`hover-vs-tap`), kein „neue Nachricht"-Signal beim Hochscrollen | Journal-Spez §6; Copy auch fokussierbar |
| Suche + Alles kopieren | Verlauf filtern | über Transcript | ✗/✓/✓ | Tippen | 8 | Transcript | Trefferzahl unsichtbar | Trefferzahl + aria-live |
| Texteingabe | Fallback senden | unter Transcript | ✓/✓/✓ | Strg+Enter | 3 | WS | Hint nur Platzhalter; opacity .35 wirkt disabled | sichtbarer Hint, klare Affordanz |
| Panel-Antwort | letzte Antwort kompakt | Panel | ✓/—/— | Scroll | 4 | Transcript | ok | bleibt (Serifen-Stimme) |
| Aktionshistorie | Aktionen verfolgen | Fokus-Spalte/KZ/Panel-mini | mini/✓/✓(KZ) | Scroll | 8 (laufend: 1) | WS action | **3-fach dupliziert**; in Fokus konkurriert sie mit Gespräch | Dedupe §5: laufende Aktion → Statuszeile; volle Liste NUR KZ; Panel-mini bleibt |
| Seiten-Nav (Jarvis/KZ) | Bereichswechsel | Titelleiste links | ✓/✓/✓ | Klick | 5 | rootClass | unauffällig, aktiver Tab nur Farbton | Text-Tabs mit Unterstreichung (`nav-state-active`) |
| Modus-Schalter (Vollbild/Mitte/Klein) | Fenstergröße | Titelleiste rechts | ✓/✓/✓ | Klick | 5 | pywebview | Benennung „Mitte/Klein" ≠ Doku „Fokus/Panel" | Benennung bleibt nutzerseitig (Vollbild/Mitte/Klein) — Doku-Mapping festgeschrieben; Schalter als Geräteschalter |
| KZ-Subnav (Übersicht/Musik/Einstellungen) | Unterbereich | KZ oben | —/✓/✓ | Klick | 5 | controlView | DOM-Reihenfolge ≠ definierter Reihenfolge | Reihenfolge Übersicht·Einstellungen·Musik? → bleibt Übersicht·Musik·Einstellungen wie DOM (geringste Umbaukosten), Tab-Reihenfolge = visuell |
| Profile | Arbeitsmodi wechseln/verwalten | KZ-Kopf | —/✓/✓ | Klick | 6 | /launcher | Löschen = 2-Klick ohne erklärende Bestätigung | Tabs + Aktionen; Confirm-Zeile mit Klartext (`confirmation-dialogs`) |
| Monitor-Map | Apps platzieren | KZ Mitte | —/✓/✓ | Click-to-Assign, DnD | 6 | /launcher/monitors | **nur visuell bedienbar**; Zonen unbeschriftet für SR | Map bleibt + **Select-Alternative je App** (`keyboard-shortcuts`, `gesture-alternative`) |
| Heute (Aufgaben/Inbox/Notizen) | Tageskontext | KZ unter Map | —/✓/✓ | lesen | 8 | /dashboard | leere Zustände ohne Handlung | Leerzustand = Einladung (`empty-states`) |
| Apps-Module | öffnen/Autostart/Platz | KZ rechts | —/✓/✓ | Klick/Toggle | 6 | /launcher | Platzierung nur als Text, Änderung nur via Map | + Positions-Selects (progressive disclosure bei Auswahl) |
| Systemstatus | Dienste prüfen | KZ rechts unten | —/✓/✓ | lesen | 8 | /health | Farbe allein | Dot+Klartext bleibt (ist schon Text) ✓ |
| Einstellungen | konfigurieren | KZ-Subview | —/✓/✓ | Formular | 7 | /settings | eine lange Liste ohne Gruppen; Verwerfen ohne Rückfrage | Gruppen §8; ungespeichert-Zustand + Confirm |
| Musik | Startmusik wählen | KZ-Subview | —/✓/✓ | Klick | 7 | /music | ok; Status doppelt (Jarvis-Seite + KZ) | Doppelung ok (Status ≠ Verwaltung), dokumentiert |
| Fehlerbanner | Fehler verstehen | oben rechts | ✓/✓/✓ | Schließen | 1 | WS error | z. T. Fachsprache | Klartext + Recovery (`error-clarity`) |
| Boot-Fallback | Crash sichtbar | Vollfläche | ✓/✓/✓ | — | 1 | JS-Fehler | ok | bleibt |

**Befunde (Teil 1, konsolidiert):** Duplikate: Aktionshistorie ×3 · Musik-Status ×2 (akzeptiert, unterschiedliche Aufgabe). Konkurrenz: Aktionsspalte vs. Gespräch im Fokus. Versteckt: Copy (nur Hover), Orb-Klick, PTT (nur Vorwissen), Escape=Stop (nirgends erklärt). Unnötig permanent: vollständige Historie im Fokus. Unklare Ebenen: Modus-Schalter wirkt wie Navigation. Ohne Hierarchie: Status-Center-Fehlertext vs. Banner. Überladen: KZ-Übersicht (6 Informationsblöcke gleichzeitig). Zu reduziert: Panel-Statuszeile (`font-size:0`-Trick). Benennung inkonsistent: „Mitte/Klein" (UI) vs. „Fokus/Panel" (Doku) — festgelegt: UI-Namen bleiben, Doku führt beide. Nur-Vorwissen: Sprachbefehle („Stopp", „Mikro stumm"), Strg+Enter.

## 3. Seiten- und Navigationsebenen (Teil 3)

**Ebene 1:** Jarvis (Gespräch) · Kontrollzentrum. **Ebene 2 (nur KZ):** Übersicht · Musik · Einstellungen. **Diese Struktur genügt** — Nachweis: alle 33 Flows (USER_FLOWS.md) erreichen ihr Ziel in ≤2 Navigationsschritten; eine dritte Ebene (z. B. Settings-Unterseiten) würde Flows 25–29 verlängern, ohne Übersicht zu gewinnen. Keine neue Ebene.

- **Permanent sichtbar:** Ebene-1-Nav + Modus-Schalter (Titelleiste) in allen Modi (`persistent-nav`); Ebene-2-Subnav nur im KZ.
- **Reduktion je Modus:** Panel behält beide Ebene-1-Tabs (kompakt); Subnav existiert im Panel nicht (KZ nicht darstellbar).
- **Aktiver Bereich:** Messing-Unterstreichung + `aria-selected` (`nav-state-active`); Fensterknopf zusätzlich `aria-pressed`.
- **Zurück:** Ebene 1 ist flach — „zurück" = anderer Tab; im KZ führt Abbrechen (Settings/Musik) zur Übersicht zurück (bestehendes Verhalten, bleibt). Escape navigiert NICHT (Escape = Stop/Auswahl abbrechen — Konfliktregel in STATE_MODEL §Escape).
- **Fokus nach Wechsel:** auf die Bereichsüberschrift (`h1/h2[tabindex="-1"]`) des Ziels (`focus-on-route-change`).
- **Bereichserhalt:** appPage & controlView bleiben beim Moduswechsel erhalten; Ausnahme (bestehende Invariante): Panel erzwingt Jarvis-Seite; KZ-Aufruf aus Panel wechselt zu „Mitte". Beim Rückweg Panel→ bleibt Jarvis. Kein weiterer Zustand wird zurückgesetzt (`state-preservation`; Suchtext, Scroll, Auswahl bleiben).
- **Lazy Load:** Dashboard-/Launcher-/Musik-Daten laden erst beim ersten KZ-Öffnen (bestehend: `shouldLoadControlData`) — bleibt; Ladezustände gemäß COMPONENT_BEHAVIOR.
- **Sackgassen:** keine — jede Ansicht behält Titelleisten-Nav; Modals existieren nicht (Bestätigungen sind Inline-Zeilen, `modal-vs-navigation`).

## 4. Hauptansicht Jarvis (Teil 5) — Hierarchie

Reihenfolge (vertikal, Vollbild): 1. Begrüßung (nur bis erste Interaktion) → 2. Instrument (Orb in Lünette) → 3. Statuszeile (Zustandswort + laufende Aktion) → 4. Journal (Gespräch) → 5. Eingabezeile → 6. Gerätefußleiste (Verbindung/Mikro-Klartext + Stop/Mute ≥44px).

Prüffragen beantwortet: **Orb-Platz** — Vollbild 196px zentriert ist Inszenierung (Prio 1: Zustand); im Fokus 132px, Panel 92px — nie auf Kosten des Journals (Journal bekommt `flex:1`). **Zustand ohne Orb verständlich?** Ja: Statuszeile führt dasselbe Zustandswort (STATE_MODEL Spalte „Bezeichnung") + Fußleisten-Klartext. **Stop jederzeit?** Fußleiste fixed in allen Modi, zusätzlich Esc + Sprachbefehl; in `speaking/action-running` wird Stop zur visuell primären Aktion (Bernstein-Kontur). **Texteingabe gleichwertig?** Sichtbarer Hint „Strg+Enter sendet" + volle Opazität im Leerlauf; Placeholder ist nicht das Label (`input-labels`: visuell verborgenes Label). **Status/Fehler verständlich?** Klartext-Vokabular STATE_MODEL; Banner nach `error-clarity` (Ursache + Abhilfe). **Lesebreite?** Journal max 660px ≈ 66–75 Zeichen Serife (`line-length-control`). **Einhand/Tastatur?** Alle Kernaktionen unten gebündelt (Eingabe→Fußleiste), Tastatur: Tab-Kette + Esc + Strg+Enter + Leertaste (PTT) — dokumentiert in ACCESSIBILITY_SPEC.

## 5. Aktions-Kommunikation (Dedupe-Entscheidung)

- **Statuszeile** zeigt in `action-running` die laufende Aktion als Klartext: „Recherchiert: Elektroautos Reichweite … (Stopp mit Esc)".
- **Panel:** Mini-Historie (letzte 3) bleibt — dort ersetzt sie das Journal.
- **Fokus/Vollbild Jarvis-Seite:** KEINE Aktionsspalte mehr; Historie lebt ausschließlich im KZ (rechte Spalte).
- Begründung: Prio 1/4 > 8; das Gespräch gewinnt die Fokus-Fläche zurück; Diagnose bleibt einen Nav-Klick entfernt (`content-priority`).

## 6. Transcript/Journal (Teil 6)

- **Lesebreite** max 660px; **Rhythmus:** Nutzer-Eintrag 16px Abstand, Jarvis-Eintrag 24px danach (Absatzgefühl); Marginalspalte 52px Mono-Zeit.
- **Unterscheidung:** Sprecherzeile („Du"/„Jarvis") + Stimme (Sans/Serife) — keine Bubbles (DESIGN §9).
- **Zeitstempel** Mono, `text-muted`, nicht fokussierbar. **Quellen:** Kupfer-Links, `target`-los (öffnen via Browser-Aktion), Unterstreichung permanent. **Aktionshinweise:** Inline-Zeile unterhalb der Jarvis-Antwort („→ Notiz in Inbox abgelegt", Mono, mit Status-Dot).
- **Laufende Antwort:** Eintrag erscheint mit Zustandswort „schreibt …" (Drei-Punkt still, kein Spinner); **unterbrochene Antwort:** Suffix „— gestoppt" in `text-muted` + Aktion „Weiterlesen? Erneut fragen" nicht nötig (Antwort bleibt stehen).
- **Fehler im Gespräch:** System-Eintrag mit Ziegel-Sprecher „System" statt Banner-Doppelung, wenn der Fehler die Antwort betrifft (TTS-Fallback: Banner + Text bleibt).
- **Suche:** filtert live; Trefferzeile „3 von 20 Einträgen" (`aria-live=polite`); Fokus bleibt im Feld; Treffer-Highlight Pergament-auf-Selection-bg; leerer Treffer: „Kein Eintrag enthält ‚xyz'."
- **Kopieren:** je Eintrag Button (sichtbar bei Hover UND `:focus-visible`); Feedback „Kopiert" 2 s im Button (`success-feedback`), kein Toast. „Alles kopieren" nutzt Filterzustand.
- **Leerzustand:** „Noch kein Gespräch. Sag ‚Jarvis' — oder schreib unten die erste Nachricht."
- **Scroll:** Auto-Scroll nur, wenn Nutzer am Ende steht; sonst Pill „↓ Neue Nachricht" (Klick springt ans Ende, Pill verschwindet); nach Suche kein Scroll-Sprung. Max 20 Einträge (Invariante).
- **Lange Inhalte/Wörter:** `overflow-wrap:break-word` (Kompositum-Beleg Phase 2); Links brechen; kein horizontales Scrollen.

## 7. Kontrollzentrum (Teil 7) — progressive Offenlegung

**Immer sichtbar:** Profilzeile (aktives Profil zuerst), Monitor-Bucht (Kern der Werkbank), Apps-Spalte, Systemzeile (kompakt), Heute-Strip. **Bei Auswahl:** Positions-Selects im App-Modul (erst wenn Modul ausgewählt/fokussiert = progressive disclosure), Zonen-Hervorhebung. **In Details verschoben:** vollständige Aktionshistorie (eigener Block, scrollt), Monitor-Pixelmaße (Mono-Nebeninfo). **Nur bei Fehlern prominent:** Vault-/Dienststörung als Banner + Ziegel-Dot im System. **In Einstellungen statt Übersicht:** Apps-Registry-Bearbeitung (Name=Befehl), Ordnerpfade, Mikrofonmodus.

Spaltenlogik (Fokus/Vollbild): links Gespräch (Kontinuität), Mitte Werkbank (Profile→Bucht→Heute), rechts Module (Apps→Aktionen→System). Reihenfolge = Prioritätenfolge 6→8.

### Apps (Zustände)
Primäraktion „Öffnen" (ein Primary je Modul, `primary-action`); Autostart-Schalter; Position als Klartext + (bei Auswahl) Selects; Auswahl = Messing-Kante; Laden = Button-Spinner + disabled (`loading-buttons`); Erfolg = kurzes „Geöffnet ✓" im Button (2 s); Fehler = Ziegel-Kante + Meldungszeile mit Abhilfe („Pfad prüfen → Einstellungen") (`error-recovery`); unbekannte/nicht verfügbare App = Modul gedimmt + Badge „nicht gefunden", Öffnen disabled mit Erklärung (`empty-nav-state`-Analogie).

### Profile
Aktiv = Tab mit Unterstreichung + „aktiv"-SR-Text; Wechsel = Klick (sofort, kein Confirm); Neu/Duplizieren = Inline-Eingabe (Enter=an legen, Esc=abbrechen); Umbenennen = gleiche Inline-Eingabe vorbefüllt; **Löschen** = zweistufig: Klick „Löschen" → Tab wird Ziegel-Kontur „Nochmal klicken zum Löschen" (`aria-live=assertive` Hinweis) + jede andere Aktion bricht ab (`confirmation-dialogs`, destruktiv separiert `destructive-nav-separation`); **letztes Profil:** Löschen disabled mit Grund („Mindestens ein Profil bleibt bestehen").

### Monitor-Map
Ablauf A (visuell): App-Modul wählen → Bucht hebt Zonen an (`assigning`) → Zone klicken → „Speichert …" → Zone pulst + Chip erscheint (Erfolg) / Ziegel-Meldung (Fehler). Ablauf B (nicht-visuell, **gleichwertig**): im ausgewählten App-Modul Selects „Monitor" (links/rechts/primär) + „Zone" (9 Zonen + Vollbild) → „Position speichern" → gleiche Persistenz. Vorschau: Ghost (visuell) bzw. Selects zeigen aktuellen Wert. Nicht zuweisbarer Monitor: gedimmt + `aria-disabled` + Grund im Label. Tastatur (Map): Zonen sind Buttons im Tab-Fluss, Enter/Space weist zu, Esc bricht Auswahl ab. Screenreader: Zonen-`aria-label` „Monitor links, Zone Mitte — belegt: Obsidian"; Live-Status „Obsidian → Monitor links, rechte Hälfte gespeichert". **Sichtbares Feedback:** Die Bucht führt eine eigene Statuszeile (App → Ziel gespeichert / „Erst eine App auswählen …"); der Chip der App wandert sichtbar in die neue Zone (Reviewer-Befund 7). **Not-Halt-Regel:** Der Stop-BUTTON stoppt immer direkt; nur die Esc-TASTE durchläuft die Abbruch-Kaskade (Reviewer-Befund 2, STATE_MODEL §Escape).

## 8. Einstellungen & Musik (Teil 8)

**Gruppen:** 1 Persönlichkeit (Name, Anrede, Tätigkeit) · 2 Standort (Stadt) · 3 Stimme (ElevenLabs-Voice-ID) · 4 Speicher & Obsidian (Vault, Inbox) · 5 Musik (Ordner) · 6 Verhalten (Mikrofonmodus) · 7 Apps & Workspace (Registry-Textarea). Geschützt (nur config.json, Read-only-Erklärung, `read-only-distinction`): API-Schlüssel, Origin/Token-Sicherheit.
Labels sichtbar über dem Feld; Hilfetexte persistent unter komplexen Feldern (`input-helper-text`); Validierung on-blur (`inline-validation`), Fehler unter dem Feld (`error-placement`) + `aria-live`; ungespeicherte Änderungen: Hinweispill „Nicht gespeicherte Änderungen" neben Speichern + Verwerfen-Rückfrage (`sheet-dismiss-confirm`); Speichern = Diff-POST (bestehend) mit Button-Spinner → Erfolg „Gespeichert ✓" (Moos) + Rückkehr zur Übersicht; Fehler: Zusammenfassung oben + Fokus aufs erste Fehlerfeld (`error-summary`, `focus-management`).

**Musik:** aktueller Titel oben („Spielt beim nächsten Start: …" oder „Keine Musik ausgewählt"); Dateiliste (Name + „ausgewählt"-Dot); Auswahl = sofortiges Speichern mit Zeilen-Feedback; Entfernen = „Keine Musik"-Zeile; fehlender Ordner: Meldung + Link „Ordner in Einstellungen festlegen"; leerer Ordner: „Keine MP3-Dateien in <Ordner>"; nicht verfügbare Datei (gelöscht): Eintrag gedimmt + Hinweis. Musik bleibt sekundär (eigener Subview, kein Platz auf der Jarvis-Seite außer Status).
