# Jarvis – Risk Register (Phase 2)

> Verfolgung aller Threats aus [../../jarvis-voice-assistant-threat-model.md](../../jarvis-voice-assistant-threat-model.md).
> Stand 2026-07-14, ergänzt 2026-07-19 (Phase 5B). Status ∈ {open, mitigation-planned,
> mitigation-in-progress, mitigated, accepted, unacceptable, superseded}. **Kein
> Critical-Risiko** (lokal, kein Public-Exposure, kein external-write). Jedes High trägt
> konkrete Mitigation + Zielphase + messbares Gate.
>
> **Phase-5C-Nachtrag (2026-07-19, Prompt 20).** Die Vollmigration aller derzeit
> durchsetzbaren Pfade ist abgeschlossen: **22/22 Voice-Actions** und **9/10 mutierende
> REST-Routen** laufen ueber den Coordinator, das gespeicherte `ActionSpec.risk` und der
> `execute_action`-Fallback sind entfernt. **TM-001 und TM-002 bleiben trotzdem `high`.**
> TM-001 ist nicht geloest, sondern nur **flaechendeckend durchsetzbar** geworden — die
> zentrale SI-1-Regel greift jetzt fuer alle Pfade, aber untrusted Inhalt erreicht das
> Modell unveraendert. TM-002 bleibt **ohne IP-Pinning** nur teilweise mitigiert;
> **DNS-Rebinding zwischen Evidenz und Navigation ist weiterhin offen**.
> `launcher.profile.delete` ist die **einzige** ungeschuetzte mutierende Route (Phase 10).
>
> **Phase-5B-Nachtrag (2026-07-19).** Der Capability-/Policy-Kernel (RFC-0007 Pilotphase) ist
> implementiert. **TM-001 und TM-002 sind NICHT behoben** — nur teilweise bearbeitet: die
> zentrale SI-1-Durchsetzung und der SSRF-`TargetGuard` existieren, greifen aber erst für die
> **vier migrierten Piloten** bzw. lassen **DNS-Rebinding** ohne IP-Pinning offen. Beide
> bleiben **high**.

| Threat ID | Risiko | Priority | Status | Vorhandene Kontrolle (Evidence) | Erforderliche Mitigation | Zielphase | Owner-Rolle | Nachweis/Gate | Restrisiko | Nutzerentscheidung |
|---|---|---|---|---|---|---|---|---|---|---|
| TM-001 | Untrusted Inhalt → LLM → Aktion (Prompt Injection) | **high** | mitigation-in-progress (Phase 5C: **flaechendeckend durchsetzbar, nicht geloest**) | `parse_action` (`actions.py:210`), Allowlist (`app_launcher.py:479`), OPEN http/https (`actions.py:171`), FORGET confirm; **NEU (Phase 5B):** reiner Policy Kernel setzt SI-1 zentral durch (`derived` autorisiert nie), `[ACTION:…]` aus LLM-Antwort ist immer `derived` — für **alle 22 Actions und 9 von 10 mutierenden Routen** (Phase 5C) | **erledigt (Prompt 20)**; verbleibend: untrusted Inhalt vollständig als Vorschlag; Preview für wirkende Aktionen | Phase 5B (Pilot) → Prompt 20 (vollständig) | Architektur+Security | Contract-Test: `derived` kann keine `[ACTION:…]` autorisieren (`test_capability_policy`); Wirkungs-Zensus grün | medium (alle Pfade migriert, aber Injection selbst unveraendert moeglich) | Delegation: konservative Nutzung bis Vollmigration |
| TM-002 | SSRF über Browser/HTTP (nur Schema geprüft, Redirects offen) | **high** | mitigation-in-progress (Phase 5B: **teilweise mitigiert**) | http/https (`actions.py:171`), Size-Cap, Timeout; **NEU (Phase 5B):** reiner `TargetGuard` + zwei Produktionsadapter (httpx mit gepruefter Redirect-Kette **und** Playwright-Navigations-/Route-Guard + Nachprüfung der verbundenen IP); Denylist Loopback/RFC1918/link-local/ULA/metadata + Selbstzugriff `127.0.0.1:8340` (`test_capability_ssrf`) | **IP-Pinning gegen DNS-Rebinding** (eigene Verbindungsschicht) — bleibt offen | Phase 9 (IP-Pinning) | Security | Test: private/loopback/metadata blockiert je Hop; verbundene IP nachgeprüft — **grün** | **DNS-Rebinding bleibt Restrisiko** (kein IP-Pinning) | Delegation: Host-Policy umgesetzt, Rebinding-Rest datiert |
| TM-003 | Lokaler Prozess liest Token via `GET /` | medium | mitigation-planned | Token-Gate (`server.py:236`), Bind 127.0.0.1 (`:746`) | Token nicht in HTML einbetten (Fenster-Nonce/Handshake); `Sec-Fetch`/Origin prüfen; UI-Bestätigung für Hochrisiko | Phase 4/9 | Architektur | Test: `GET /` liefert kein nutzbares Token; Hochrisiko braucht UI-Confirm | niedrig (lokaler Zugriff teils out-of-scope) | accepted-interim (Malware=Benutzerrechte out-of-scope) |
| TM-004 | Voice-Spoofing / unauthentifizierte Voice-Aktion | medium | mitigation-planned | FORGET confirm; Wirkungen heute begrenzt | Invariante „Voice ≠ Identität"; Hochrisiko/destruktiv/external-write nur mit UI-Confirm; Push-to-Talk-Option | Phase 5/9 | Security+UX | Test: Voice allein autorisiert kein Hochrisiko | medium | Delegation: UI-Confirm für Hochrisiko |
| TM-005 | Vollbild-Capture → Cloud ohne Scope/Preview | medium | mitigation-planned | — (`screen_capture.py:13`) | Region/aktives Fenster; sichtbare Vorschau; Secret-Filter; Datenklasse `sensitive` | Phase 9 | Security+UX | Test/Manuell: Vorschau + Region vor Cloud-Versand | medium | Delegation: Region+Preview |
| TM-006 | Clipboard → Cloud ohne Preview/Filter | medium | mitigation-planned | Cap 4000, fixes Kommando (`clipboard_tools.py`) | Übertragungsvorschau; Secret-Muster-Filter | Phase 9 | Security+UX | Manuell/Test: Preview + Filter | medium | Delegation |
| TM-007 | Klartext-API-Keys in `config.json` | medium | mitigation-planned | Gitignored; `PROTECTED_KEYS`; Werte nie geloggt | DPAPI/Credential Manager (siehe CREDENTIAL_STRATEGY); Rotation | Phase 11 | Security | Keys nicht mehr im Klartext; Migration reversibel | niedrig | Delegation: DPAPI-Ziel |
| TM-008 | Persistente Memory-/Vault-Injection in den System-Prompt | medium | mitigation-planned | MEMORY_WRITE nur explizit; FORGET confirm; Context-Secret-Filter (`memory.py`) | Vault/Memory als untrusted markieren; Review-Inbox für Auto-Extraktion; Provenienz | Phase 7 | Architektur+Security | Test: injizierte Notiz autorisiert keine Aktion; Auto-Extraktion nur Review-Inbox | medium | Delegation |
| TM-009 | Supply-Chain (Provider/Dependency/Skill-Quelle) | low | mitigation-planned | `skills-lock.json`-Hashes; Skills geprüft (Phase 0/2); TLS | Dependency-Pinning/Hashes; Skill-Review beibehalten; Runtime/Dev trennen | Phase 11 | Maintainer | Lockfile-Review; gepinnte Deps | niedrig | Delegation |
| TM-010 | Lokale DoS / Ressourcenflut | low | mitigation-planned | MAX_TABS=5, MAX_HISTORY=60, Download-Cap, Timeouts, Stop | Zeit-/Kosten-/Call-Budgets je Workflow | Phase 6/11 | Architektur | Budget-Überschreitung stoppt kontrolliert | niedrig | Delegation |

## Hinweise

- **Keine** offenen Critical-Risiken.
- Beide High-Risiken (TM-001, TM-002) haben konkrete Mitigation + Zielphase + messbares
  Gate — die Phase-2-Gate-Bedingung für High ist damit erfüllt; zusätzlich ist die
  interim-Restakzeptanz (konservative Nutzung) über die Nutzer-Delegation dokumentiert.
- `accepted-interim` (TM-003) bezieht sich ausschließlich auf den out-of-scope-Anteil
  „Malware mit Benutzerrechten"; der Token-in-HTML-Anteil bleibt `mitigation-planned`.
- Kein Risiko ist `unacceptable`; keines wurde `superseded` (Erstanlage).
