# Jarvis User Flows (Phase 3)

33 Kernabläufe. Schema je Flow: **A**usgangszustand → **T**rigger → **S**chritte → **F**eedback → **✓** Erfolg → **✗** Fehler → **⎋** Abbruch → **↩** Rückkehr → **⌨/🎤** Tastatur/Sprache. `▲` = Vereinfachung gegenüber heute. Zustände: siehe STATE_MODEL.md.

## Kernabläufe

**1 · Starten & Zustand verstehen** — A: App-Start (Launcher/Doppelklatschen). T: Fenster erscheint. S: connecting → Begrüßungs-Briefing (auto) → idle/listening. F: Orb + Statuszeile („Verbinde …" → „Hört zu"), Fußleiste „Server verbunden · Mikrofon bereit". ✓ Zustandswort sichtbar <1 s nach Verbindung. ✗ disconnected: „Getrennt — verbinde neu (Versuch 2)" + Banner ab 3. Versuch. ⎋ —. ↩ —. ⌨ keiner nötig. ▲ Statuszeile ersetzt heutiges Leer-/Flüsterwort.

**2 · Spracheingabe beginnen** — A: idle/listening. T: sprechen (always-listen) / Leertaste halten (PTT) / Orb-Klick. S: Erkennung läuft. F: Orb listening + „Hört zu". ✓ Zustand listening. ✗ Mikrofon verweigert → error + Banner „Mikrofon nicht erreichbar — Berechtigung prüfen". ⎋ Leertaste loslassen / Orb-Klick. ↩ idle. ⌨ Space (PTT). 🎤 immer.

**3 · Eingabe erkennen lassen** — A: listening. T: Satzende. S: Transkript → processing. F: „Verarbeite …" + Nutzertext erscheint im Journal. ✓ Eintrag „Du: …". ✗ nichts erkannt → zurück zu listening (kein Fehlerbanner, stilles Retry — bestehend). ⎋ Esc (verwirft nichts Gesendetes). ⌨ —.

**4 · Denkzustand verfolgen** — A: processing/thinking. F: Orb thinking + „Denkt nach"; bei Aktion: action-running + „Recherchiert: … (Esc stoppt)". ✓ Antwort kommt. ✗ LLM-Fehler → error-Banner mit Abhilfe + Orb-Flash. ⎋ Esc = Stop-Anforderung (stopping). ▲ laufende Aktion steht JETZT in der Statuszeile statt nur in der Historien-Spalte.

**5 · Antwort lesen & hören** — A: thinking→speaking. F: Journal-Eintrag (Serife) + TTS; Orb speaking. ✓ Audio endet → listening/idle. ✗ TTS-Fehler → degraded: Text bleibt, Banner „Sprachausgabe fehlgeschlagen — Antwort steht im Gespräch". ⎋ Flow 6. ↩ —.

**6 · Sprachausgabe stoppen** — A: speaking. T: Stop-Button / Esc / „Stopp". S: stopping → Audio bricht ab. F: „Gestoppt" 1 s → idle; Journal markiert „— gestoppt". ✓ Ruhe <300 ms. ✗ (kein Serverkontakt) lokal stoppt trotzdem (bestehende Architektur). ⌨ Esc. 🎤 „Stopp". ▲ Stop ≥44px sichtbar statt 34px/35 %.

**7 · Laufende Aktion abbrechen** — wie 6 aus action-running; F: Statuszeile „Aktion abgebrochen"; Historie (KZ) markiert Eintrag „abgebrochen". ✓ Zustand idle ≤1 s.

**8 · Mute an/aus** — A: beliebig außer disconnected. T: Mute-Button / „Mikro stumm"/„Mikro an". S: muted ⇄ vorheriger Hörzustand. F: Orb muted (Ziegelring), Fußleiste „Mikrofon stumm", Button gefüllt. ✓ kein Erkennen mehr. Sonderfall: PTT-Modus — Mute blockiert auch Space (Erklär-Tooltip). ⌨ Tab→Button (kein Global-Shortcut, Konfliktvermeidung). 🎤 nur AUS→AN nicht möglich wenn stumm → UI-Hinweis „stumm — per Klick reaktivieren".

**9 · Text senden** — A: beliebig verbunden. T: Feld fokussieren, tippen, Strg+Enter. F: sofort Journal-Eintrag + processing. ✓ wie Sprache. ✗ leer → nichts (kein Fehler). ⎋ Feld leeren/Esc (Feld verlassen, kein Stop wenn Feld gefüllt & fokussiert — Escape-Regel: 1. Auswahl/Feld-Abbruch, 2. Stop). ⌨ Strg+Enter. ▲ Hint dauerhaft sichtbar.

**10 · Nach Fehler weiterarbeiten** — A: error/degraded. T: Banner lesen. S: Abhilfe folgen (z. B. erneut fragen); Banner schließen (×). F: Orb kehrt nach 2 Fehlpulsen zu statisch zurück; nächste Eingabe setzt normalen Zustand. ✓ Folgeinteraktion funktioniert ohne Neustart. ✗ Wiederholung → Banner bleibt (persistent bei llm/ws). ↩ idle.

## Transcript

**11 · Nachricht finden** — Suche fokussieren (Klick/Tab) → tippen → Liveliste + „n von 20". ⎋ Feld leeren = ×-Button/Backspace. ⌨ vollständig. ▲ Trefferzahl neu.
**12 · Einzelne kopieren** — Eintrag hovern ODER per Tab zum Copy-Button → Enter → „Kopiert" 2 s. ▲ tastaturzugänglich (heute hover-only).
**13 · Alles kopieren** — Button im Journalkopf → kopiert Filterstand → „Kopiert (n Einträge)".
**14 · Lange Antwort lesen** — Journal scrollt intern; Auto-Scroll pausiert beim Hochscrollen; Pill „↓ Neue Nachricht" bei Neuem. ▲ Pill neu.
**15 · Quellen/Resultate erkennen** — Kupfer-Links unter Antwort; Aktionsresultat-Zeile „→ Notiz abgelegt ✓" mit Dot. Enter öffnet Link (Browser). ▲ Resultat-Zeile im Gespräch statt nur Historien-Spalte.

## Kontrollzentrum

**16 · KZ öffnen** — Nav-Tab „Kontrollzentrum" (aus Panel: wechselt zugleich auf „Mitte" — Tooltip kündigt an). F: Fokus auf KZ-Überschrift; Daten laden (Skeleton-Zeilen ≤1 s). ↩ Tab „Gespräch". ⌨ Tab→Nav→Enter.
**17 · App starten** — Übersicht → App-Modul „Öffnen" → Button-Spinner → „Geöffnet ✓" / Fehlerzeile mit Abhilfe. Doppelklick-Schutz: disabled während busy.
**18 · Autostart toggeln** — Schalter im Modul → sofortiger POST → Knopf gleitet + „Autostart an/aus" (SR-announce). ✗ Netzfehler: Knopf springt zurück + Meldungszeile.
**19 · App→Zone zuweisen** — Weg A: Modul klicken (ausgewählt) → Zone in Bucht klicken → „Speichert…" → Puls+Chip. Weg B (▲ neu, nicht-visuell): Modul fokussieren → Selects Monitor+Zone → „Position speichern". ⎋ Esc bricht Auswahl ab. ✗ „Speichern fehlgeschlagen — erneut versuchen".
**20 · Profil neu** — „Neu" → Inline-Feld → Name → Enter. ✗ leer/doppelt: Fehler unter Feld. ⎋ Esc.
**21 · Profil wechseln** — Tab klicken → aktiv (sofort); Chips/Toggles laden nach. F: „Profil ‚Research' aktiv" (polite).
**22 · Umbenennen/Löschen** — Umbenennen: Inline vorbefüllt. Löschen: 2-Klick-Confirm (Ziegel), andere Aktion bricht ab; letztes Profil: disabled + Grund. ▲ Confirm-Klartext statt kommentarlosem Rot.
**23 · Systemstatus verstehen** — KZ rechts unten: Dot+Klartext je Dienst; degraded zusätzlich als Banner. Kein Interaktionszwang.
**24 · Historie prüfen** — KZ rechts Mitte: Liste (Dot, Zeit Mono, Label, Detail); läuft = Bernstein-Puls. ▲ nur noch hier (Dedupe).

## Konfiguration

**25 · Einstellungen ändern** — Subnav „Einstellungen" → Gruppe → Feld (on-blur-Validierung). Pill „Nicht gespeicherte Änderungen" erscheint.
**26 · Speichern/Verwerfen** — Speichern: Diff-POST, Spinner, „Gespeichert ✓", zurück zur Übersicht, Fokus auf Übersichts-H2. Verwerfen bei Änderungen: Rückfrage-Zeile „Änderungen verwerfen? [Verwerfen] [Weiter bearbeiten]". ✗ Serverfehler: Zusammenfassung + Fokus erstes Fehlerfeld.
**27 · Musik wählen** — Subnav „Musik" → Datei klicken → Dot + „Spielt beim nächsten Start". Sofort persistiert.
**28 · Musik entfernen** — Zeile „Keine Musik" → Status leert sich; Jarvis-Seiten-Status verschwindet (`:empty`).
**29 · Zwischen Subviews wechseln** — Subnav-Tabs; ungespeicherte Settings → Flow-26-Rückfrage; Fokus je auf Bereichs-H2.

## Fenster & Navigation

**30 · Jarvis⇄KZ** — Nav-Tabs; Zustand des jeweils anderen Bereichs bleibt erhalten; Fokus-Regel §3.
**31 · Modus wechseln** — Titelleisten-Schalter Vollbild/Mitte/Klein; Inhalt folgt Sichtbarkeitsmatrix; kein Datenverlust; Panel⇒KZ-Kombination unmöglich (erzwungener Jarvis-Bereich, bestehende Invariante).
**32 · Panel→KZ sicher** — Panel: Tab „Kontrollzentrum" → Fenster wird „Mitte" + KZ; Rückweg: „Klein" → zurück ins Panel (Jarvis). ▲ Tooltip „Öffnet das Kontrollzentrum in mittlerer Größe" macht den Moduswechsel erwartbar.
**33 · Komplett per Tastatur** — Reihenfolge: Skip-Link → Nav → Modus → (Bereichsinhalt) → Eingabe → Fußleiste (Stop→Mute). Alle Aktionen Enter/Space; Esc-Kaskade: 1) Inline-Edit/Auswahl abbrechen 2) sonst Stop. PTT: Space nur außerhalb von Feldern. Vollständige Karte: ACCESSIBILITY_SPEC §Fokusreihenfolge.

## Unnötige Schritte / Vereinfachungen (Sammelliste)

| Heute | Problem | Vereinfachung (Phase 4) |
|---|---|---|
| Stop 34px/35 % Opacity | übersehbar in Stresssituation | ≥44px, volle Präsenz, Zustimmung „primär bei speaking" |
| Copy nur bei Hover | Tastatur/Touch ausgeschlossen | fokussierbar + `:focus-visible` zeigt Button |
| Aktion nur in Spalte | Blickwechsel weg vom Gespräch | Klartext in Statuszeile (laufend), Spalte nur KZ |
| Zuweisung nur Map | rein visuell | Selects je App (gleichwertig) |
| Löschen-2-Klick unkommentiert | Bedeutung unklar | Confirm-Text + assertive-Announce |
| Settings ungruppiert | Suchaufwand | 7 Gruppen + Pflicht-/Hilfetexte |
| „Getrennt" nur Dot | Farbe allein | Klartext + Versuchszähler |
| Sprachbefehle unsichtbar | nur Vorwissen | Hint-Zeile in Fußleiste (dezent, Mono) „Esc = Stopp · ‚Stopp' sagen" |
