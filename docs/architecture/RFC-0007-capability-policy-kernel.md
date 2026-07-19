# RFC-0007 — Capability- und Policy-Kernel

- **Status:** Accepted for incremental implementation (2026-07-19)
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
