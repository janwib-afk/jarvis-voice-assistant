# RFC-0007 — Capability- und Policy-Kernel

- **Status:** Accepted for incremental implementation (2026-07-19) — **inkl.
  [Amendment 1](#amendment-1--pilotphase-wirkungsinventar-ssrf-durchsetzung-und-lifecycle-grenzen)**
- **Phase:** 5A (Architektur) — Umsetzung frühestens Prompt 19
- **Datum:** 2026-07-19
- **Basis:** `master 98244a08` (Post-Merge-Gate `29680320223`, Fast + Browser erfolgreich)
- **Bindend vorgelagert:** SI-1 … SI-9 (`docs/security/SECURITY_REQUIREMENTS.md`),
  ADR-0004/0005, RFC-0001 … RFC-0006 einschließlich Amendments

> Dieses RFC ist **Architektur**. Es ändert keinen Produktionscode, keine Tests, keinen
> Workflow und keine Abhängigkeit. Es markiert insbesondere **keinen** Threat als behoben:
> TM-001 und TM-002 bleiben offen, bis Prompt 19 sie im Code mitigiert.

---

## 1. Scope, Ziele, Nicht-Ziele

### Ziele

1. Einen **typisierten Capability-Vertrag** definieren, der die heute nur in
   Sicherheitsdokumenten existierenden Begriffe — Datenklasse, Wirkungsklasse, Scopes,
   Presence, Preview, Verify, Audit — in der Laufzeit **darstellbar** macht.
2. Eine **einzige Stelle** definieren, an der die Frage „darf diese Wirkung jetzt, aus
   dieser Quelle, mit dieser Provenance und dieser Präsenz passieren?" beantwortet wird.
3. Die **vollständige Wirkungsfläche** erfassen — nicht nur die 22 Actions.
4. Die Abgrenzung zwischen der bestehenden mündlichen **Confirmation** und einer künftigen
   **Authorization** verbindlich festlegen.
5. Vertikale, einzeln rückrollbare **Migrationsslices** für Prompt 19 festlegen.

### Nicht-Ziele (ausdrücklich)

Job-Engine, Persistenz, SQLite, Outbox, Saga, Resume, Checkpoints, Exactly-once,
Retry-Engine, Compensation-Engine, Scheduler, Connectoren, DPAPI, Win32-Lock-/RDP-Erkennung,
Screen-/Clipboard-Preview-**UI**, STT-/TTS-/Audioänderungen, Panic Lock, vollständiger
Audit-/Event-Store, vollständiges Tracing, Protocol-Major-Bump, Legacy-Abschaltung,
dynamische Runtime-Plugins, UI-Redesign.

---

## 2. Belegtes Ist-Inventar

Alle Angaben sind am Code des Basis-SHA verifiziert, nicht geschätzt.

### 2.1 Action-Capabilities

`actions.REGISTRY` enthält **22** Einträge (per Import gezählt, nicht per Textsuche):

```
APP_AUTOSTART_OFF  APP_AUTOSTART_ON  APP_OPEN     APP_PLACE   BROWSE
CLIPBOARD          CLIPBOARD_NOTE    INBOX_READ   INBOX_WRITE MEMORY_FORGET
MEMORY_READ        MEMORY_WRITE      NEWS         NOTES_RECENT OPEN
PROFILE_ACTIVATE   PROFILE_STATUS    PROJECT_CONTEXT RESEARCH  SCREEN
SEARCH             SESSION_SUMMARY
```

Damit bestätigt sich die Zahl 22 aus `CAPABILITY_MATRIX.md` und
`SECURITY_REQUIREMENTS.md` §10. **21** davon sind im Prompt beworben
(`describe != None`); `BROWSE` ist ausführbar, aber bewusst nicht beworben (RFC-0001).

### 2.2 Der zentrale Befund: die Laufzeit kennt das Sicherheitsmodell nicht

`ActionSpec` trägt die Felder `type, label, payload, is_url, risk, timeout, is_browser,
speaks_result, summary_task, summary_max_tokens, execute, describe, prompt_order,
prompt_group`.

**`risk` ist zweiwertig:** `low` oder `confirm`. `CONFIRM_ACTIONS` enthält genau einen
Eintrag: `MEMORY_FORGET`.

| Dokumentierter Begriff | Definiert in | In der Laufzeit |
|---|---|---|
| 5 Datenklassen (`public`…`secret`) | SECURITY_REQUIREMENTS §2 | **existiert nicht** |
| 7 Wirkungsklassen (`read-local`…`destructive`) | SECURITY_REQUIREMENTS §3 | **existiert nicht** |
| 6 Präsenzzustände | IDENTITY_AND_PRESENCE_MODEL §3 | **existiert nicht** |
| Scopes | — | **existiert nicht** |
| Preview / Verify / Audit-Metadaten | SECURITY_REQUIREMENTS §5 | **existiert nicht** |

Konkrete Folge: `SCREEN` (Vollbildaufnahme → Cloud-Vision) und `CLIPBOARD`
(Zwischenablage → Cloud-LLM) tragen `risk="low"` und sind damit von `SEARCH`
nicht unterscheidbar.

### 2.3 Wirkungsproduzenten — vier, aber nur einer hat eine Registry

| Produzent | Anzahl wirkender Pfade | Kennt `actions.REGISTRY`? |
|---|---|---|
| Stimme/LLM über `[ACTION:…]` | 22 | ja |
| UI/REST | 10 zustandsändernde Routen | **nein** |
| Nativ (Klatschen, PS1, Launcher) | mehrere, teils **außerhalb des Serverprozesses** | **nein** |
| Startup/Lifespan | 1 (ausgehend + Dateisystem) | **nein** |

Die 10 zustandsändernden Routen (von 24 Routen insgesamt):
`POST /settings`, `POST /music/selection`, `POST /commands/app/open`,
`POST /launcher/apps/{id}/placement`, `POST /launcher/apps/{id}/toggle`,
`POST /launcher/profiles`, `DELETE /launcher/profiles/{id}`,
`POST /launcher/profiles/{id}/activate|rename|duplicate`.

**Profile anlegen, löschen, umbenennen und duplizieren haben keine Action-Entsprechung.**
Sie sind ausschließlich über REST erreichbar.

### 2.4 Wirkungen, die `spec.execute()` nicht sieht

Dies ist die Begründung dafür, warum ein Vertrag an `ActionSpec` nicht ausreicht.

| Wirkung | Ort | Auslöser | Klasse (nach Doku-Taxonomie) |
|---|---|---|---|
| Haupt-LLM-Aufruf | `assistant_core.py:413` | jede Nachricht | `network-read` |
| Summary-LLM-Aufruf | `assistant_core.py:358` | 8 der 22 Actions | `network-read` |
| TTS (ElevenLabs) | `assistant_core.py:224` | jede gesprochene Antwort | `network-read` |
| Recherche-Autosave | `assistant_core.py:305` | nach `RESEARCH` | `local-write` |
| Wetter + Vault-Scan | `runtime.py:147` | **Serverstart** | `network-read` + `read-sensitive` |
| Wetter + Vault-Scan | `server.py:369` | **nach jedem Settings-Save** | dito |
| Sichtbarer Chromium-Prozess | `browser_tools.py:56` | erste Browser-Action | `local-execute` |
| PowerShell `SetForegroundWindow` | `browser_tools.py:27` | SEARCH/NEWS/OPEN/RESEARCH | `local-execute` |
| `taskkill /F` auf Port 8340 | `jarvis-launcher.pyw:104` | nativer Start | `local-execute` |
| Globaler Tastatur-Hook (Win+J) | `jarvis-launcher.pyw:258` | nativer Start | `local-execute` |
| Zwischenablage **schreiben** | `frontend/main.js:909` | Kopier-Button | `local-write` |
| Server als Kindprozess starten | `jarvis-launcher.pyw:84` | nativer Start | `local-execute` |

Die 8 Actions mit Summary-LLM-Aufruf: `CLIPBOARD`, `INBOX_READ`, `MEMORY_FORGET`,
`MEMORY_READ`, `NOTES_RECENT`, `PROJECT_CONTEXT`, `RESEARCH`, `SESSION_SUMMARY`.

### 2.5 SSRF — belegter Ist-Stand

- `actions.normalize_url` prüft **ausschließlich das Schema** (`http`/`https`); der Host
  wird nie geprüft.
- `browser_tools.py:179` und `:270` verwenden `follow_redirects=True`; kein Redirect-Ziel
  wird revalidiert.
- `actions.is_allowed_origin` ist eine **eingehende** Origin-Prüfung für den
  WS-Handshake und hat mit ausgehenden Zielen nichts zu tun.

Damit bleibt TM-002 unverändert offen.


### 2.6 Vollständige Wirkungsmatrix

Producer/Entry Point → Provenance → Primärwirkung → Folge-/Cloudwirkung → Datenklasse
→ Wirkungsklasse → Scope → Autorisierung heute → benötigte Policy → Migrationsslice.

#### 2.6.1 Action-Capabilities (Produzent: Stimme/LLM, Provenance immer *derived*)

Die Spalte *Folge-/Cloudwirkung* ist der Kern dieser Tabelle: sie listet, was heute an
der Ausführungsfunktion vorbei passiert und deshalb in keiner Klassifikation auftaucht.
| Action | Primärwirkung | Folge-/Cloudwirkung (heute unsichtbar) | Datenklasse | Wirkungsklasse | Scope | Autorisierung heute | Policy nötig | Slice |
|---|---|---|---|---|---|---|---|---|
| `APP_AUTOSTART_OFF` | Clap-Start aus | TTS | local | local-write | config.launcher | Voice/UI (implizit) | Provenance | 8 |
| `APP_AUTOSTART_ON` | Clap-Start an | TTS | local | local-write | config.launcher | Voice/UI (implizit) | Provenance | 8 |
| `APP_OPEN` | App öffnen | TTS | local | local-execute | apps | Allowlist | Provenance | 8 |
| `APP_PLACE` | App platzieren | TTS | local | local-write | config.launcher | Voice/UI (implizit) | Provenance | 8 |
| `BROWSE` | Seite lesen | Chromium-Fenster + PowerShell-Fokus, TTS | public | network-read | web | URL-Policy (nur Schema!) | SSRF-Ziel + Provenance | 8 |
| `CLIPBOARD` | Zwischenablage | Summary-LLM, TTS | sensitive | read-sensitive + network-read | clipboard | Voice/UI (implizit) | SSRF-Ziel + Presence (Ph. 9) + Provenance | 8 |
| `CLIPBOARD_NOTE` | Clipboard-Notiz | TTS | sensitive→personal | local-write | clipboard+vault | Voice/UI (implizit) | Provenance | 8 |
| `INBOX_READ` | Inbox lesen | Summary-LLM, TTS | personal | read-sensitive | vault | Voice/UI (implizit) | Presence (Ph. 9) + Provenance | 8 |
| `INBOX_WRITE` | Inbox-Eintrag | TTS | personal | local-write | vault | Voice/UI (implizit) | Provenance | 8 |
| `MEMORY_FORGET` | Vergessen | Summary-LLM, TTS | personal | **destructive** | vault | **Confirm** | Confirm + Provenance | 5 |
| `MEMORY_READ` | Gedächtnis lesen | Summary-LLM, TTS | personal | read-sensitive | vault | Voice/UI (implizit) | Presence (Ph. 9) + Provenance | 8 |
| `MEMORY_WRITE` | Merken | TTS | personal | local-write | vault | Voice/UI (implizit) | Provenance | 8 |
| `NEWS` | Nachrichten | Chromium-Fenster + PowerShell-Fokus, TTS | public | network-read | web | Voice/UI (implizit) | SSRF-Ziel + Provenance | 8 |
| `NOTES_RECENT` | Letzte Notizen | Summary-LLM, TTS | personal | read-sensitive | vault | Voice/UI (implizit) | Presence (Ph. 9) + Provenance | 8 |
| `OPEN` | Browser öffnen | Chromium-Fenster + PowerShell-Fokus, TTS | public | local-execute + network-read | web | URL-Policy (nur Schema!) | SSRF-Ziel + Provenance | 8 |
| `PROFILE_ACTIVATE` | Profil aktivieren | TTS | local | local-write | config.launcher | Voice/UI (implizit) | Provenance | 8 |
| `PROFILE_STATUS` | Profil-Status | TTS | local | read-local | config.launcher | Voice/UI (implizit) | Provenance | 8 |
| `PROJECT_CONTEXT` | Projekt-Kontext | Summary-LLM, TTS | personal | read-sensitive | vault | Voice/UI (implizit) | Presence (Ph. 9) + Provenance | 8 |
| `RESEARCH` | Recherche | Summary-LLM, Chromium-Fenster + PowerShell-Fokus, Vault-Autosave, TTS | public→personal | network-read + local-write | web+vault | Voice/UI (implizit) | SSRF-Ziel + Provenance | 8 |
| `SCREEN` | Bildschirm ansehen | TTS | sensitive | read-sensitive + network-read | screen | Voice/UI (implizit) | SSRF-Ziel + Presence (Ph. 9) + Provenance | 8 |
| `SEARCH` | Websuche | Chromium-Fenster + PowerShell-Fokus, TTS | public | network-read | web | Voice/UI (implizit) | SSRF-Ziel + Provenance | 3 |
| `SESSION_SUMMARY` | Sitzungsfazit | Summary-LLM, TTS | personal | read-local | — | Voice/UI (implizit) | Provenance | 8 |


### 2.6.2 Direkte REST-/UI-Wirkungen (kein Action-Pfad)

Provenance dieser Zeilen ist durchgehend `operator` (bewusster lokaler UI-Klick), nicht
`derived`.

| Route | Primärwirkung | Folgewirkung | Datenklasse | Wirkungsklasse | Autorisierung heute | Policy nötig | Slice |
|---|---|---|---|---|---|---|---|
| `POST /settings` | Einstellungen speichern | **`refresh_data`: wttr.in + Vault-Scan** | personal/local | local-write | Token + Whitelist | Provenance | 9 |
| `POST /music/selection` | Musikauswahl speichern | ggf. `refresh_data` | local | local-write | Token | Provenance | 9 |
| `POST /commands/app/open` | App starten | — | local | local-execute | Token + Allowlist | Provenance | 9 |
| `POST /launcher/apps/{id}/toggle` | Autostart schalten | — | local | local-write | Token | Provenance | 9 |
| `POST /launcher/apps/{id}/placement` | Platzierung setzen | — | local | local-write | Token | Provenance | 9 |
| `POST /launcher/profiles` | Profil anlegen | — | local | local-write | Token | Provenance | 9 |
| **`DELETE /launcher/profiles/{id}`** | **Profil löschen** | — | local | **destructive** | **nur Token — keine Bestätigung, keine Vorschau** | **Confirm-Äquivalent** + Provenance | **6 (Pilot)** |
| `POST /launcher/profiles/{id}/activate` | Profil aktivieren | — | local | local-write | Token | Provenance | 9 |
| `POST /launcher/profiles/{id}/rename` | Profil umbenennen | — | local | local-write | Token | Provenance | 9 |
| `POST /launcher/profiles/{id}/duplicate` | Profil duplizieren | — | local | local-write | Token | Provenance | 9 |

> **Belegte Asymmetrie.** `DELETE /launcher/profiles/{id}` (`server.py:833`) prüft Token,
> Existenz und Intent-Guards und löscht dann — **ohne jede Bestätigung**. Ein
> Gedächtniseintrag zu vergessen verlangt heute eine mündliche Rückfrage; ein ganzes Profil
> zu löschen verlangt nichts. Genau deshalb ist diese Route ein Pilot (D8).

### 2.6.3 Wirkungen ohne Nutzerauslöser

| Wirkung | Ort | Auslöser | Wirkungsklasse | Policy nötig | Slice |
|---|---|---|---|---|---|
| `context.refresh` (wttr.in + Vault-Scan) | `runtime.py:147` | **Serverstart** | network-read + read-sensitive | SSRF-Ziel | **7 (Pilot)** |
| `context.refresh` | `server.py:369` | **nach jedem Settings-Save** | dito | SSRF-Ziel | **7 (Pilot)** |
| Haupt-LLM-Aufruf | `assistant_core.py:413` | jede Nachricht | network-read | — (Teil des Turns, D4) | — |

### 2.6.4 Nativ — außerhalb des Kernels (D3)

Diese Pfade laufen teils **außerhalb des Serverprozesses** und können keinen In-Process-Kernel
fragen. Sie sind hier namentlich benannt, damit die Lücke belegt und nicht versehentlich ist.

| Wirkung | Ort | Auslöser | Wirkungsklasse |
|---|---|---|---|
| `taskkill /F` auf dem Port-8340-Inhaber | `jarvis-launcher.pyw:104` | nativer Start | local-execute |
| Server als Kindprozess starten | `jarvis-launcher.pyw:84` | nativer Start | local-execute |
| Globaler Tastatur-Hook (Win+J) | `jarvis-launcher.pyw:258` | nativer Start | local-execute |
| `launch-session.ps1` starten | `clap-trigger.py:85` | Doppelklatschen | local-execute |
| Programme starten, Fenster platzieren | `launch-session.ps1` | Sessionstart | local-execute |
| Zwischenablage **schreiben** | `frontend/main.js:909` | Kopier-Button in der UI | local-write |

**Grenzvertrag (D3).** Diese Pfade bleiben in Phase 5 außerhalb des Kernels. Begründung:
Wer klatschen oder Win+J drücken kann, steht physisch am Gerät — physischer Zugriff ist
ohnehin die stärkere Berechtigung, und ein Out-of-Process-Policy-Aufruf bräuchte einen
zweiten Vertrauensanker außerhalb des Servers, der genau dann fehlt, wenn der Clap-Trigger
den Server erst startet.

**Verbindliche Regel:** Es darf **kein neuer nativer Wirkungspfad ohne Kernel** hinzukommen.
Wer einen anlegt, muss diesen Abschnitt ändern — und das ist im Diff sichtbar.

---

## 3. Decision Log

Jede Entscheidung wird hier sofort nach der Bestätigung festgehalten. „Bestätigt" heißt:
vom Nutzer ausdrücklich gewählt, nicht von mir angenommen.

| # | Entscheidung | Gewählt | Status |
|---|---|---|---|
| **D1** | **Architekturkandidat** | **Variante C** — transportneutraler Capability Core + reiner Policy Kernel + runtime-eigener Coordinator; `[ACTION:…]`, REST/UI und ggf. strukturierte Tool Calls werden Adapter vor demselben Core. | bestätigt |
| **D2** | **Öffentliche Interface** | **Hybrid** aus dem Design-It-Twice: Rückgrat „häufigster Aufrufer" (abgeleiteter `tier()`, Pflichtfelder ohne Defaults) + öffentliches `inspect()` aus dem Minimal-Entwurf + Regeltabelle aus dem Flexibilitäts-Entwurf, **ohne** `attributes` und `with_rules`. | bestätigt |
| **D3** | **Native Wirkungspfade** | **Dokumentierte Ausnahme mit Grenzvertrag.** Die außerhalb des Serverprozesses laufenden Pfade bleiben außerhalb des Kernels, werden aber namentlich benannt und begründet; Regel: **kein neuer nativer Wirkungspfad ohne Kernel**. | bestätigt |
| **D4** | **Orchestrierungs-Wirkungen** | Summary-LLM, TTS und Recherche-Autosave werden als **Effekte am Vertrag der auslösenden Capability** deklariert. Der **Haupt-LLM-Aufruf** bleibt Teil des Conversation Turns (kein Attempt). **`refresh_data` wird eine eigene Capability**, weil es keinen Action-Pfad hat und aus zwei Nicht-Nutzer-Quellen ausgelöst wird. | bestätigt |
| **D5** | **Authorization Grant** | **Nur Vertrag, keine Laufzeit.** Vollständig spezifiziert (Preview-Hash-Bindung, TTL, Single-Use, fail-closed-Invalidierung, „Voice erfüllt nie einen Grant"), aber in Phase 5 **nicht implementiert**. Damit entsteht kein `awaiting-authorization` und **RFC-0006 bleibt unverändert — kein Amendment nötig**. | bestätigt |
| **D6** | **Fail-closed vs. fehlende Presence** | **Nur erfüllbare Regeln werden aktiviert.** Die Klassifikation gilt ab Phase 5 und ist testbar; eine Regel, deren Anforderung in Phase 5 niemand erfüllen kann (`presence:unlocked` ohne Win32-Erkennung), wird **nicht aktiviert**, sondern mit Phasen-Datum eingetragen. Fail-closed gilt **vollumfänglich für jede aktive Regel**. Ausdrücklich abgelehnt: `unknown` als „erlaubt" durchzuwinken (fail-open unter fail-closed-Namen). | bestätigt |
| **D7** | **SSRF-Durchsetzungspunkt** | **Policy deklariert, Transport erzwingt.** Prüfung der tatsächlich aufgelösten IP bei **jeder** Verbindung inklusive **jedes Redirect-Hops**, in einer `httpx`-Transportschicht. Denylist (freies Browsen ist der Zweck): Loopback, RFC1918, Link-local, IPv6-ULA, Cloud-Metadata, **Selbstzugriff `127.0.0.1:8340`**. Vollständiges **IP-Pinning gegen DNS-Rebinding wird als benanntes Restrisiko datiert**, nicht halb gebaut. | bestätigt |
| **D8** | **Pilot-Capabilities** | Vier Piloten, die die Wirkungsmatrix aufspannen: **`SEARCH`** (Voice, `network-read`, fährt die SSRF-Transportschicht), **`MEMORY_FORGET`** (Voice, `destructive`, beweist dass Confirmation Confirmation bleibt), **`launcher.profile.delete`** (REST-only, schließt den Bypass), **`context.refresh`** (kein Nutzerauslöser, fährt Startup und Settings-Save). | bestätigt |
| **D9** | **Wire-/Legacy-/Frontend-Vertrag** | **Keine neuen Wire-Typen in Phase 5.** `Outcome` wird in den Adaptern auf bestehende Frames abgebildet (`needs` → bestehender gesprochener Confirm-Pfad, `denied` → vorhandener `error`-Frame, `ok` → `response` bzw. bestehende REST-Antwort). Legacy bleibt damit byte-exakt, das Frontend unverändert. Die additiven V1-Formen werden **spezifiziert, aber nicht gebaut** (kein zweiter Leser — Zwei-Adapter-Regel). | bestätigt |
| **D10** | **Doppelwahrheit vermeiden** | **Der Vertrag ist die Wahrheit.** `ActionSpec.risk` bleibt für RFC-0001-Kompatibilität sichtbar, wird aber **nicht mehr gespeichert, sondern aus dem Vertrag berechnet** — ein Widerspruch ist damit nicht darstellbar statt nur unwahrscheinlich. **Deletion Gate:** das gespeicherte `risk`-Feld fällt erst bei 22/22 migrierten Actions **und** grüner Suite, nicht schon bei den Piloten. | bestätigt |

**Begründung zu D1 (aus der Evidenz, nicht aus Präferenz):** Drei der vier
Wirkungsproduzenten kennen `actions.REGISTRY` nicht (§2.3). Jeder Entwurf, der den Vertrag
an `ActionSpec` hängt, ist ab dem ersten Tag unvollständig, und die Lücke ist von außen
nicht sichtbar — das wäre schlechter als der heutige Zustand, weil es Sicherheit
vortäuscht. Variante B verteilt die Policy auf N Module und macht SI-1 N-fach verletzbar.
Variante C setzt das Muster fort, das dieses Repository bereits dreimal geliefert hat
(RFC-0003 Single Writer, RFC-0005 Codec + Adapter, RFC-0006 reiner Kern + Effekte außen).

**Begründung zu D2:** Drei unabhängige Entwürfe konvergierten auf Paketform, eingefrorene
Verträge, reine `decide()` und runtime-eigenen Coordinator. Der ausschlaggebende Unterschied
war nicht Tiefe oder Locality — dort lagen alle drei nahe beieinander —, sondern die Frage
**wer sich irren kann und ob es auffällt**. Der reale Fehlermodus ist nicht ein böswilliger
Aufrufer, sondern jemand, der später eine Capability hinzufügt und nicht nachdenkt. Nur das
gewählte Rückgrat macht Schweigen strukturell unmöglich: `effects`/`reads`/`writes` ohne
Defaults (Weglassen = `TypeError` beim Registry-Bau) und ein **abgeleiteter** `tier()`, den
niemand behaupten kann. Das öffentliche `inspect()` kam hinzu, weil eine kostenlose,
reine Vorabprüfung vier Konsumenten bedient (UI-Ausgrauen, passives `/health`,
Prompt-Filterung, Kernel-Tests) — eine teure Vorabprüfung würde unterlassen. Die
Erweiterungspunkte `attributes` und `with_rules` bleiben draußen, bis ein zweiter Leser
existiert (Zwei-Adapter-Regel aus `DEEPENING.md`: ein Adapter ist ein hypothetischer Seam).

---


## 4. Domänenbegriffe und Abgrenzungen

Diese Begriffe sind Jarvis-spezifisch und gehören nach Abschluss in `CONTEXT.md`.
Allgemeine Programmierbegriffe (Adapter, Interface, Transition, Effect) gehören **nicht**
dorthin und stehen nur hier.

| Begriff | Bedeutung | Abgrenzung |
|---|---|---|
| **Capability** | Eine benannte, versionierte Fähigkeit mit deklarierten Wirkungen. | Nicht die *Action* (das ist der `[ACTION:…]`-Adapter) und nicht die Ausführungsfunktion. |
| **Capability Attempt** | Ein einzelner Ausführungsversuch einer Capability. | **Weder** Conversation Turn (der gehört der Session) **noch** Job (dauerhaft, Phase 6). Überlebt keinen Prozessneustart. |
| **Policy Decision** | Das Ergebnis der reinen Entscheidungsfunktion: erlauben, verweigern oder Anforderungen stellen. | Nicht die Ausführung und nicht die Confirmation. |
| **Effect Class** | Was eine Wirkung *tut* (7 Werte). | Nicht was sie *anfasst* — das ist die Data Class. |
| **Data Class** | Wie schutzbedürftig die berührten Daten sind (5 Werte). | Nicht die Wirkungsklasse. |
| **Provenance** | Ob die Eingabe vom Bediener stammt oder aus untrusted Inhalt abgeleitet ist. | Nicht Identität und nicht Präsenz. |
| **Presence Evidence** | Beobachtete Aussage über den Zustand des lokalen Desktops. | Nicht Identität. Fehlt sie, ist sie `unknown` — nicht „entsperrt". |
| **Confirmation** | Mündliche Ja/Nein-Rückfrage vor einer riskanten Action (heute nur `MEMORY_FORGET`). | **Keine** Autorisierung. Beweist Absicht, nicht Identität. |
| **Authorization Grant** | An Preview-Hash, TTL und Single-Use gebundene Freigabe durch die lokale UI. | Nicht die Confirmation. Voice kann ihn **nie** erfüllen. |

---

## 5. Untersuchte Architekturvarianten

| Variante | Kern | Verworfen weil |
|---|---|---|
| **A** `ActionSpec` additiv vertiefen | Registry wächst um Klassen; Gate vor `execute()`. | Der Seam sitzt am `[ACTION:…]`-Legacy-Adapter. Die 10 REST-Routen, die nativen Pfade und der Startup-Pfad kennen die Registry nicht — die Lücke wäre von außen unsichtbar. |
| **B** Capability-Module mit eigener Policy | Jede Fähigkeit trägt Lifecycle **und** Policy. | Verteilt genau die Entscheidung, die zentral gehört. SI-1 wäre N-fach implementiert und N-fach verletzbar; die Interface-Fläche wächst mit N (flaches Modul). |
| **C** Core + Kernel + Coordinator | Drei Module mit kleinem Interface; alle Produzenten werden Adapter. | **Gewählt (D1).** |

---

## 6. Design-It-Twice-Ergebnisse

Drei unabhängige Entwürfe mit gegensätzlichen Vorgaben. Alle drei konvergierten auf
Paketform neben `conversation/`, eingefrorene Verträge, reine `decide()`, runtime-eigenen
Coordinator, Vertrag-als-Port und Wiederverwendung von `wire_protocol/_seams.py`.

| Entwurf | Stärke | Schwäche (vom Entwurf selbst benannt) |
|---|---|---|
| **Minimalste Interface** | Zwei Namen (`inspect`/`attempt`) für vier Konsumenten; höchste Tiefe. | Ein `on_step`-Kanal trägt Fortschritt, TTS und Cancel zugleich; Policy ohne Registry nicht nutzbar. |
| **Maximale Flexibilität** | Regeltabelle; Phase 6/9/10 sind je eine neue Regel, `decide()` bewegt sich nie. | `attributes` und `with_rules` haben am ersten Tag **null Nutzer**; hoher Deklarationsaufwand bei einer einzigen feuernden Regel. |
| **Häufigster Aufrufer** | **Abgeleiteter `tier()`** und Pflichtfelder ohne Defaults — Schweigen ist strukturell unmöglich. | Nichts hindert einen Menschen, Destruktives als `READ_LOCAL` zu deklarieren; Gegenmittel ist ein eingefrorener Zensus. |

**Warum der Hybrid (D2):** Tiefe und Locality lagen nahe beieinander; ausschlaggebend war,
**wer sich irren kann und ob es auffällt**. Der reale Fehlermodus ist jemand, der später
eine Capability hinzufügt und nicht nachdenkt.

---

## 7. Ownership, Module, Interfaces, Seams

```
capability/
  __init__.py        oeffentliche Oberflaeche (klein)
  _contract.py       Capability Core  — WAS es gibt      (rein, I/O-frei)
  _policy.py         Policy Kernel    — OB es darf       (rein, I/O-frei, total)
  _coordinator.py    Coordinator      — WIE es ablaeuft  (runtime-eigen)
  _legacy.py         Adapter [ACTION:...] -> Capability
```

**Besitz.** Die `Runtime` konstruiert genau einen Coordinator als Instanzattribut — exakt
wie heute `configuration`, `wire_protocol`, `connections` und `conversation_manager`
(`runtime.py:55–71`). **Keine neuen Modul-Globals, kein Service Locator.**

**Seams.**

| Seam | Art | Adapter |
|---|---|---|
| `SEAM-CAPABILITY` | Contract (Registry + `inspect`) | — (rein) |
| `SEAM-POLICY` | Contract (`decide`) | — (rein) |
| `SEAM-CAPABILITY-COORDINATION` | Integration | Fake-Verträge im Test |
| SSRF-Transport | Ports & Adapters | Produktions-Transport + Test-Transport (zwei Adapter ⇒ echter Seam) |

Presence bekommt in Phase 5 **keinen** Seam: es gäbe genau einen Adapter, der immer
`unknown` liefert. Der fail-closed-Default lebt im Feld, nicht in einem Port
(`DEEPENING.md`: ein Adapter ist ein hypothetischer Seam).

---

## 8. Capability-Identität, Versionierung, Schema

- **Name:** stabile, punktierte Kennung — `memory.forget`, `launcher.profile.delete`,
  `context.refresh`. Für die 22 Legacy-Actions bildet `_legacy.py` `ActionSpec.type` auf
  den Namen ab; die `[ACTION:TYP]`-Syntax bleibt unverändert.
- **Version:** ganzzahlig je Capability, beginnend bei 1. Sie ändert sich, wenn sich
  Eingabeschema **oder deklarierte Wirkungen** ändern — nicht bei reinen
  Implementierungsänderungen. Die Version geht in den Idempotency Key ein.
- **Schema:** deklarative Eingabeform je Capability. Adapter wandeln in sie um; der Core
  validiert. Ein Adapter, der Unsinn schickt, ist ein Fehler und wirft — er bekommt
  kein `Outcome`.
- **Registry:** nach Konstruktion eingefroren. Namen sind eindeutig und werden nie für
  andere Wirkungen wiederverwendet. Ein unbekannter Name ist ein Fehler, nie ein Fallback.

---

## 9. Der Capability-Vertrag

Der Vertrag muss alles Folgende ausdrücken können. **`effects`, `reads` und `writes` haben
keine Defaults** — sie wegzulassen ist ein `TypeError` beim Registry-Bau (D2).

| Feld | Zweck |
|---|---|
| `name`, `version` | stabile Identität |
| `title` | Anzeigename (UI-Metadatum) |
| `inputs` | typisiertes Eingabeschema |
| `output` | typisiertes Ergebnisschema |
| `effects` | **Pflicht** — Menge der Wirkungsklassen, **inklusive Folgewirkungen** (D4) |
| `reads`, `writes` | **Pflicht** — Datenklassen |
| `scopes` | benötigte Berechtigungsbereiche |
| `timeout_s` | Obergrenze je Versuch |
| `retry` | **Eignung**, deklarativ (`never` / `on_timeout` / `on_transport`) — keine Engine |
| `cancellable` | ob ein Abbruch sinnvoll durchgereicht werden kann |
| `preview` | `none` / `text` / `diff` / `transfer` |
| `verify` | `none` / `self-reported` / `observable` |
| `health` | **passive**, seiteneffekt- und kostenfreie Prüfung |
| `audit` | Metadaten-Allowlist für `obslog` (nie Inhalte) |
| `fixture` | Testfixture für den Vertrag |
| `execute` | Ausführung (bei Legacy-Actions: die bestehende `ActionSpec.execute`) |

**Abgeleitet, nicht deklarierbar:**

```
tier(contract) = TRIVIAL, wenn effects ⊆ {read-local, network-read}
                          und writes = ∅
                          und reads  ⊆ {public, local}
                 sonst GOVERNED
```

Niemand kann `tier="trivial"` schreiben. Eine Capability wird billig, indem sie billig
**ist**.

---

## 10. Lifecycle

```
validate → preview → authorize → execute → verify
```

Keine Stufe ist überspringbar. `execute` wird nur für eine `Decision` erreicht, die für
**diesen** Versuch berechnet wurde; verlangt der Vertrag eine Vorschau, zusätzlich nur für
**diesen** Preview-Hash. `verify` läuft **immer** — auch wenn `execute` geworfen hat; genau
dadurch ist Teilerfolg beobachtbar. Sagt der Vertrag `verify="none"`, wird **dieser Umstand
protokolliert**, statt Erfolg zu behaupten.

Für eine `TRIVIAL`-Capability liefert der Kernel `Allow` mit **leerer** Anforderungsmenge.
Der triviale Pfad überspringt die Policy nicht — er besteht sie mit nichts zu tun.

---

## 11. Cancel, Timeout, Teilerfolg, Kompensation

- **Cancel:** `asyncio.CancelledError` wird **unverändert weitergereicht**. Der Coordinator
  hält keinen Task, keine Queue, kein Lock; `ConversationSession` behält Turn-, Queue- und
  Cancel-Besitz (RFC-0006). Kein `finally` darf den Abbruch schlucken.
- **Timeout:** je Vertrag; erzeugt den Ausgang `timeout`, keine Exception.
- **Teilerfolg:** eigener Ausgang `partial` mit den Feldern „vollzogen" und „ausstehend".
  Er ist **kein** Fehler und wird nicht zu Erfolg aufgerundet. `verify` darf `ok` zu
  `partial` herabstufen, nie umgekehrt.
- **Kompensation:** in Phase 5 **nicht** vorhanden. Der Vertrag benennt, ob eine Wirkung
  umkehrbar wäre; eine Kompensations-Engine ist Phase 6.

**Geschlossenes Ergebnismodell.** `attempt` gibt genau einen Ausgang zurück:
`ok`, `partial`, `denied`, `needs`, `timeout`, `cancelled`, `failed`.
Domänenablehnungen sind **Ergebnisse, keine Exceptions**. Geworfen wird nur bei
`CancelledError`, unbekannter Capability und Schemaverletzung — alle drei sind
Programmierfehler des Adapters.

---

## 12. Policy-Modell

```
decide(contract, request, evidence, rules) -> Decision
```

Rein, deterministisch, total, I/O-frei, wirft nie aus Domänengründen — strukturell
derselbe Modultyp wie `conversation/_core.py`.

- **Deny-by-default:** `allow` nur, wenn keine Regel `deny` oder `needs` liefert.
- **Reihenfolgeunabhängig:** `deny` gewinnt, `needs` akkumuliert. Damit ist die
  Regelmenge eine Tabelle und die gesamte Sicherheitslage ein Tabellentest.
- **Aktive Regeln in Phase 5** (D6 — nur was erfüllbar ist):
  1. Provenance-Regel (SI-1): untrusted Inhalt erhöht nie Wirkungsklasse, Scope,
     Presence oder Autorisierung.
  2. Confirm-Regel: `destructive` verlangt Confirmation (heute `MEMORY_FORGET`).
  3. SSRF-Zielregel: `network-read` verlangt ein zulässiges Ziel.
- **Datiert, nicht aktiv:** `presence:unlocked` für `read-sensitive` (Phase 9, braucht
  Win32-Erkennung); `preview` für Screen/Clipboard (Phase 9, braucht die Vorschau-UI);
  Budget-/Hintergrundregeln (Phase 6); Connector-Principal (Phase 10).

Fail-closed gilt **vollumfänglich für jede aktive Regel**. `unknown` als „erlaubt"
durchzuwinken ist ausdrücklich abgelehnt (D6): das wäre fail-open unter fail-closed-Namen.

---

## 13. Taxonomie

**Wirkungsklassen (7)** — unverändert aus `SECURITY_REQUIREMENTS.md` §3 übernommen:
`read-local`, `read-sensitive`, `network-read`, `local-write`, `local-execute`,
`external-write`, `destructive`.

**Datenklassen (5)** — unverändert aus §2: `public`, `local`, `personal`, `sensitive`,
`secret`. `secret` ist strukturell nicht als Capability-Eingabe oder -Ausgabe darstellbar
(SI-5).

**Scopes** sind Ressourcenbereiche (`vault`, `config.launcher`, `web`, `screen`,
`clipboard`, `apps`) und **nicht** dasselbe wie Wirkungsklassen: die Klasse sagt *was*,
der Scope sagt *woran*.

---

## 14. Provenance und Bindung an den Nutzerwillen

`Provenance` ist zweiwertig: `operator` oder `derived`. Alles, was aus Web, Vault,
Clipboard, Screen, Recherche, Verlauf oder LLM-Ausgabe stammt, ist `derived`.

- Provenance kann eine Anforderung **nur hinzufügen, nie entfernen**. Der Kernel hat keinen
  Zweig, in dem `derived` etwas erlaubt, das `operator` nicht erlaubt.
- Provenance ist **request-scoped**: sie wird beim Erzeugen der Anfrage gesetzt und
  nirgends persistiert. Das bestehende Message-Format bleibt unverändert.
- Modell-generierte Felder können **keine** Freigabe liefern. Ein `[ACTION:…]`, das aus
  einer LLM-Antwort stammt, ist immer `derived` — auch wenn der Nutzer es wörtlich so
  gesagt hat, denn zwischen Nutzer und Tag liegt das Modell.

---

## 15. Presence Evidence

`unknown` / `unlocked` / `locked` / `remote`. **`unknown` ist der Default und der
Nullwert.** Fehlende Evidenz ist nie „wahrscheinlich entsperrt".

In Phase 5 liefert nichts eine andere Aussage als `unknown` — echte Windows-Lock-/
RDP-Erkennung ist Phase 9. Deshalb ist keine Presence-Regel aktiv (D6). Ausdrücklich
festgehalten: Audio-`UserGesture`, WS-Verbindung, Session-Token, Voice State und UI-Token
sind **keine** belastbare OS-Presence und dürfen nie als solche verwendet werden.

---

## 16. Preview, Hash, Grant — und die Abgrenzung zur Confirmation

**Preview** ist die vor der Wirkung gezeigte, kanonisch serialisierte Beschreibung dessen,
was passieren wird. Ihr **kanonischer Hash** bindet eine Freigabe an genau diese Wirkung.

**Authorization Grant** (Vertrag, in Phase 5 **nicht implementiert** — D5):

- gebunden an: Preview-Hash, Principal `local-ui`, TTL, **Single-Use**;
- **fail-closed invalidiert** durch: Stop, Disconnect, neue Nachricht, Ablauf, Reconnect;
- **Voice kann einen Grant nie erfüllen** (SI-2);
- Replay eines verbrauchten oder abgelaufenen Grants wird abgelehnt;
- ändert sich zwischen Freigabe und Ausführung der Preview-Hash (TOCTOU), wird abgelehnt.

**Abgrenzung, verbindlich:**

| | Confirmation | Authorization Grant |
|---|---|---|
| Kanal | gesprochen (Voice) | lokale UI |
| Beweist | Absicht | Absicht **und** Principal |
| Bindung | an den laufenden Turn | an Preview-Hash + TTL + Single-Use |
| Erfüllt | `needs:confirmation` | `needs:authorization` |
| Heute vorhanden | ja (`MEMORY_FORGET`) | nein |

**`MEMORY_FORGET` bleibt Confirmation.** Es wird durch dieses RFC **nicht** zu einem Grant
umetikettiert; die Capability behält exakt das heutige beobachtbare Verhalten.

---

## 17. Conversation- und Runtime-Integration

- Die `Runtime` besitzt Registry, Regeln und Coordinator.
- `ConversationSession` behält Queue, aktiven Turn, Cancellation und die offene Rückfrage.
  Der Coordinator besitzt **nichts** davon.
- Ein Capability Attempt läuft **innerhalb** eines Turns. Stop cancelt den Turn, und die
  `CancelledError` erreicht den Attempt unverändert.
- Ein `needs:confirmation` wird über den **bestehenden** Pfad
  (`ctx.request_confirmation` → Session-`suspended`) gestellt — kein neuer Session-Zustand,
  kein RFC-0006-Amendment (D5).
- Disconnect schließt die Session; laufende Attempts werden mitgenommen (kein Task-Leak).

---

## 18. V1-, Legacy- und Frontend-Strategie

**Phase 5 ändert die Leitung nicht** (D9). `Outcome` wird in den Adaptern abgebildet:

| Ausgang | Bestehende Form |
|---|---|
| `ok` | `response`-Frame bzw. bestehende REST-Antwort |
| `needs` (confirmation) | bestehender gesprochener Rückfrage-Pfad |
| `denied` | vorhandener `error`-Frame bzw. REST-Fehlerform |
| `timeout`, `failed` | vorhandener `error`-Frame |
| `partial` | tritt bei keinem der vier Piloten auf |

Legacy bleibt damit byte- und shape-exakt; das Frontend bleibt unverändert. Die additiven
V1-Formen für `Outcome` und `Decision` werden hier **spezifiziert**, aber erst gebaut, wenn
ein zweiter Leser existiert. RFC-0005 bleibt unverändert; **kein Amendment nötig**.

Ausdrücklich: `event_id` ist kein Idempotency Key, `correlation_id` keine Job-ID,
`session_id` keine Autorisierung.

---

## 19. Idempotency und Retry — mit klaren Grenzen

- **Eigener Schlüssel**, abgeleitet aus `(name, version, kanonisierte Eingabe, Dedupe-Scope)`.
  Wire-IDs sind als Parameter **nicht annehmbar** und können ihn nicht erreichen.
- **Nur flüchtig:** Gültigkeit höchstens für Runtime beziehungsweise Session. Kein
  crash-dauerhaftes Deduplizieren. **Exactly-once wird ausdrücklich nicht behauptet.**
- **Retry ist deklarative Eignung**, keine Engine. Der Vertrag sagt, ob ein Wiederholen
  überhaupt zulässig wäre; ob wiederholt wird, entscheidet der Aufrufer. Damit kein
  Adapter eigene Retry-Schleifen wachsen lässt, gilt: **eine Retry-Schleife im Adapter ist
  ein Fehler**, solange es keine Engine gibt (Phase 6).

---

## 20. Health, Verify, Audit

- **Health** ist passiv, seiteneffektfrei und verursacht **keine Providerkosten**. Er liest
  Registry und `decide` — mehr nicht. `/health` bleibt damit so kostenlos wie heute.
- **Verify** liefert beobachtbare Evidenz. `verify="none"` wird als solches vermerkt,
  statt Erfolg zu behaupten.
- **Audit** sind Metadaten über `obslog.event` mit geschlossener Feld-Allowlist (RFC-0004):
  Name, Version, Wirkungsklassen, Ausgang, Dauer, Korrelation. **Nie** Inhalte, nie
  Payloads. Preview-Hashes werden **nicht** geloggt, wenn sie über einem kleinen Raum
  raten lassen. **Kein dauerhafter Audit-Store vor Phase 11.**

---

## 21. SSRF-Vertrag

**Policy deklariert, Transport erzwingt** (D7). Eine Prüfung allein in der Policy-Schicht
wäre wirkungslos: Redirects und die DNS-Auflösung passieren darunter.

- Nur `http`/`https`.
- Bei **jeder** Verbindung und **jedem** Redirect-Hop wird die **tatsächlich aufgelöste IP**
  geprüft.
- Denylist (freies Browsen ist der Zweck, daher keine Allowlist): Loopback `127.0.0.0/8`
  und `::1`, RFC1918 `10/8` `172.16/12` `192.168/16`, Link-local `169.254/16` und
  `fe80::/10`, ULA `fc00::/7`, Cloud-Metadata `169.254.169.254`.
- **Selbstzugriff auf `127.0.0.1:8340` wird hart blockiert.**
- Kurze Timeouts; Redirect-Ketten begrenzt.
- **Benanntes Restrisiko:** vollständiger DNS-Rebinding-Schutz verlangt IP-Pinning
  (geprüfte IP verbinden, Host-Header erhalten). Das ist **datiert vertagt**, weil es eine
  eigene Verbindungsschicht braucht und TLS-SNI sowie CDN-Round-Robin brechen kann. Die
  Prüfung pro Verbindung erschwert Rebinding erheblich, schließt es aber nicht.

---

## 22. `[ACTION]`-Adapter und strukturierte Tool Calls

**`[ACTION:…]` bleibt ein unterstützter Legacy-Adapter.** RFC-0001 bleibt bindend:
`Action` und `ActionSpec` werden nicht entfernt und nicht umbenannt. `_legacy.py` bildet
`ActionSpec.type` auf den Capability-Namen ab; die Prompt-Selbstbeschreibung
(`describe`) bleibt, wo sie ist.

`ActionSpec.risk` wird zur **abgeleiteten Projektion** aus dem Vertrag (D10) — genau eine
Quelle, ein Widerspruch ist nicht darstellbar.

**Strukturierte Provider-Tool-Calls sind ausdrücklich KEINE Pflicht für Prompt 19.** Sie
wären ein **dritter Adapter** vor demselben Core und ändern an Core, Kernel und Coordinator
nichts. Die Entscheidung wird vertagt (§29), weil sie eine eigene Abwägung zu Kosten,
Modellbindung und Prompt-Verträgen verlangt, die in dieses RFC nicht gehört.

---

## 23. Test-Seams für Prompt 19

| Seam | Ebene | Was geprüft wird | Was Grenze ist |
|---|---|---|---|
| `SEAM-POLICY` | Contract (rein) | `decide` als **Tabellentest** über Vertrag × Anfrage × Evidenz | nichts — rein |
| `SEAM-CAPABILITY` | Contract (rein) | Registry-Bau, Schemavalidierung, abgeleiteter `tier()`, **Wirkungs-Zensus** | nichts — rein |
| `SEAM-CAPABILITY-COORDINATION` | Integration | Lifecycle-Reihenfolge, Nicht-Überspringbarkeit, Ausgänge, Cancel-Durchreichung, Idempotency | Fake-Verträge |
| SSRF-Transport | Integration | Denylist je Hop, Redirect-Revalidierung, Selbstzugriff blockiert | Test-Transport, **kein echtes Netz** |
| bestehende Seams | — | `SEAM-CONVERSATION`, `SEAM-WS`, `SEAM-REST` bleiben unverändert gültig | — |

**Der Wirkungs-Zensus** ist die Absicherung gegen Fehldeklaration: ein Test nagelt für jede
Capability die deklarierten Wirkungsklassen gegen eine überprüfte Liste fest. Eine
Herabstufung erscheint dann als fehlschlagender Test im Diff, nicht als stille Feldänderung.
Vorbild im Repo: `tests/test_action_deep_module.py:778` (`len(actions.REGISTRY) == 22`).

---

## 24. Migrationsslices, Piloten, Deletion Gates

Vertikal, einzeln rückrollbar, jeder Slice endet grün.

| Slice | Inhalt | Rückrollbar durch |
|---|---|---|
| 1 | `capability/_contract.py` + `_policy.py` (rein, ohne Aufrufer) + Tabellentests | Paket entfernen |
| 2 | Coordinator + `inspect`/`attempt`, noch ohne Produktionsaufrufer | Commit revert |
| 3 | Pilot `SEARCH` über den Legacy-Adapter | Adapter zurück auf direkten Aufruf |
| 4 | SSRF-Transport + Denylist, verdrahtet an `network-read` | Transport zurücktauschen |
| 5 | Pilot `MEMORY_FORGET` (Confirmation-Pfad unverändert) | wie 3 |
| 6 | Pilot `launcher.profile.delete` (REST-Adapter) | Route zurück auf direkten Aufruf |
| 7 | Pilot `context.refresh` (Startup + Settings-Save) | wie 6 |
| 8 | Restliche 21 Actions in Gruppen | je Gruppe |
| 9 | Restliche 9 REST-Routen | je Route |
| 10 | `risk` auf abgeleitete Projektion umstellen | Feld zurückholen |
| 11 | Doku, `CAPABILITY_MATRIX`, `TEST_SEAMS`, CI | Commit revert |

**Deletion Gates** — was wann verschwinden darf:

| Was | Gate |
|---|---|
| Gespeichertes `ActionSpec.risk` | **alle 22** Actions migriert **und** Suite grün (D10) |
| Direkter `spec.execute()`-Aufruf im Legacy-Pfad | Pilot-Slices grün, Frames byte-gleich |
| Direkte Wirkung in den 10 REST-Routen | jeweilige Route migriert, REST-Vertrag unverändert |
| `follow_redirects=True` ohne Prüfung | SSRF-Transport aktiv und getestet |

**Nichts wird gelöscht, bevor der Ersatz die gleiche Abdeckung nachweist.**

---

## 25. Risiken

| # | Risiko | Gegenmittel |
|---|---|---|
| R1 | **Halb migrierter Zustand**: manche Wirkungen geprüft, andere nicht, von außen ununterscheidbar | Vertikale Slices; jeder Slice ist ein vollständiger Pfad; `inspect()` macht den Zustand abfragbar |
| R2 | **Unter-Deklaration**: jemand deklariert Destruktives als `read-local` | Pflichtfelder ohne Defaults, abgeleiteter `tier()`, **Wirkungs-Zensus-Test** |
| R3 | **Scheinsicherheit**: Klassifikation ohne aktive Regel wird für Schutz gehalten | Regeln, die nicht erfüllbar sind, werden **datiert und nicht aktiviert** (D6); das RFC benennt sie |
| R4 | **Doppelwahrheit** `risk` vs. Vertrag | D10: Projektion statt zweiter Speicher |
| R5 | **Native Lücke** wird vergessen | D3: namentlich benannt, Regel „kein neuer nativer Pfad ohne Kernel" |
| R6 | **Verhaltensänderung** bei `SCREEN`/`CLIPBOARD` (werden `GOVERNED`) | In Phase 5 folgt daraus keine aktive Anforderung (D6); die Änderung wird sichtbar, wenn Phase 9 die Vorschau bringt |
| R7 | **DNS-Rebinding** bleibt möglich | benanntes, datiertes Restrisiko (D7) — nicht als gelöst dargestellt |
| R8 | Erweiterungspunkte ohne Nutzer | `attributes`/`with_rules` bewusst **nicht** aufgenommen (D2) |

---

## 26. Rollback

Jeder Slice ist ein eigener Commit und einzeln revertierbar. Bis Slice 10 existiert der
alte Pfad unverändert daneben; ein Rollback stellt ihn ohne Datenmigration wieder her.
Es gibt keinen Zustand, in dem ein Rückbau eine Konfiguration oder einen Vault
zurücklassen würde, den der alte Code nicht lesen kann — der Kernel schreibt nichts
Eigenes und persistiert nichts.

---

## 27. Phasengrenzen

| Phase | Was dort passiert |
|---|---|
| **5 (Prompt 19)** | Core, Kernel, Coordinator, vier Piloten, SSRF-Transport, drei aktive Regeln |
| **6** | Job-Engine, Persistenz, Resume, Retry-Engine, Kompensation, Budgets |
| **9** | Win32-Presence, Screen-/Clipboard-Vorschau-UI, Panic Lock — damit werden die datierten Regeln aktiv |
| **10** | Connectoren, erste `external-write`-Capability — damit bekommt der Grant-Vertrag seine Laufzeit |
| **11** | Audit-Store, durchgehende Korrelation |

---

## 28. Akzeptanzkriterien für Prompt 19

1. `capability/_policy.py` ist **rein** — der Nachweis erfolgt verhaltensbasiert in einer
   Sandbox, in der DOM/Netz/Datei/Zeit werfen (Muster aus dem Voice-Contract von Phase 4J).
2. `decide` ist als Tabelle getestet; jede aktive Regel hat mindestens einen
   Erlaubnis- und einen Ablehnungsfall.
3. Der **Wirkungs-Zensus** ist grün und schlägt bei jeder Herabstufung fehl
   (Rot-Grün nachgewiesen, nicht behauptet).
4. Die vier Piloten laufen über den Kernel; **beobachtbares Verhalten unverändert**,
   Frames byte-gleich, Visual-Regression ohne Baseline-Update grün.
5. `MEMORY_FORGET` verhält sich exakt wie heute (Confirmation, kein Grant).
6. SSRF: Selbstzugriff auf `127.0.0.1:8340` und ein Redirect auf Loopback werden
   **nachweislich** blockiert, ohne echtes Netz.
7. Kein neues Modul-Global; `Runtime` besitzt den Coordinator.
8. `CancelledError` erreicht einen laufenden Attempt unverändert — mit Test.
9. Keine Persistenz, kein Job, kein Scheduler, kein Wire-Typ hinzugekommen.
10. Vollständige lokale Gates plus beide Hosted-Gates auf dem exakten finalen SHA.

---

## 29. Ausdrücklich vertagte Entscheidungen

| Thema | Warum vertagt | Frühestens |
|---|---|---|
| **Strukturierte Provider-Tool-Calls** | Eigene Abwägung zu Kosten, Modellbindung und Prompt-Vertrag; ändert an Core/Kernel/Coordinator nichts (dritter Adapter) | eigene Entscheidung |
| **IP-Pinning gegen DNS-Rebinding** | Eigene Verbindungsschicht; Risiko für TLS-SNI und CDN | Phase 9 |
| **Presence-Runtime** | Braucht Win32-Session-APIs | Phase 9 |
| **Grant-Laufzeit** | Null Nutzer, solange `external-write` leer ist | Phase 10 |
| **Preview-UI für Screen/Clipboard** | UI-Arbeit, ausdrückliches Nicht-Ziel | Phase 9 |
| **Audit-Store, durchgehende Korrelation** | Braucht Speicher- und Aufbewahrungsentscheidung | Phase 11 |
| **Rate-/Budget-Grenzen** | Gehören zur Job-Engine | Phase 6 |
| **Push-to-Talk-Pflicht** | Nutzerentscheidung, offen seit Phase 2 | offen |
| **`/docs`, `/redoc`, `/openapi.json` ohne Token** | Beim Inventar aufgefallen, kein Capability-/Policy-Thema; lokal gebunden, aber Informationsquelle über alle wirkenden Routen (Klasse TM-003) | eigene Entscheidung |

---

# Amendment 1 — Pilotphase, Wirkungsinventar, SSRF-Durchsetzung und Lifecycle-Grenzen

- **Datum:** 2026-07-19
- **Anlass:** Prompt 19 (Phase 5B) — verpflichtendes Amendment-Gate vor der Umsetzung
- **Basis:** `origin/master` `f03e4d63a220e8acd22b24ef3076a828993f7356`;
  Post-Merge-Hosted-Run **29683333214** (`workflow_dispatch`, Fast-Job `88183275932` und
  Browser-Job `88183275901` beide `success`)
- **Status:** vom Nutzer ausdrücklich angenommen (Beschlusspunkte A–G, 2026-07-19)

> **Was sich NICHT ändert:** Die Architekturentscheidungen **D1–D6, D8 und D10** bleiben
> unverändert. Variante C (Core + Kernel + Coordinator), das Hybrid-Interface, der
> Grenzvertrag für native Pfade, die Effekt-Zuordnung an die auslösende Capability, „Grant
> nur Vertrag, keine Laufzeit", „nur erfüllbare Regeln aktivieren" und „der Vertrag ist die
> Wahrheit" gelten fort. **D7** (SSRF-Durchsetzungspunkt) und **D9** (Wire-Vertrag) werden
> **präzisiert, nicht umgestoßen**. Es entsteht keine neue Wire-Form; RFC-0005 und RFC-0006
> bleiben unverändert.

## A1.0 Warum dieses Amendment nötig wurde

Ein Abgleich des akzeptierten RFC mit dem Code auf dem Basis-SHA fand sechs Stellen, an
denen das Dokument entweder sich selbst oder dem Code widerspricht. Alle sechs sind am
Code verifiziert, nicht geschätzt. Sie still als Implementierungsdetail zu lösen, hätte
in drei Fällen zu **Scheinsicherheit** geführt — dem Fehlermodus, den dieses RFC
ausdrücklich vermeiden will (R3).

| # | Befund | Beleg |
|---|---|---|
| 1 | §24 listet elf Slices **bis zur Vollmigration**; §27/§28 begrenzen Prompt 19 auf Core, Kernel, Coordinator, vier Piloten und SSRF | §24 vs. §27/§28 |
| 2 | §24 Slice 8 sagt „restliche **21** Actions"; nach zwei Piloten bleiben **20** | `len(actions.REGISTRY) == 22` |
| 3 | §2.4 nennt „Summary-LLM bei **8** Actions" (die mit gesetztem `summary_task`); der Code triggert die Stufe über `not speaks_result` ∧ `!= OPEN` — das sind **15** | `assistant_core.py:341,345,358` + `:240` (Fallback auf `DEFAULT_SUMMARY_TASK`) |
| 4 | D7 nennt nur eine `httpx`-Transportschicht; die produktiven Browserpfade sind **primär Playwright** | `browser_tools.py:94,335,351` ohne httpx-Weg; httpx nur `:176`/`:267` |
| 5 | `launcher.profile.delete` ist serverseitig **nicht** bestätigbar — der Zwei-Klick-Dialog ist browserlokal | `server.py:832-846`; `frontend/main.js:1049,1793-1803` |
| 6 | Provenance-Wirkung, Timeout-Verantwortung, Cancel-vs-Verify und Idempotency-Semantik sind nicht testscharf; §10 und §11 widersprechen sich offen | §10 „verify läuft immer" vs. §11 „CancelledError unverändert" |

## A1.1 (A) Prompt-19-Scope — Pilotphase, nicht Vollmigration

**Beschluss.** Prompt 19 implementiert die **Pilotphase**: Capability Core, reiner Policy
Kernel, runtime-eigener Coordinator, SSRF-`TargetGuard` mit zwei Transportadaptern und
**vier repräsentative Produktionspfade**.

Die Vollmigration der verbleibenden **20** Actions, der neun REST-Routen und die
Entfernung des **gespeicherten** `ActionSpec.risk` folgen in **Prompt 20**.

> **Korrigiert durch Amendment 2 (§A2.1).** „Neun REST-Routen" ist mit §A1.4 unvereinbar,
> das `launcher.profile.delete` bis Phase 10 unverändert lässt. Migrierbar sind **acht**;
> zusammen mit dem bereits migrierten Rename sind danach **9 von 10** Routen geschützt.

**§24 wird entsprechend harmonisiert.** Die Slice-Tabelle gilt fort, ihre Zuordnung zu den
Prompts lautet nun:

| Slice (§24) | Prompt | Anmerkung |
|---|---|---|
| 1–7 | **19** | Core, Kernel, Coordinator, vier Piloten, SSRF |
| 8 | 20 | **20** (nicht 21) restliche Actions in Gruppen |
| 9 | 20 | restliche neun REST-Routen |
| 10 | 20 | `risk` auf abgeleitete Projektion umstellen — Deletion Gate aus D10 unverändert |
| 11 | 19 **und** 20 | Doku/CI je Phase, nicht erst am Ende |

**§27 und §28 gelten unverändert als Beschreibung der Pilotphase.** Ergänzend gilt:
**Prompt 19 darf nicht als vollständiges Phase-5-Gate bezeichnet werden.** Phase 5 ist
erst mit Prompt 20 abgeschlossen. Jede Abschlussmeldung aus Prompt 19 muss die vier
migrierten Pfade, die 20 offenen Actions und die neun offenen REST-Routen benennen.

## A1.2 (B) Wirkungsinventar — die Summary-LLM-Stufe trifft 15 Actions

**Befund.** §2.4 zählte die Actions mit gesetztem `summary_task`. Das ist die
**Aufgabenbeschreibung**, nicht der **Auslöser**. Der Auslöser steht in der
Orchestrierung:

```
assistant_core.py:341   if action.type == "OPEN": return          # Frühabbruch
assistant_core.py:345   if action.type in actions.SPEAK_RESULT_ACTIONS: ...  # kein Summary
assistant_core.py:358   summary_resp = await ai.messages.create(...)          # sonst: Summary-LLM
assistant_core.py:240   task = spec.summary_task or actions.DEFAULT_SUMMARY_TASK
```

22 Actions − 6 mit `speaks_result` − 1 (`OPEN`) = **15**.

**Beschluss.** Die Angabe wird korrigiert und durch einen **Characterization-Test** gegen
den tatsächlichen Bestand abgesichert, statt durch eine Zahl im Dokument. Die 15 Actions:

`SEARCH`, `BROWSE`, `SCREEN`, `NEWS`, `INBOX_READ`, `INBOX_WRITE`, `MEMORY_WRITE`,
`MEMORY_READ`, `MEMORY_FORGET`, `RESEARCH`, `CLIPBOARD`, `CLIPBOARD_NOTE`, `NOTES_RECENT`,
`PROJECT_CONTEXT`, `SESSION_SUMMARY`.

**Folgeeffekte gehören in den Vertrag der auslösenden Capability** (bekräftigt D4):
Summary-LLM, TTS, sichtbarer Chromium-Prozess, PowerShell-`SetForegroundWindow`-Fokus und
Recherche-Autosave. Eine Capability, die eine dieser Wirkungen auslöst, deklariert sie —
auch wenn sie außerhalb ihrer `execute`-Funktion passiert.

## A1.3 (C) SSRF — ein reiner TargetGuard, zwei Produktionsadapter

**Befund.** D7 nannte eine `httpx`-Transportschicht. Der produktive Hauptpfad ist aber
Playwright:

| Funktion | Aufrufende Action | Primärpfad | httpx-Fallback |
|---|---|---|---|
| `search_and_read` (`:88`) | **`SEARCH`** (Pilot) | `page.goto` `:94` **+ Klick auf das erste Ergebnis** | **keiner** |
| `fetch_news` (`:331`) | `NEWS` | `page.goto` `:335` | keiner |
| `open_url` (`:348`) | `OPEN` | `page.goto` `:351` | keiner |
| `visit` (`:292`) | `BROWSE` | `page.goto` `:305` | `:267`, `follow_redirects=True` `:270` |
| `search_links` (`:191`) | `RESEARCH` | `page.goto` `:203` | `:176`, `follow_redirects=True` `:179` |

Ein reiner httpx-Schutz würde **ausgerechnet den Piloten `web.search` vollständig
verfehlen** — und damit Sicherheit vortäuschen, wo keine ist.

**Beschluss.** Ein **gemeinsamer reiner `TargetGuard`** (I/O-frei, mit injiziertem
Resolver) wird durch **zwei** Produktionsadapter erzwungen:

1. **httpx-Adapter** — Prüfung aller aufgelösten Adressen **vor jedem Request** und **vor
   jedem manuell behandelten Redirect-Hop**. Kein unkontrolliertes
   `follow_redirects=True`; die Kette wird selbst gefahren und je Hop revalidiert.
2. **Playwright-Adapter** — Prüfung **vor jeder Navigation** und **vor jedem Redirect-/
   Navigation-Request**. Alle aufgelösten Adressen eines Ziels müssen zulässig sein. Wo
   Playwright die Remote-Adresse offenlegt, wird sie **zusätzlich** geprüft und bei
   Abweichung abgebrochen.

Damit sind es **zwei Adapter an einem Seam** — nach der Regel aus `DEEPENING.md` ein
echter Seam, kein hypothetischer.

**Denylist (unverändert aus §21).** Loopback `127.0.0.0/8` und `::1`, RFC1918 `10/8`
`172.16/12` `192.168/16`, Link-local `169.254/16` und `fe80::/10`, ULA `fc00::/7`,
Cloud-Metadata `169.254.169.254`, sowie der **harte Selbstzugriffsblock auf
`127.0.0.1:8340`**. Nur `http`/`https`. Kurze Timeouts, begrenzte Redirect-Kette.

**Ehrlichkeitsklausel.** Ohne IP-Pinning wird **nicht** behauptet, die tatsächlich
verbundene IP zu binden. **DNS-Rebinding bleibt ausdrücklich als Restrisiko bestehen**
(R7 unverändert), und **TM-002 wird höchstens als „teilweise mitigiert" bezeichnet** —
nie als behoben.

**Abbruchbedingung.** Lässt sich der produktive Playwright-Hauptpfad nicht belegbar
schützen, wird die Umsetzung mit `PROMPT 19 BLOCKIERT – PLAYWRIGHT-SSRF-SEAM NICHT
BELEGBAR` gestoppt. Dann wird **keine** TM-002-Mitigation behauptet.

## A1.4 (D) REST-Pilot — `launcher.profile.rename` statt `launcher.profile.delete`

**Befund.** `DELETE /launcher/profiles/{id}` (`server.py:832-846`) prüft Token, Existenz
und Intent-Guards — und löscht dann. Der Zwei-Klick-Dialog existiert **ausschließlich im
Browser** (`profileDeleteMode`, `frontend/main.js:1049`, `:1793-1803`): der erste Klick
schaltet den Löschmodus scharf, der zweite Klick auf einen Profil-Tab sendet das `DELETE`.

**Der Server sieht genau einen `DELETE`-Request** — nicht unterscheidbar von einem
direkten Aufruf mit gültigem Token. Er hat keine Evidenz über den vorausgegangenen
Dialog. Da **D5** die Grant-Laufzeit und **D9** neue REST-/Wire-Formen ausschließt, gibt
es in Prompt 19 **keinen ehrlichen Weg**, hier ein `needs:confirmation` zu erfüllen.

**Beschluss.**

- Der REST-Pilot ist **`launcher.profile.rename`** (`server.py:812-829`). Er hat dieselbe
  Adapterform (Token, Body, Namensvalidierung, 404, `_persist_launcher` mit
  `configuration`-Intent, `obslog`-Event, `_profiles_response`), ist aber `local-write`
  statt `destructive` und beweist den REST-Adapter **ohne** neue UI, Wire-Form oder
  Grant-Runtime.
- **`launcher.profile.delete` bleibt unverändert** und wird als **bekannte destructive
  Lücke** dokumentiert. Migriert wird sie erst mit einem **serverseitig nachweisbaren
  Preview-/Grant-Vertrag** (Phase 10, D5).
- **Ein direkter `DELETE` darf nicht als „Confirmation" umetikettiert werden.** Das wäre
  fail-open unter fail-closed-Namen — genau die Umetikettierung, die §16 für
  `MEMORY_FORGET` in die Gegenrichtung verbietet.

Die in §2.6.2 belegte Asymmetrie — ein Gedächtniseintrag verlangt eine Rückfrage, ein
ganzes Profil nicht — **bleibt damit bestehen und wird ehrlich als offen ausgewiesen**,
statt durch eine Scheinabsicherung verdeckt zu werden.

## A1.5 (E) Provenance — Präzisierung von §14

**Beschluss.**

1. **Wirkungen, Scopes und Tier stammen ausschließlich aus der eingefrorenen Registry.**
   Adapter, LLM-Ausgaben und Nutzdaten können sie weder setzen noch abschwächen. Eine
   Anfrage trägt Provenance und Eingabe — sonst nichts, was die Policy beeinflusst.
2. **`derived` liefert niemals Confirmation, Presence oder Authorization.** Es gibt im
   Kernel keinen Zweig, in dem eine dieser Anforderungen durch Provenance erfüllt wird.
3. **`derived` darf eine bestehende Anforderung nur beibehalten oder verschärfen** — nie
   entfernen und nie abschwächen.
4. **`web.search` läuft mit sicherem Ziel weiter.** Die Provenance-Regel erzeugt für
   `network-read` **keine** zusätzliche Anforderung; andernfalls würde jede Sprachsuche
   bestätigungspflichtig, was das beobachtbare Verhalten ändern würde (§28.4).
5. **`memory.forget` liefert im ersten Attempt `needs:confirmation`.** Erfüllt wird diese
   Anforderung **ausschließlich** durch die nachfolgende echte Operator-Bestätigung
   **desselben offenen Conversation-Turns** über den bestehenden Pfad
   (`ctx.request_confirmation` → Session `awaiting-confirmation`, RFC-0006 §11).

## A1.6 (F) Lifecycle-Grenzen — Auflösung des Widerspruchs zwischen §10 und §11

**Befund.** §10 sagt „`verify` läuft **immer** — auch wenn `execute` geworfen hat". §11
sagt „`asyncio.CancelledError` wird **unverändert weitergereicht**; kein `finally` darf
den Abbruch schlucken". Beides zugleich ist nicht implementierbar: ein Verify nach einer
`CancelledError` verzögert oder verschluckt den Abbruch.

**Beschluss.**

1. **Timeout.** Der Coordinator ist für migrierte Pfade der **alleinige** Timeout-Owner.
   **Kein doppeltes `asyncio.wait_for`.** Heute liegt der einzige Timeout in
   `assistant_core.py:324-325`; für einen migrierten Pfad geht diese Verantwortung an den
   Coordinator über, statt sich zu addieren.
2. **Cancellation.** `asyncio.CancelledError` wird **sofort und unverändert**
   weitergereicht. **Cancellation ist die ausdrückliche Ausnahme von „verify läuft
   immer"** — nach einer `CancelledError` läuft **kein** Verify. §10 gilt damit für alle
   Ausgänge des geschlossenen Ergebnismodells, nicht für den Abbruch.
3. **Abgrenzung `cancelled`.** Der Ausgang `cancelled` bezeichnet **nur** eine vom
   Executor **normal gemeldete kooperative Domänenstornierung**. Eine propagierte
   `CancelledError` erzeugt **kein** `Outcome` — sie verlässt den Coordinator als
   Exception (unverändert §11: geworfen wird nur bei `CancelledError`, unbekannter
   Capability und Schemaverletzung).
4. **Idempotency.** Der Schlüssel wird **deterministisch** aus `(Capability-Name,
   Version, kanonisierte Eingabe, lokaler Dedupe-Scope)` erzeugt und **an die Ausführung
   übergeben**. **Prompt 19 baut keinen Ergebnis-Cache, keine automatische
   Deduplizierung und keine Retry-Schleife** — das folgt frühestens mit Phase 6. Der
   Schlüssel ist in Prompt 19 also ein *übergebener Wert*, kein *wirksamer Mechanismus*.
5. **Audit.** Es werden **ausschließlich** Metadaten aus der Allowlist emittiert: Name,
   Version, Wirkungsklassen, Ausgang, Dauer. **Keine** Payloads, Inhalte, URLs,
   Preview-Hashes oder Secrets. **Keine neue durchgehende Korrelation vor Phase 11**
   (unverändert §20).

## A1.7 (G) Identitäten und Test-Seams

1. **`SEARCH` erhält den stabilen Capability-Namen `web.search`, Version 1.**
2. Die konkreten **typisierten Ein- und Ausgaben der vier Piloten** werden **vor dem
   Einfrieren** durch Characterization-Tests gegen das heutige Verhalten festgelegt —
   nicht aus dem Dokument abgeleitet.
3. Folgende Seams sind mit diesem Amendment **bestätigt**:
   `SEAM-CAPABILITY`, `SEAM-POLICY`, `SEAM-CAPABILITY-COORDINATION`,
   `SSRF-Transport/TargetGuard`.
4. Ihr Status in `docs/quality/TEST_SEAMS.md` wechselt **erst nach vorhandener grüner
   Evidenz** von `proposed` auf `approved` — nicht mit dieser Bestätigung.

## A1.8 Unverändert gültig

Keine neue Wire-Form · RFC-0005 und RFC-0006 unverändert · Legacy byte-/shape-exakt ·
keine Persistenz · keine Job-Engine · kein Scheduler · keine Grant-Laufzeit · kein
`awaiting-authorization` · keine neue Dependency · **TM-001 nur teilweise bearbeitet**,
**TM-002 höchstens teilweise mitigiert**, **DNS-Rebinding offen**, **`profile.delete`
offen** · **Phase 5 ist mit Prompt 19 nicht abgeschlossen.**

---

# RFC-0007 AMENDMENT 2 — Vollmigration der durchsetzbaren Pfade (Phase 5C)

**Status:** Accepted · **Angenommen am:** 2026-07-19 · **Basis-SHA:** `96bcc6e68434ddcc06b9897a0df4cfdb5734769f`
**Anlass:** Prompt 20 / Phase 5C. **Entscheider:** Nutzer (explizite Freigabe „Amendment 2 annehmen und fortfahren").

**Begründung.** Amendment 1 enthält einen belegten Scope-Widerspruch: §792 und §802 kündigen für
Prompt 20 die Migration der **neun** verbleibenden REST-Routen an, während §A1.4 (Zeilen 901–903)
`launcher.profile.delete` ausdrücklich **bis Phase 10** unverändert lässt, weil dafür kein
serverseitig überprüfbarer Preview-/Grant-Vertrag existiert. Beide Aussagen sind nicht gleichzeitig
erfüllbar — die „neun" enthalten das Delete. Amendment 2 löst den Widerspruch zugunsten der
sicherheitskonservativen Lesart auf und ergänzt die für die Restmigration notwendigen
Vertragsvertiefungen.

## A2.1 (A) Ehrlicher Scope

Prompt 20 migriert:

* alle noch offenen **20** Voice-Action-Typen,
* **acht** derzeit sicher migrierbare REST-Routen,
* den direkten `activate`-Refresh-Bypass in `assistant_core.process_message`.

Danach gilt:

| Größe | Vorher (Prompt 19) | Nachher (Prompt 20) |
|---|---|---|
| Capability-gesteuerte Voice-Actions | 2 / 22 | **22 / 22** |
| Capability-gesteuerte mutierende REST-Routen | 1 / 10 | **9 / 10** |
| Gespeichertes `ActionSpec.risk` | vorhanden | **entfernt** |
| Produktiver `execute_action`-Fallback | vorhanden | **entfernt** |

`DELETE /launcher/profiles/{profile_id}` bleibt **exakt die einzige** datierte Phase-10-Ausnahme.
Der direkte DELETE darf **nicht** als „Confirmation" oder „Grant" umetikettiert werden; der
browserlokale Zwei-Klick-Dialog ist serverseitig nicht überprüfbar (§A1.4, D5).

**Zulässiger Abschlussstatus:** `PHASE 5C FÜR ALLE DERZEIT DURCHSETZBAREN PFADE VOLLSTÄNDIG`.
**Unzulässig** ist die uneingeschränkte Behauptung, die ursprüngliche vollständige Phase 5
inklusive Profile-Delete und serverseitigem Grant sei abgeschlossen.

## A2.2 (B) Kanonische Action-Zuordnung

| Action | Capability | Status |
|---|---|---|
| `SEARCH` | `web.search` | Prompt 19 |
| `BROWSE` | `web.browse` | Prompt 20 |
| `OPEN` | `web.open` | Prompt 20 |
| `NEWS` | `web.news` | Prompt 20 |
| `RESEARCH` | `web.research` | Prompt 20 |
| `SCREEN` | `screen.describe` | Prompt 20 |
| `CLIPBOARD` | `clipboard.process` | Prompt 20 |
| `CLIPBOARD_NOTE` | `clipboard.note.create` | Prompt 20 |
| `INBOX_READ` | `vault.inbox.read` | Prompt 20 |
| `INBOX_WRITE` | `vault.inbox.write` | Prompt 20 |
| `MEMORY_READ` | `memory.read` | Prompt 20 |
| `MEMORY_WRITE` | `memory.write` | Prompt 20 |
| `MEMORY_FORGET` | `memory.forget` | Prompt 19 |
| `NOTES_RECENT` | `vault.notes.recent` | Prompt 20 |
| `PROJECT_CONTEXT` | `vault.project.context` | Prompt 20 |
| `SESSION_SUMMARY` | `conversation.summary` | Prompt 20 |
| `APP_OPEN` | `launcher.app.open` | Prompt 20 |
| `PROFILE_ACTIVATE` | `launcher.profile.activate` | Prompt 20 |
| `PROFILE_STATUS` | `launcher.profile.status` | Prompt 20 |
| `APP_AUTOSTART_ON` | `launcher.app.autostart.set` | Prompt 20 |
| `APP_AUTOSTART_OFF` | `launcher.app.autostart.set` | Prompt 20 |
| `APP_PLACE` | `launcher.app.placement.set` | Prompt 20 |

`APP_AUTOSTART_ON` und `APP_AUTOSTART_OFF` teilen **denselben** semantischen Vertrag und
unterscheiden sich ausschließlich durch den booleschen Eingabewert `enabled`.

**Invariante:** `set(MIGRATED_ACTIONS) == set(actions.REGISTRY)`, beide mit exakt **22** Einträgen.
Es werden **nicht** 22 unterschiedliche Capability-Namen erzwungen — mehrere Adapter dürfen
denselben semantischen Vertrag verwenden (21 Namen für 22 Actions).

## A2.3 (C) Kanonische REST-Zuordnung

| Route | Capability | Status |
|---|---|---|
| `POST /settings` | `settings.update` | Prompt 20 |
| `POST /music/selection` | `music.selection.set` | Prompt 20 |
| `POST /commands/app/open` | `launcher.app.open` | Prompt 20 |
| `POST /launcher/apps/{id}/toggle` | `launcher.app.autostart.set` | Prompt 20 |
| `POST /launcher/apps/{id}/placement` | `launcher.app.placement.set` | Prompt 20 |
| `POST /launcher/profiles` | `launcher.profile.create` | Prompt 20 |
| `POST /launcher/profiles/{id}/activate` | `launcher.profile.activate` | Prompt 20 |
| `POST /launcher/profiles/{id}/duplicate` | `launcher.profile.duplicate` | Prompt 20 |
| `POST /launcher/profiles/{id}/rename` | `launcher.profile.rename` | Prompt 19 |
| `DELETE /launcher/profiles/{id}` | — | **Phase 10** |

Voice und REST benutzen bei derselben fachlichen Operation **denselben** Capability-Vertrag
(`launcher.app.open`, `launcher.app.autostart.set`, `launcher.app.placement.set`,
`launcher.profile.activate`). Es entsteht **keine** transportabhängige zweite Wahrheit.

## A2.4 (D) Typisierte Verträge und request-spezifische Bindings

`InputSchema` und `OutputSchema` werden **rückwärtskompatibel** zu echten Typverträgen vertieft:
explizite Feldtypen, eindeutiges required/optional, **keine** implizite Typumwandlung, **keine**
unbekannten Felder, deterministische Fehlermeldungen, ausschließlich synthetische Fixtures.

Ergänzte Scopes — **nur die belegten**: `config.settings`, `config.music`, `conversation`.
`config.launcher` wird **nicht** für fachfremde Daten missbraucht.

**Invocation-Bindings.** Für request-spezifische Abhängigkeiten ist ein kleiner **unveränderlicher**
Seam zulässig. Er enthält ausschließlich schmale, tatsächlich benötigte Ports:

* AI-Client-Port,
* unveränderlicher History-Snapshot,
* semantischer Launcher-Mutationsport,
* falls für SCREEN notwendig: ein schmaler autorisierter Feedback-Port.

**Verboten** darin: Runtime- oder Server-Objekte, Service-Locator, frei erweiterbare
Dependency-Dicts, Session-Dictionaries, globale Rückreferenzen.

Die Bindings sind **nicht** Teil von `CapabilityRequest`, Input-Schema, Payload, `meta`,
Preview-/Idempotency-Hash, Policy-Entscheidung oder Auditdaten. Clients, Historien und Funktionen
werden **nie** serialisiert oder in Payload bzw. `meta` versteckt.

## A2.5 (E) Vollständige Wirkungsdeklaration

Die Effekt- und Datenklassifikation wird **direkt aus dem Produktionscode** erhoben, nicht aus
alten Tabellen kopiert. Primär- **und** Folgeeffekte zählen: Browser-/HTTP-Zugriffe, Summary-LLM,
TTS, sichtbarer Browser/Fokus, lokale Writes, Research-Autosave, sensitive Reads, Launcher-/
Config-Mutationen.

Jede Voice-Action besitzt potenziell einen Netzwerkeffekt: 15 Actions verwenden Summary-LLM und
TTS, sechs Launcher-Actions sprechen ihr Ergebnis direkt, `OPEN` ist selbst ein Browser-/
Netzwerkpfad.

**Ausdrücklich zu korrigieren:**

* `INBOX_WRITE` liest beim LLM-Dedup vorhandene persönliche Inbox-Inhalte und schreibt lokal →
  `READ_SENSITIVE`, `LOCAL_WRITE`, `NETWORK_READ`.
* `CLIPBOARD_NOTE` liest sensitive Clipboard-Daten, kann persönliche Inbox-Daten zum Dedup lesen,
  sendet Daten an das LLM und schreibt persönliche Daten →
  `READ_SENSITIVE`, `LOCAL_WRITE`, `NETWORK_READ`.

**Keine deklarierte Wirkung darf vor einer `Allow`-Entscheidung stattfinden.** Insbesondere wird
die SCREEN-Sprachausgabe („Ich werfe kurz einen Blick …") **nach** die Policy-Freigabe, aber
weiterhin **vor** Aufnahme/Upload verschoben. Ist das ohne Vertragsbruch unmöglich, gilt
`PROMPT 20 BLOCKIERT – PRE-AUTH-WIRKUNG BEI SCREEN`.

Summary, TTS, sichtbarer Browser/Fokus und Research-Autosave gehören zum **vollständigen
Wirkungsvertrag** der auslösenden Capability. Sie laufen nach `DENIED`, `NEEDS`, `TIMEOUT`,
`CANCELLED` oder `FAILED` **nicht** als normaler Erfolgs-Folgeeffekt weiter. Bestehende
Fehlertexte und Legacy-Fehlerframes bleiben erhalten, ohne einen falschen `done`- oder
Erfolgspfad zu erzeugen.

## A2.6 (F) Safe-Target- und SSRF-Evidenz

`target_allowed=True` darf **nicht** pauschal für alle migrierten Actions gesetzt werden.

* Feste, im Code definierte Provider-Ziele dürfen **adapterseitig** als feste Ziele belegt werden.
* Nutzer- oder modellgesteuerte URLs (`BROWSE`, `OPEN`, …) benötigen eine vom runtime-eigenen
  `TargetGuard` **abgeleitete** Evidenz.
* Payload oder LLM-Inhalt dürfen sich **niemals selbst** als sicher deklarieren.
* Jede tatsächliche HTTP-Weiterleitung und Browsernavigation wird **transportseitig erneut**
  geprüft; `RESEARCH` prüft **jeden** entdeckten Link und **jeden** Redirect.
* **Kein** automatisches ungeprüftes Redirect-Following; die verbundene IP wird **nach** der
  Navigation kontrolliert.

**DNS-Rebinding ohne IP-Pinning bleibt ein ehrlich dokumentiertes Restrisiko** (Phase 9).

## A2.7 (G) Outcome-Projektion und Timeout-Ownership

| Outcome | Legacy-Projektion |
|---|---|
| `OK` | bestehendes Rohresultat, bestehender `done`-Pfad |
| `DENIED` | bestehender Fehlerpfad — **niemals** `done` |
| `NEEDS` | bestehender Confirmation-Pfad — **niemals** `done` |
| `FAILED` | bestehender Fehlerpfad — **niemals** falsche Zusammenfassung |
| `TIMEOUT` | bestehender Timeout-/Fehlerpfad |
| `PARTIAL` | ausdrücklich degradierter Pfad — **niemals** uneingeschränktes `done` |
| `CancelledError` | unverändert weiterreichen |

Dafür ist eine **interne typisierte Legacy-Projektion** zulässig; es entsteht **kein** neues
Wire-Format. Der Coordinator bleibt der **einzige äußere Timeout-Owner** jedes migrierten Action-
und REST-Pfads. Nach vollständiger Action-Migration wird der produktive Fallback
`asyncio.wait_for(execute_action(...))` **entfernt**.

Die SDK-internen Anthropic-Retries (`max_retries=2`) sind eine **bestehende Provider-Eigenschaft**:
es wird **keine** weitere Retry-Schicht ergänzt und die SDK-Eigenschaft **nicht stillschweigend
abgeschaltet**. Diese Grenze ist für Phase 6 dokumentiert.

## A2.8 (H) Context-Refresh-Bypass

Der direkte Pfad in `assistant_core.process_message`
(`if "activate" in user_text.lower(): await asyncio.to_thread(refresh_data)`) läuft künftig über
**dieselbe bestehende Capability `context.refresh`** wie Startup und Settings-Save.

Anforderungen: exakt **einmal** ausführen · **gleiche Position** relativ zu History und
Prompt-Erstellung · gleiche beobachtbare Semantik · **keine** zusätzlichen Provider- oder
Netzwerkaufrufe · **kein** direkter `refresh_data`-Bypass mehr in diesem Pfad.

## A2.9 (I) Ablösung von gespeichertem `ActionSpec.risk`

**Erst** wenn alle 22 Action-Typen migriert und die vollständige Suite grün ist:

* das gespeicherte `risk`-Dataclass-Feld wird **entfernt**,
* alle `risk=`-Konstruktorargumente werden **entfernt**,
* `CONFIRM_ACTIONS` wird **ausschließlich** aus den kanonischen Capability-Effekten abgeleitet,
* `CONFIRM_ACTIONS` bleibt exakt `{MEMORY_FORGET}`,
* eine Mutation des `DESTRUCTIVE`-Effekts **muss** den abgeleiteten Confirmation-Status ändern.

Benötigen bestehende interne Konsumenten `ActionSpec.risk`, darf höchstens eine **read-only
Kompatibilitäts-Property** verbleiben, die den Wert ausschließlich aus demselben kanonischen
Action-zu-Capability-Katalog ableitet: `confirm` genau bei `DESTRUCTIVE`, sonst `low`.

**Es darf keine zweite Risk-Tabelle, kein gespeicherter Risk-Wert und keine zweite
Sicherheitswahrheit entstehen.** `ActionSpec.execute` und `ActionSpec.describe` bleiben gemäß
RFC-0001/RFC-0007 erhalten; Prompt-Metadaten wandern in dieser Phase **nicht** in den
Capability-Vertrag.

## A2.10 Unverändert gültig

Keine neue Wire-Form · RFC-0005 und RFC-0006 unverändert · Legacy byte-/shape-exakt · keine
Persistenz · keine Job-Engine · kein Scheduler · **keine Grant-Laufzeit** · kein
`awaiting-authorization` · keine neue Dependency · keine Presence-Erkennung · **kein IP-Pinning** ·
Presence-/Preview-Regeln bleiben **datiert und inaktiv** · native D3-Ausnahmen bleiben außerhalb
des Scopes und **es entsteht kein neuer nativer Bypass** · **TM-001 auch nach Vollmigration nicht
vollständig gelöst** · **TM-002 ohne IP-Pinning nur teilweise mitigiert** · **`profile.delete`
bleibt offen bis Phase 10.**

---

## A2.11 Umsetzungsstand nach Prompt 20 (2026-07-19)

Amendment 2 ist **vollständig umgesetzt**. Belegt durch `tests/test_phase5c_audit.py`
(eigenes Fast-Gate) und das Ledger `PHASE5C_CAPABILITY_FULL_MIGRATION.md`.

| Zusage | Stand |
|---|---|
| §A2.1 Ehrlicher Scope | 22/22 Actions, 9/10 Routen, `activate`-Bypass geschlossen |
| §A2.2 Kanonische Action-Zuordnung | erfüllt — 22 Actions auf **21** Verträgen |
| §A2.3 Kanonische REST-Zuordnung | erfüllt — Voice und REST teilen die Verträge |
| §A2.4 Typisierte Verträge + Bindings | erfüllt — `Field`, drei neue Scopes, vier Ports |
| §A2.5 Vollständige Wirkungsdeklaration | erfüllt — aus dem Code erhoben, SCREEN-Ansage hinter die Freigabe |
| §A2.6 Safe-Target/SSRF | erfüllt — feste vs. abgeleitete Evidenz, fail-closed ohne Guard |
| §A2.7 Outcome/Timeout | erfüllt — kein falsches `done`, Coordinator einziger Timeout-Owner |
| §A2.8 Context-Refresh | erfüllt — ein Vertrag für alle drei Auslöser |
| §A2.9 `risk`-Ablösung | erfüllt — abgeleitet, Mutationsbeweis vorhanden |

**Unverändert offen** (§A2.10): `launcher.profile.delete` bis zur Phase-10-Grant-Laufzeit ·
TM-001 flächendeckend durchsetzbar, **nicht gelöst** · TM-002 ohne IP-Pinning nur teilweise
mitigiert · **DNS-Rebinding** offen · Presence-/Preview-Regeln datiert und inaktiv · native
D3-Ausnahmen außerhalb des Scopes, **kein neuer nativer Bypass** · SDK-interne
Provider-Retries bestehen fort, **keine** zweite Retry-Schicht.

