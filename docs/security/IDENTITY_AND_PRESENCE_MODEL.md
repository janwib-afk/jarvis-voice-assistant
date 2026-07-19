# Jarvis – Identity and Presence Model (Phase 2)

> Wer darf was, unter welcher Präsenz. **Anforderungsdokument** — die Presence-Runtime
> ist noch **nicht** implementiert. Stand 2026-07-14. Bezug:
> [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md), Threats TM-003/TM-004.

## 1. Identitäten und Principals

| Principal | Bedeutung | Heute im Code |
|---|---|---|
| Legitimer lokaler Windows-Nutzer | Eigentümer der Sitzung | implizit (kein Identitätscheck) |
| Lokale UI-Sitzung | die vom Server ausgelieferte Seite/pywebview | Session-Token (`server.py:723`) |
| Voice-/Audioquelle | Eingabekanal Mikrofon → Text | keine Identität |
| UI-Klick | bewusste lokale Interaktion | Token-REST (`server.py:236`) |
| Remote-Sitzung | RDP/Remote-Desktop | nicht unterschieden (heute) |
| Geplanter Hintergrundjob | Scheduler/Routine (Phase 6/8) | **nicht vorhanden** |
| Connector-Principal | externer Dienst (Kalender/Mail, Phase 10) | **nicht vorhanden** |

## 2. Identität ≠ Präsenz

- **Identität** = *wer* handelt (legitimer Nutzer vs. anderer Principal).
- **Präsenz** = *in welchem Zustand* gehandelt wird (entsperrt/gesperrt/remote/Voice/
  UI-Klick/Hintergrund).
- **Kern-Invariante (SI-2):** Eine erkannte **Stimme ist kein Identitätsnachweis**. Der
  Token beweist „von dieser Server-Seite", nicht „vom legitimen Nutzer" — und ist über
  `GET /` für jeden lokalen Prozess lesbar (TM-003). Daher ersetzt weder Voice noch Token
  allein die Präsenz-/Bestätigungsanforderung für Hochrisiko.

## 3. Präsenzzustände und erlaubte Wirkungsklassen

| Präsenz | read-local | read-sensitive | network-read | local-write | local-execute | external-write | destructive |
|---|---|---|---|---|---|---|---|
| Lokal entsperrter Desktop | ✅ | ✅ | ✅ | ✅ | ✅ | UI-Bestätigung (geplant) | **Confirm** |
| Gesperrter Desktop | nur passiv (Status) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Remote-Desktop-Sitzung | nur passiv | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Voice-Befehl (Kanal) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (Voice allein nie) | ❌ (Voice allein nie) |
| UI-Klick | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (mit Preview) | ✅ (mit Confirm) |
| Geplante Hintergrundroutine | ✅ | ❌ | ✅ (mit Budget) | vorautorisiert | vorautorisiert | ❌ | ❌ |

Regeln:
- **Nur-Lesen-Kombinationen:** gesperrter/Remote-Desktop; Hintergrundroutine für
  `read-sensitive`.
- **Lokal schreiben erlaubt:** nur entsperrter Desktop (Voice oder UI).
- **Lokale Ausführung erlaubt:** nur entsperrter Desktop; Hintergrund nur vorautorisiert.
- **External-write möglich:** nur entsperrt **und** per UI-Bestätigung mit Preview
  (geplant, Phase 10) — nie durch Voice allein, nie durch untrusted Inhalt.
- **Zusätzliche sichtbare Bestätigung nötig:** `destructive` (heute Confirm),
  künftig alle `external-write` und Hochrisiko.
- **Nur per UI bestätigbar (geplant):** `external-write` und irreversibles Löschen über
  Vault hinaus — Voice darf hier nur vorschlagen.

## 4. Untrusted Inhalt

Untrusted Inhalt (Web/Vault/Clipboard/Screen/Recherche/LLM-Ausgabe) besitzt **keine**
Präsenz und **keine** Autorisierung. Er darf Vorschläge erzeugen, aber niemals eine
Wirkungsklasse freischalten oder Präsenz vortäuschen (SI-1).

## 5. Ablauf, Widerruf, künftige Bindung

- **Heute:** Session-Token je Prozess (`secrets.token_urlsafe(24)`, `server.py:44`),
  gültig bis Serverneustart; keine TTL je Aktion, keine Preview-Bindung.
- **Geplant (Phase 5/10):** Autorisierung für Hochrisiko/`external-write` wird an
  **Preview-Hash + Nutzerpräsenz + Ablaufzeit (TTL) + Correlation-ID** gebunden; eine
  Freigabe gilt nur für genau die vorab gezeigte Wirkung und verfällt.
- **Widerruf:** Panic Lock (geplant) entzieht laufende Autorisierungen und verlangt
  bewusste lokale Reaktivierung (SECURITY_REQUIREMENTS §9).

## 6. Verhalten bei Lock, Disconnect, Panic Lock

- **Desktop-Lock (geplant):** keine wirkenden Aktionen; nur passiver Status; Mikrofon-
  Verarbeitung für Wirkung ausgesetzt.
- **WS-Disconnect (heute):** Der `ConversationManager` schließt die Session, ihr Zustand
  wird verworfen und eine laufende Verarbeitung garantiert abgebrochen (RFC-0006; das
  frühere `assistant_core.end_session` existiert nicht mehr).
- **Stop (heute):** bricht Wiedergabe + laufende Aktion ab (`server.py:180`).
- **Panic Lock (geplant):** Mikro aus, Jobs stoppen, neue Jobs/Connectoren/`external-write`
  blockiert, sichtbarer Zustand, manuelle Reaktivierung.

## 7. Offene Entscheidungen

- Erkennung „gesperrter Desktop"/„Remote-Sitzung" (Win32 Session-APIs) — Umsetzung Phase 9.
- Push-to-Talk-Pflicht für wirkende Aktionen gegen Voice-Spoofing (TM-004) — empfohlen,
  Nutzerentscheidung offen.
- Ob der Fenster-Nonce (statt Token-in-HTML) die lokale Token-Lesbarkeit schließt (TM-003).
