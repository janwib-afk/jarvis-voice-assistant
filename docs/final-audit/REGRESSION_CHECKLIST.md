# Jarvis Frontend — Regressions-Checkliste

Kurz und wiederverwendbar. Vor jeder Frontend-Änderung durchgehen (Harness `docs/design-baseline/tools/baseline_server.py --port 8341`, **nie gegen den echten Server** — Auto-Begrüßung kostet API-Calls).

## Fenstermodi (3)
- [ ] **Vollbild** — Orb voll sichtbar, Journal nutzt Höhe, kein Overflow.
- [ ] **Mitte** — Orb **nicht** von der Titelleiste beschnitten (`@media max-height:860px`), Eingabe frei.
- [ ] **Klein/Panel** — Wortmarke, Nav, Orb, Antwort, Eingabe, Mini-Aktionen, Dots, Stop/Mute sichtbar.

## Jarvis-Zustände
- [ ] idle / listening / thinking / speaking / muted / error / disconnected — je Wort + Farbe + Dot + Orb-Licht (nie Farbe allein).
- [ ] action-running — Lünetten-Sweep nur währenddessen; endet stabil.

## Steuerung
- [ ] **Stop** bricht Wiedergabe **und** laufende Aktion ab (Button + Esc).
- [ ] **Mute/Unmute** — `aria-pressed` korrekt, Orb gedämpft (kein Fehlerzustand).
- [ ] Textanfrage senden (Strg+Enter), Antwort erscheint.
- [ ] Transcript durchsuchen (Trefferzähler), Nachricht + „Alles kopieren".

## Kontrollzentrum
- [ ] Öffnen (Nav), Übersicht/Musik/Einstellungen (Sub-Tabs).
- [ ] Apps: Öffnen, Autostart-Toggle.
- [ ] Profile: wechseln, verwalten (Neu/Umbenennen/Löschen mit Confirm).
- [ ] **Monitor-Map:** Klick-zu-Zuweisen (Weg A) **und** Selects „Monitor/Zone/Position speichern" (Weg B, per Tastatur via `:focus-within` erreichbar).

## Formulare
- [ ] Einstellungen: bearbeiten → dirty-Pill → Speichern („Gespeichert ✓").
- [ ] Abbrechen mit Änderungen → Verwerfen-Rückfrage.
- [ ] **API-Keys erscheinen nie** im Form/DOM; GET /settings ohne `*_api_key`.
- [ ] `autocomplete="off"` + `spellcheck="false"` am Settings-Form.
- [ ] Musik: auswählen / entfernen / neu laden.

## Tastatur & Fokus
- [ ] Tab-Reihenfolge = visuelle Ordnung; keine Falle.
- [ ] **Sichtbarer Fokus** (Messing-Ring) auf allen Buttons; Inputs per Rahmen/Halo.
- [ ] Escape: Stop/Kaskade, Confirm/Sheet schließen, Fokus sinnvoll.
- [ ] Skip-Link → Eingabe.
- [ ] Icon-Buttons (min/close/Banner-Schließer) mit `aria-label`.

## Zoom & Responsive
- [ ] Zoom 125/150/200 % — kein H-Scroll; Stop/Mute + Eingabe erreichbar.
- [ ] Overflow 0 bei 1920/1366/1024/768/430.
- [ ] Lange DE-Wörter / lange App-/Profilnamen / langes Transcript brechen sauber.

## Motion & Reduced Motion
- [ ] Übergänge <260ms, unterbrechbar; Stop sofort; kein Endlos-Warnblinken.
- [ ] `prefers-reduced-motion`: 0 Loop-Animationen, Zustands-Glow statisch, alle Funktionen identisch.
- [ ] Delight: Orb-Erwachen (erster Connect), Chip-Landung (Zuweisung) — reduced-safe.

## Theming
- [ ] `color-scheme: dark` gesetzt (native Selects/Scrollbars dunkel).
- [ ] Kontraste ≥ 4.5:1 für Text.

## Browserkonsole & Netz
- [ ] **0 Konsolenfehler**, 0 unhandled rejections.
- [ ] 0 404, **nur** `localhost:8341` (keine externen Hosts/CDNs/Fonts).

## Tests
- [ ] `python -m unittest discover -s tests` → OK, **0 skipped**.
- [ ] `python scripts/smoke-test.py` → Exit 0.
- [ ] `verify_phase4.py` 27/27 · `verify_phase5.py` 13/13.
