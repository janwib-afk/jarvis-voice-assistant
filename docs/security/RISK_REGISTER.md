# Jarvis – Risk Register (Phase 2)

> Verfolgung aller Threats aus [../../jarvis-voice-assistant-threat-model.md](../../jarvis-voice-assistant-threat-model.md).
> Stand 2026-07-14. Status ∈ {open, mitigation-planned, mitigated, accepted, unacceptable,
> superseded}. **Kein Critical-Risiko** (lokal, kein Public-Exposure, kein external-write).
> Jedes High trägt konkrete Mitigation + Zielphase + messbares Gate.

| Threat ID | Risiko | Priority | Status | Vorhandene Kontrolle (Evidence) | Erforderliche Mitigation | Zielphase | Owner-Rolle | Nachweis/Gate | Restrisiko | Nutzerentscheidung |
|---|---|---|---|---|---|---|---|---|---|---|
| TM-001 | Untrusted Inhalt → LLM → Aktion (Prompt Injection) | **high** | mitigation-planned | `parse_action` (`actions.py:210`), Allowlist (`app_launcher.py:479`), OPEN http/https (`actions.py:171`), FORGET confirm | Untrusted-Content-Isolation; Wirkungen aus untrusted Text nur als Vorschlag; Wirkungsklassen-/Policy-Kernel; Preview für wirkende Aktionen | Phase 5 | Architektur+Security | Contract-Test: untrusted Inhalt kann keine `[ACTION:…]` autorisieren; Policy-Gate grün | medium (bis Phase 5) | Delegation: konservative Nutzung bis Phase 5 |
| TM-002 | SSRF über Browser/HTTP (nur Schema geprüft, Redirects offen) | **high** | mitigation-planned | http/https (`actions.py:171`), Size-Cap (`browser_tools.py:233`), Timeout | Host-Denylist (loopback/RFC1918/link-local/ULA/metadata); Redirect-Ziel re-validieren; DNS-Rebinding-Schutz; Selbstzugriff blocken | Phase 5 (ggf. vorziehen) | Security | Test: private/loopback/metadata-Hosts blockiert; Redirect-Revalidierung grün | medium | Delegation: Host-Policy priorisieren |
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
