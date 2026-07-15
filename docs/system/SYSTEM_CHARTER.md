# Jarvis – System Charter (Phase 0)

> Verbindliche System- und Programmgrenzen. Stand **2026-07-13**. Entscheidungen sind
> markiert als **[beschlossen]**, **[vorläufig]** oder **[ADR]** (später per ADR zu
> überprüfen). Bestätigt im Phase-0-Entscheidungsgate (Prompt 2).

## 1. Systemzweck

Jarvis ist ein **lokaler, persönlicher Sprach-Assistent** für den Windows-Arbeitsplatz:
Sprach-Konversation, Browser-Steuerung, Bildschirm-/Clipboard-Kontext, Obsidian-Notizen
und ein transparentes Gedächtnis. Zielbild (Masterplan): Wahrnehmen → Verstehen →
Vorschlagen → Autorisieren → Ausführen → Verifizieren → Erinnern — mit
nachvollziehbarer Freigabe für jede Wirkung. **[beschlossen]**

## 2. Vertrauensprinzip

Der stärkste Jarvis ist **nicht der autonomste**, sondern der nachvollziehbarste: jede
Wahrnehmung, Freigabe, Aktion und Erinnerung bleibt sichtbar, begrenzt und stoppbar.
Untrusted Inhalte (Web, Screen, Clipboard, Vault, Modellausgabe) dürfen **keine**
Aktionen autorisieren. **[beschlossen]**

## 3. Unterstützte Plattform

- **Betriebssystem:** Windows 10/11. **[beschlossen]**
- **Python:** Minimum **3.10**; Referenz-/Entwicklungslaufzeit beobachtet **3.14.5**
  (Suite lief laut `.pyc`-Artefakten auch unter 3.10). Verbindliche CI-Matrix (z.B.
  3.10–3.13 + 3.14) in Phase 3 festzulegen. **[vorläufig]**
- **Browser (Frontend/STT):** Google Chrome (Web Speech API). **[beschlossen]**

## 4. Prozess- und Deploymentmodell

- `jarvis-launcher.pyw` ist die sichtbare **Tray-/Desktop-App**. **[beschlossen]**
- FastAPI läuft als **ausschließlich lokal gebundener Hintergrundprozess**
  (`uvicorn` an `127.0.0.1`). **[beschlossen]** — [ADR 0001](../adr/0001-runtime-deployment-model.md)
- **Kein Windows-Service** in der ersten produktiven Stufe; erst nach einem konkreten
  unbeaufsichtigten Anwendungsfall (per ADR). **[ADR]**

## 5. Lokale Bindung und Expositionsgrenzen

- Server bindet nur an `127.0.0.1`; **keine öffentliche Exposition**, kein
  0.0.0.0-Bind, kein Reverse-Proxy in Phase 0. **[beschlossen]**
- Zusätzlicher Schutz von `/ws`: Origin-Check + lokales `SESSION_TOKEN`. **[beschlossen]**
- Der lokale Server wird nicht ins Internet gestellt (bewusstes Nicht-Ziel, §9). **[beschlossen]**

## 6. Cloud-/Local-Strategie

Ist-Zustand vs. Zielrichtung — [ADR 0002](../adr/0002-cloud-local-provider-strategy.md):

| Fähigkeit | Ist | Zielrichtung |
|---|---|---|
| LLM (Denken) | Anthropic Cloud (Claude) | über Adapter austauschbar **[vorläufig]** |
| Vision | Anthropic Cloud | über Adapter austauschbar |
| TTS | ElevenLabs Cloud | über Adapter austauschbar |
| STT | Browser Web Speech API | über Adapter austauschbar |
| Browsersteuerung | lokal (Playwright) | lokal |
| Memory/Vault | lokal (Obsidian/Markdown) | lokal |
| Launcher/Windows | lokal | lokal |

- **Keine erzwungene lokale Modellruntime** in Phase 0; lokale Alternativen erst nach
  messbarem Bedarf. **[beschlossen]**
- **Jede Cloud-Übertragung** braucht bekannte **Quelle**, **Datenklasse** und sichtbaren
  **Zweck**. **[beschlossen]**
- **Standardtests verursachen ausnahmslos keine Providerkosten.** **[beschlossen]**

## 7. Datenhoheit

- Nutzerwissen bleibt **lokal und lesbar** (Obsidian/Markdown ist Source of Truth);
  Langzeit-Gedächtnis ist eine editierbare Datei „Jarvis Memory.md". **[beschlossen]**
- **Secrets** (API-Keys) liegen nur in `config.json` (gitignored); die Settings-API
  liest/schreibt sie nie. Credential-Manager/DPAPI ist ein späteres Ziel (Phase 2/10).
  **[vorläufig]**
- Standardlogs enthalten keine vollständigen Gespräche, Screens oder Clipboard-Inhalte
  (private Inhalte nur auf DEBUG). **[beschlossen]**

## 8. Kompatibilitätsversprechen

- Der **visuelle Sieben-Phasen-Umbau ist als Baseline eingefroren**
  (siehe [CURRENT_STATE.md](CURRENT_STATE.md) §13); Regressionsnetz: `verify_phase4/5`.
- Bis zu einer **kontrollierten Migration** bleiben kompatibel: die 22
  `[ACTION:...]`-Typen, die WS-Frame-Typen (`health`, `response`, `action`, `error`,
  `stop`, `music_changed`, `app_event`, `launcher_changed` + Eingang `text`/`stop` +
  Auto-„Jarvis activate"), alle 24 Routen inkl. `/settings`-Whitelist und
  `/health`-Shape, das `config.json`-Format und alle in `FEATURES.md` dokumentierten
  Funktionen. **[beschlossen]**

## 9. Non-Goals (bewusst nicht)

Jarvis soll **nicht**: beliebige Shell-Kommandos aus Modellantworten ausführen;
unbekannte Runtime-Plugins selbst installieren; eigenen Code autonom ändern;
Bildschirm/Clipboard dauerhaft überwachen; heimlich Audio aufzeichnen; E-Mails/Käufe/
Löschungen/Veröffentlichungen autonom ausführen; den lokalen Server öffentlich
exponieren; Erinnerungen ausschließlich in undurchsichtiger Cloud speichern;
Hintergrundjobs ohne sichtbaren Status/Budget/Audit/Stop betreiben. **[beschlossen]**

## 10. Erste Budgets

Gemessen wo möglich (2026-07-13, lokal), sonst ausdrücklich **[zu bestätigen]**.
Grundlagen und Nicht-Ziele der Messung: [../quality/QUALITY_BASELINE.md](../quality/QUALITY_BASELINE.md).

| Budget | Wert | Grundlage / Status |
|---|---|---|
| Schnelle Suite Laufzeit | < 15 s | gemessen 2.35 s / 503 Tests **[beschlossen]** |
| `/health` In-Process-Latenz | < 50 ms | gemessen median 2 ms **[beschlossen]** |
| Kaltstart bis `/health` bereit | ≤ 5 s | Import+TestClient 1.3 s in-process; echter uvicorn-Kaltstart **[zu bestätigen]** |
| Stop-Bestätigung (lokal) | ≤ 300 ms | verify5 zeigt sofortigen Abbruch; ms-Messung **[zu bestätigen]** |
| Max. Browser-Tabs | 5 | `browser_tools.MAX_TABS` **[beschlossen]** |
| Max. Conversation-History | 60 gespeichert / 16 an LLM | `assistant_core.MAX_HISTORY` **[beschlossen]** |
| Providerkosten autom. Tests | 0 | verifiziert **[beschlossen]** |
| Max. externe Calls / Workflow | Q&A: 1 LLM + 1 TTS; Recherche: 3–5 Quellen + 1 LLM | Code/`FEATURES.md` **[vorläufig]** |
| Idle-RAM Server / Browser | – | Prozessmessung ausstehend **[zu bestätigen]** |

Messmethoden für „[zu bestätigen]": Kaltstart über den Launcher (`wait_for_server`);
Stop-Latenz über Browser-E2E-Zeitmessung; Idle-RAM über getrennte Prozessmessung von
uvicorn und Chromium. Ziele werden mit echten Messwerten in einer Folgephase fixiert.

## 11. Kriterien für spätere Änderungen dieser Entscheidungen

Jede Änderung an §4–§9 erfordert eine **neue oder aktualisierte ADR** mit Kontext,
Alternativen, Konsequenzen, Sicherheitsauswirkung und Rücknahmekriterium. Auslöser:
konkreter unbeaufsichtigter Use-Case (Service-Frage), messbarer Bedarf (lokale
Modellruntime), Threat-Model-Delta (Phase 2), oder eine kontrollierte Wire-Format-Migration.
Budgets (§10) werden fixiert, sobald reproduzierbare Messwerte vorliegen — ein
Überschreiten ist ein Untersuchungsgrund, kein stiller Normalzustand.
