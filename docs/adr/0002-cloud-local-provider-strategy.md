# ADR 0002 – Cloud-/Local-Provider-Strategie

- **Status:** akzeptiert (Phase 0, 2026-07-13) — bestätigt im Entscheidungsgate.
- **Betrifft:** [SYSTEM_CHARTER.md](../system/SYSTEM_CHARTER.md) §6, [QUALITY_BASELINE.md](../quality/QUALITY_BASELINE.md) §6.

## Kontext

Jarvis nutzt heute Cloud-Provider für Denken/Vision (Anthropic), Sprachausgabe
(ElevenLabs) und die browserbasierte Spracherkennung (Web Speech API); Browsersteuerung,
Gedächtnis/Vault und Windows-Steuerung sind lokal. Der Masterplan verlangt eine klare,
dokumentierte Ausgangsstrategie und die Zusicherung, dass automatisierte Tests keine
Kosten verursachen.

## Entscheidung

- Der **Ist-Split bleibt** vorerst bestehen (siehe Tabelle in SYSTEM_CHARTER §6).
- Provider werden mittelfristig **hinter Adapter** austauschbar gemacht (Umsetzung in
  einer Kernphase, nicht in Phase 0).
- **Keine erzwungene lokale Modellruntime** in Phase 0; lokale Alternativen (STT/LLM/TTS)
  erst nach **messbarem Bedarf**.
- **Jede Cloud-Übertragung** trägt bekannte **Quelle**, **Datenklasse** und sichtbaren
  **Zweck**.
- **Standardtests rufen keine echten Provider auf** (gemockt/gestubbt; Dummy-Keys in der
  Test-Fixture; `JARVIS_SKIP_STARTUP_REFRESH`).

## Alternativen

1. **Sofort lokale Modelle (Whisper/lokales LLM/lokale TTS).** Höhere Datenhoheit, aber
   erheblicher Aufwand, schwächere Qualität, kein aktueller messbarer Bedarf. Verworfen
   für Phase 0.
2. **Provider hart verdrahtet lassen ohne Adapterziel.** Verhindert späteren Austausch
   und lokale Optionen. Verworfen.
3. **Cloud-only ohne Datenklassen-Regel.** Widerspricht dem Vertrauensprinzip. Verworfen.

## Konsequenzen

- Der spätere Adapter-Layer (Phase 4/9) bekommt einen klaren Auftrag; heutige Provider
  bleiben Referenzimplementierung.
- Kosten-/Datenschutzrisiken bleiben sichtbar; Screen/Clipboard→Cloud brauchen künftig
  eine Übertragungsvorschau (Phase 2/9).
- Testkosten bleiben strukturell bei 0.

## Sicherheitsauswirkungen

- Cloud sieht potenziell persönliche/sensible Inhalte (Prompt, Screen-Vision, Clipboard).
  Datenklasse + Zweck müssen pro Übertragung nachvollziehbar sein; untrusted Inhalte
  dürfen keine Aktionen autorisieren.
- API-Keys bleiben in `config.json` (nicht in UI/Logs); DPAPI/Credential-Manager ist
  Folgeziel (Phase 2/10).

## Rücknahmekriterien

Neu bewerten bei: messbarem Bedarf für lokale Modelle (Kosten/Datenschutz/Offline),
Provider-Ausfall/Preisänderung, oder Threat-Model-Ergebnissen, die Cloud-Übertragungen
einschränken. Änderung nur über Adapter + aktualisierte ADR, nie als stiller Wechsel.
