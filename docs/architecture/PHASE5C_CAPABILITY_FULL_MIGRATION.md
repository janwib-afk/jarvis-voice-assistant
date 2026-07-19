# Phase 5C — Vollmigration der durchsetzbaren Capability-Pfade (Prompt 20)

> Testgetriebenes Migrationsledger zu **RFC-0007 Amendment 2**. Ein Abschnitt je Slice:
> Ziel und öffentlicher Seam · Ausgangsverhalten · erstes beobachtetes ROT · minimales GRÜN ·
> Regressionsergebnis · Commit-SHA · Rollback-Pfad · offene Restrisiken.

## Rahmen

| | |
|---|---|
| **Basis-SHA** | `96bcc6e68434ddcc06b9897a0df4cfdb5734769f` (Merge-Commit aus Prompt 19, zwei Eltern) |
| **Branch** | `phase-5c-capability-full-migration`, direkt von `origin/master` |
| **Amendment** | RFC-0007 Amendment 2, angenommen 2026-07-19 durch den Nutzer |
| **Vorgänger-Ledger** | `PHASE5B_CAPABILITY_POLICY_KERNEL_MIGRATION.md` (Prompt 19, Slices 0–10) |

### Start-Gate (read-only, vor jeder Dateiänderung)

| Prüfung | Ergebnis |
|---|---|
| `origin/master` | `96bcc6e6…` — exakt |
| Merge-Eltern | `f03e4d63…` + `99815a22…` — zwei |
| Post-Merge-Lauf `29689663484` | `success`, `workflow_dispatch`, headSha `96bcc6e6…` |
| Fast-Job `88200038084` | `success` |
| Browser-Job `88200038078` | `success` |
| Actions in `actions.REGISTRY` | **22**, davon 2 migriert (`SEARCH`, `MEMORY_FORGET`), **20 offen** |
| Mutierende REST-Routen | **10** (9× `POST`, 1× `DELETE`), Rename migriert, **8 migrierbar**, Delete = Ausnahme |
| Activate-Bypass | `assistant_core.py:431-432` — `await asyncio.to_thread(refresh_data)` |
| Gespeichertes `risk` | `actions.py:88` (Feld), `actions.py:629` (`CONFIRM_ACTIONS` daraus abgeleitet) |
| Legacy-Fallback | `assistant_core.py:342` — `asyncio.wait_for(execute_action(...))` |

### Unveränderte Nutzerartefakte

41 Einträge im Arbeitsbaum sind **ausschließlich** Nutzerartefakte und werden von keinem Slice
angefasst oder gestaged: `.claude/settings.local.json` (modifiziert), `.agents/`,
`.claude/skills/`, `.hermes/`, `.impeccable/`, `skills-lock.json` sowie die lokalen
Screenshot-/Evidenz-/Baseline-Verzeichnisse unter `docs/`.

Der Branchwechsel war nachweislich gefahrlos: `git diff HEAD origin/master` war leer, der Baum
also identisch — keine Nutzeränderung konnte überschrieben werden. Es wurde **kein** `git stash`,
`git reset --hard`, `git clean`, `git add .` oder `git add -A` verwendet; jeder Commit stagt
ausschließlich explizit aufgezählte Pfade.

### Baseline vor Produktivänderungen

| Gate | Ergebnis |
|---|---|
| `python -m unittest discover -s tests` | **1024 Tests, OK** |
| `verify_phase4` | **27/27** |
| `verify_phase5` | **13/13** |
| Fixture-Set-SHA256 (4 Dateien) | `dd770c19cc24fae8a52807220ad134b48b605085c14e40dda857dd0c2f1f3b55` |

Die Baseline ist grün — `PROMPT 20 BLOCKIERT – BASELINE ROT` trifft nicht zu.

Die Verifier laufen gegen den lokalen Harness `docs/design-baseline/tools/baseline_server.py` auf
**Port 8341**. **Port 8340 ist von der echten Jarvis-Instanz des Nutzers belegt und wird zu keinem
Zeitpunkt beendet**; es wurden ausschließlich eigene Testprozesse gestoppt.

---

## Slice 0 — Amendment 2, Baseline und Ledger

**Ziel und Seam.** Den in Amendment 1 belegten Scope-Widerspruch förmlich auflösen und die
Vertragsvertiefungen beschließen, bevor Produktionscode entsteht. Kein Produktionscode in diesem
Slice.

**Ausgangsverhalten.** RFC-0007 kündigte an zwei Stellen (`:792`, `:802`) die Migration von
**neun** REST-Routen in Prompt 20 an, während Amendment 1 §A1.4 (`:901-903`)
`launcher.profile.delete` bis Phase 10 unverändert lässt. Beides ist nicht gleichzeitig erfüllbar.

**Geändert.**
* `docs/architecture/RFC-0007-capability-policy-kernel.md` — Amendment 2 (§A2.1–A2.10) angehängt;
  die widersprüchliche Stelle `:792` trägt jetzt einen expliziten Korrekturhinweis auf §A2.1.
* `docs/architecture/PHASE5C_CAPABILITY_FULL_MIGRATION.md` — dieses Ledger.

**Rollback.** `git revert` dieses Commits; da kein Produktionscode betroffen ist, bleibt die
Laufzeit unberührt.

**Restrisiko.** Keines — reine Dokumentation.

---

## Slice 1 — Vertragstypen und erster Binding-Tracer

**Ziel und Seam.** `InputSchema`/`OutputSchema` rückwärtskompatibel zu echten Typverträgen
vertiefen, die drei belegten Scopes ergänzen und den schmalen unveränderlichen
Invocation-Binding-Seam einführen — belegt durch **zwei** vertikale Tracer statt durch ein
spekulatives Framework. Öffentlicher Seam: `capability.*`.

**Ausgangsverhalten.** `InputSchema.fields` war ein `tuple[str, ...]`; jedes Feld war
untypisiert und pflichtig. Request-spezifische Abhängigkeiten (LLM-Client, History,
Launcher-Mutation) erreichten die Piloten gar nicht — die vier Prompt-19-Piloten brauchten
keine.

**Erstes beobachtetes ROT.** 23 von 24 Tests scheiterten
(`AttributeError: module 'capability' has no attribute 'Field'`, fehlende `Scope`-Werte,
fehlende `InvocationBindings`, fehlende Mappings). Der **eine** grüne Test war genau
`test_plain_string_field_stays_untyped_and_required` — die Rückwärtskompatibilität galt
also schon vor der Änderung, wie beabsichtigt.

**Minimales GRÜN.**
* `Field(name, type=None, required=True)` mit reiner `check()`-Funktion; `str`-Einträge
  werden weiterhin als untypisierte Pflichtfelder gelesen.
* `bool` wird nie für ein `int`-Feld akzeptiert, obwohl Python das strukturell erlaubt.
* Fehlermeldungen sortiert → deterministisch.
* `Scope.CONFIG_SETTINGS`, `Scope.CONFIG_MUSIC`, `Scope.CONVERSATION`.
* `InvocationBindings` mit **genau vier** Ports (`ai`, `history`, `mutate_launcher`,
  `feedback`); durchgereicht als `Coordinator.attempt(..., bindings=…)` →
  `AttemptContext.bindings`. **Nicht** in Request, Payload, `meta`, Idempotency-Hash,
  Policy oder Audit.
* `_Delegated` führt den bestehenden `ActionSpec`-Executor **hinter** dem Vertrag aus —
  keine kopierte Fachlogik, also keine zweite Wahrheit.
* `PROFILE_STATUS` → `launcher.profile.status`, `SESSION_SUMMARY` → `conversation.summary`.

**Wirkungsbefund.** Beide Verträge deklarieren die TTS- bzw. Summary-LLM-Folgeeffekte als
`network-read`. `conversation.summary` liest `personal` (der Sitzungsverlauf) und ist damit
`governed`, nicht `trivial`.

**Mutationen.** M1 bool-Schutz, M2 Typprüfung, M3 Mapping, M4 Bindings, M5 optional→required,
M6 Summary-`NETWORK_READ`, M7 `reads personal→local`, M8 Status-TTS-Effekt.
**M6 blieb zunächst grün** und deckte eine echte Lücke auf: die Wirkungsdeklaration war
ungeschützt. Nach Ergänzung der Effekt-Zusagen sind **alle acht ROT**.

**Regression.** 1050 Tests OK (Baseline 1024). Ein Test-Double (`_spy` in
`test_capability_pilot_search`) spiegelt die erweiterte Coordinator-Signatur — keine
Verhaltenslockerung.

**Commit.** `e8cd881`. **Rollback:** `git revert e8cd881` — die vier Prompt-19-Piloten
laufen unverändert weiter, weil die Pilotform (`str`-Felder) nie ungültig wurde.

**Restrisiko.** Der `feedback`-Port ist deklariert, aber bis Slice 6 ungenutzt.

---

## Slice 2 — Outcome- und Adapter-Härtung

**Ziel und Seam.** Vor der Massenmigration festlegen, was ein **Nicht-Erfolg** beobachtbar
auslöst. Seam: die Frames, die `run_action_and_respond` emittiert, plus die Folgeeffekte
(Summary-LLM, TTS).

**Ausgangsverhalten — ein belegter Defekt.** Der migrierte Pfad projizierte **jedes**
Outcome auf einen blossen String und sendete danach **unbedingt** `done`. Eine abgelehnte
oder fehlgeschlagene Wirkung sah am Draht aus wie eine gelungene. Schlimmer: der
`memory.forget`-Fallbacktext („Das konnte ich nicht vergessen.") enthält kein
„fehlgeschlagen" — er lief deshalb in den **Summary-LLM**, also in einen echten
Netzaufruf nach einer Ablehnung.

**Erstes beobachtetes ROT.** 21 Fehler/Errors, darunter ausdrücklich
`test_summary_llm_does_not_run_after_denied` — der vorhergesagte Defekt ist belegt.
Grün blieben `test_ok_still_emits_done`, `test_summary_llm_runs_on_success`, die
Cancellation- und die Timeout-Ownership-Prüfung: dieses Verhalten war bereits korrekt.

**Minimales GRÜN.**
* `LegacyResult(text, status, error_type)` mit `ok`/`degraded` — eine **interne**
  typisierte Projektion, **kein** Wire-Format, sie verlässt den Prozess nie.
* `_report_capability_denial` projiziert Nicht-Erfolge auf den **bestehenden**
  Fehlerpfad: `action.failed`-Log, `error`-Frame, strukturierter Client-Fehler — exakt
  die Form des Exception-Zweigs.
* `denied` unterdrückt `done` **und** den gesamten Erfolgs-Nachlauf (Summary, Quellen,
  Autosave); gesprochen wird die bestehende Fehlerform.
* `MIGRATED_ACTIONS` ist jetzt ein `MappingProxyType` — die Zuordnung ist eine
  Sicherheitsentscheidung und zur Laufzeit nicht mehr biegbar.

**Outcome-Matrix (belegt).** `OK` → `done` + Summary · `DENIED`/`NEEDS`/`TIMEOUT`/`FAILED`
→ `error`, nie `done`, kein Summary · `PARTIAL` → degradiert, kein uneingeschränktes
`done` · `CancelledError` → unverändert weitergereicht.

**Mutationen.** M9 `MappingProxyType`→`dict`, M10 `ok` immer `True`, M11 `done` trotz
Nicht-Erfolg, M12 Erfolgs-Nachlauf nach Nicht-Erfolg, M13 Nicht-Erfolg verschluckt —
**alle fünf ROT**.

**Regression.** 1069 Tests OK. Sechs Zusicherungen in Prompt-19-Tests lesen jetzt
`.text` statt des nackten Strings: das ist die **beabsichtigte** Vertragsänderung aus
§A2.7, keine Lockerung — die geprüfte Aussage ist unverändert.

**Rollback.** `git revert` dieses Commits stellt die String-Rückgabe wieder her; die
Slice-1-Tracer laufen weiter, verlieren aber die Nicht-Erfolgs-Projektion.

**Restrisiko.** Der Legacy-Exception-Pfad ruft weiterhin den Summary-LLM mit
`"Fehler: …"` auf — unverändertes Altverhalten, das erst mit dem Wegfall des Fallbacks
in Slice 12 vollständig verschwindet.

---

## Slice 3 — Web-Pfade (BROWSE, OPEN, NEWS, RESEARCH)

**Ziel und Seam.** Die vier Web-Actions migrieren und dabei die pauschale
`target_allowed=True`-Zusage der Pilotphase ablösen. Seam: `capability.run_migrated` und
die Wirkungsdeklaration; kontrollierte Grenzen sind `browser_tools.*` und der injizierte
DNS-Resolver.

**Ausgangsverhalten.** `run_migrated` setzte `target_allowed=True` **für jede** migrierte
Action — auch für modellgesteuerte URLs. Die vier Web-Actions liefen über den Legacy-Fallback.

**Erstes beobachtetes ROT.** Alle 19 Tests scheiterten mit `UnknownCapability`/`KeyError` —
die vier Verträge existierten nicht.

**Minimales GRÜN.**
* Vier Verträge `web.browse`/`web.open`/`web.news`/`web.research`, alle über `_Delegated`.
* `Coordinator.deps` als getypte Leseeigenschaft (kein Locator — dieselbe Referenz, die
  `_exec_profile_rename` schon nutzt).
* `_target_evidence` unterscheidet **feste** Provider-Ziele (`web.search`, `web.news`,
  `web.research` — die URL steht im Code) von **modellgesteuerten** (`web.browse`,
  `web.open` — Evidenz wird vom `TargetGuard` **abgeleitet**).
* Fehlt der Guard, ist das Ergebnis `None` → `needs:safe-target` → **fail-closed**.

**Zweites ROT — ein selbst eingeführter Defekt.** Der erste Entwurf rief `check_url`
synchron auf. `check_url` löst DNS **blockierend** auf; auf der Event-Loop hätte ein
langsamer DNS-Server die gesamte WS-Empfangsschleife angehalten. Der erste Testentwurf
dazu war **vakuum** (er zählte die Ticks erst am Ende, wenn ohnehin beide Seiten fertig
waren) und blieb grün. Nach Umbau auf „Tickstand *im Moment* der Auflösung" zeigte er
**0 Ticks** — belegtes ROT. Fix: `await asyncio.to_thread(guard.check_url, …)`, genau wie
in `guarded_goto`/`install_page_guard`.

**Mutationen.** M14 Evidenz pauschal `True` · M15 fehlender Guard = fail-open ·
M16 BROWSE/OPEN als feste Ziele deklariert · M17 Guard-Urteil ignoriert ·
M18 RESEARCH-Autosave nicht deklariert · M19 BROWSE-Mapping verbogen ·
M20 DNS blockiert die Loop — **alle sieben ROT**.

**Wirkungsbefund.** `web.research` deklariert `local-write` und `writes personal`, weil der
Autosave des Rechercheergebnisses in die persönliche Inbox ein Folgeeffekt dieser
Capability ist — er läuft in `_finish_research` und darf nach einem Nicht-Erfolg (Slice 2)
nicht stattfinden.

**Regression.** 1089 Tests OK. Zwei Prompt-19-Tests kodierten den Pilotumfang und wurden
angepasst, nicht gelöscht: die Negativliste „nur SEARCH migriert" fällt planmäßig
(Vollständigkeit belegt ab Slice 11 der Audit), und das Fallback-Beispiel wechselte von
`NEWS` auf das noch offene `APP_PLACE`.

**Rollback.** `git revert` dieses Commits; die vier Actions fallen auf `execute_action`
zurück, alle übrigen Slices bleiben gültig.

**Restrisiko.** DNS-Rebinding zwischen Evidenz und Navigation bleibt offen — abgefedert,
aber nicht beseitigt durch die transportseitige Nachprüfung der verbundenen IP. IP-Pinning
bleibt Phase 9.

---

## Slice 4 — Vault- und Memory-Lesepfade

**Ziel und Seam.** `INBOX_READ`, `MEMORY_READ`, `NOTES_RECENT`, `PROJECT_CONTEXT`
migrieren. Kontrollierte Grenze: `memory.*` (Dateisystem), ausschließlich synthetische
Inhalte — kein echter Vault wird angefasst.

**Erstes beobachtetes ROT.** 33 Fehler (`UnknownCapability`).

**Minimales GRÜN.** Vier Verträge über `_read_contract`; alle deklarieren
`read-sensitive` **und** `network-read`, weil alle vier ein `summary_task` tragen: der
gelesene persönliche Inhalt geht an das Summary-LLM und danach als TTS hinaus.
`reads=personal`, `writes=∅` → durchweg `governed`, nie `trivial`.

**Datenschutz-Beleg.** Ein Audit-Spion prüft, dass der synthetische Vault-Inhalt weder
im Ereignisnamen noch in den Feldern auftaucht — die geschlossene Allowlist aus RFC-0004
macht das strukturell unmöglich. Zusätzlich ist belegt, dass keine eingecheckte Fixture
einen Vault-Auszug enthält.

**Mutationen.** M21 Lesepfade als harmlos deklariert · M22 Mapping verbogen ·
M23 Timeout weicht vom `ActionSpec` ab — **alle drei ROT**.

**Regression.** 1104 Tests OK.

**Rollback.** `git revert`; die vier Actions fallen auf `execute_action` zurück.

**Restrisiko.** TM-008 (Vault-/Memory-Injection in den Prompt) bleibt unberührt — die
Migration klassifiziert die Wirkung, sie filtert den Inhalt nicht.

---

## Slice 5 — Vault-/Memory-Writes

**Ziel und Seam.** `INBOX_WRITE`, `MEMORY_WRITE`, `CLIPBOARD_NOTE` migrieren **und** die
in §A2.5 geforderte Korrektur der Wirkungsklassifikation belegen.

**Belegter Befund.** `memory.write_inbox_entry` liest die vorhandene heutige Inbox-Datei
und schickt beim Dedup bis zu **2000 Zeichen persönlicher Inhalte** an Haiku
([memory.py](memory.py), `write_inbox_entry`). `INBOX_WRITE` und `CLIPBOARD_NOTE` sind
damit `read-sensitive` **+** `local-write` **+** `network-read` — nicht bloß lokale
Schreibvorgänge.

Dieser Pfad wird nicht behauptet, sondern gemessen: ein Fake-LLM-Client fängt ab, was
tatsächlich übertragen wird, und der Test prüft, dass der **vorhandene** Eintrag im
Prompt steht. Wäre er es nicht, wäre die Klassifikation zu streng — der Test schlägt in
beide Richtungen aus.

`MEMORY_WRITE` hat **keinen** Dedup-Read: es hängt nur an. Es trägt `local-write` und
`network-read` (Summary + TTS), aber kein `read-sensitive` — die Klassifikation folgt dem
Code, nicht einem Schema.

**Erstes beobachtetes ROT.** 16 Fehler (`UnknownCapability`).

**Mutationen.** M24 versteckter Read-/Netzeffekt weggelassen · M25 Clipboard-Scope
entfernt · M26 `memory.write` als `destructive` · M27 Mapping verbogen — **alle vier ROT**.

**Regression.** 1116 Tests OK. Die Tests arbeiten in einem temporären Inbox-Ordner; der
echte Vault des Nutzers wird nie angefasst.

**Rollback.** `git revert`.

**Restrisiko.** Der Dedup-Prompt überträgt weiterhin persönliche Inhalte an den Provider —
das ist bestehendes Produktverhalten. Die Migration macht es **sichtbar und
klassifiziert**, sie unterbindet es nicht (Preview/Transfer bleibt datiert, Phase 9).

---

## Slice 6 — Sensitive Eingaben (CLIPBOARD, SCREEN)

**Ziel und Seam.** Beide Pfade migrieren **und** die in §A2.5 geforderte
Reihenfolge-Korrektur durchführen. Seam: der `feedback`-Port der Invocation-Bindings.

**Belegter Defekt.** [assistant_core.py:345](assistant_core.py#L345) sprach
„Ich werfe kurz einen Blick auf deinen Bildschirm." **vor** dem Registry-Lookup und vor
jeder Entscheidung — eine Wirkung ohne Freigabe. Kein Test deckte das ab (die Formulierung
kam im ganzen Repo genau einmal vor, ohne Zusicherung).

**Neue Reihenfolge.** `Policy-Allow → autorisierte kurze Rückmeldung → Capture →
Verarbeitung`. Die Ansage läuft jetzt im Capability-Execute über
`ctx.bindings.feedback` — also **hinter** der Freigabe und weiterhin **vor** Aufnahme und
Upload. Der Wortlaut ist unverändert. `PROMPT 20 BLOCKIERT – PRE-AUTH-WIRKUNG BEI SCREEN`
trifft damit **nicht** zu: die Verschiebung war ohne Vertragsbruch möglich, weil der
`feedback`-Port aus Slice 1 genau dafür vorgesehen war.

**Beleg.** Der Test ordnet Rückmeldung und Capture in einer gemeinsamen Liste und prüft
die Reihenfolge; bei einer Deny-Regel muss die Liste **leer** bleiben — eine abgelehnte
Wirkung darf sich nicht einmal ankündigen.

**Klassifikation.** Beide lesen `sensitive` (nicht `personal`): Bildschirm und
Zwischenablage können alles enthalten, was gerade offen ist. `secret` bleibt strukturell
nicht darstellbar (SI-5, geprüft).

**Presence bleibt datiert.** Die Tests belegen, dass `presence-unlocked` **nicht** in
`ACTIVE_RULES` steht und `Evidence().presence` weiterhin `UNKNOWN` ist — es wird
nirgends behauptet, `unknown` sei eine bestätigte Anwesenheit.

**Mutationen.** M28 Ankündigung entfällt · M29 Ankündigung nicht verdrahtet ·
M30 sensitive Eingaben als harmlos · M31 Mapping verbogen — **alle vier ROT**.

**Regression.** 1130 Tests OK. Zwei Test-Doubles spiegeln die um `feedback` erweiterte
Signatur.

**Rollback.** `git revert` — die Ansage kehrt an ihre alte Stelle vor der Policy zurück.

**Restrisiko.** TM-005/TM-006 bleiben offen: es gibt weiterhin **keine** Vorschau und
**keine** Regionsauswahl vor dem Upload. Preview bleibt datiert (Phase 9).

---

## Slice 7 — Launcher-Sprachsteuerung

**Ziel und Seam.** `APP_OPEN`, `PROFILE_ACTIVATE`, `APP_AUTOSTART_ON/OFF`, `APP_PLACE`
migrieren. Seam: der semantische Launcher-Mutationsport der Invocation-Bindings.

**Der geteilte Vertrag.** `APP_AUTOSTART_ON` und `APP_AUTOSTART_OFF` sind fachlich
**dieselbe** Operation und teilen `launcher.app.autostart.set`; sie unterscheiden sich
nur im booleschen `enabled`. `_DelegatedAutostart` wählt danach den passenden
Legacy-Executor. Damit gilt §A2.2 exakt: **22 Actions auf 21 eindeutige Namen** — es
werden nicht 22 Namen erzwungen.

**Einziger Writer.** Die Tests fangen die Absicht ab und prüfen den **Typ** des Intents
(`SetAutostart`, `ActivateProfile`, `SetPlacement`) samt `kind`. Ein vorberechneter
Voll-Block würde diese Zusicherung nicht erfüllen (RFC-0003).

**Erstes beobachtetes ROT.** 27 Fehler (`UnknownCapability`).

**Mutationen.** M32 geteilter Vertrag aufgebrochen · M33 boolescher Eingabewert ignoriert ·
M34 `OFF` sendet `True` · M35 Profil-Aktivierung ohne `local-write` — **alle vier ROT**.

**Meilenstein.** Nach diesem Slice ist die Action-Zuordnung **22/22 vollständig**.
Der frühere Test „eine nicht migrierte Action nimmt den Fallback" hat damit kein Subjekt
mehr. Statt ihn zu streichen, ist er in seine **stärkere** Umkehrung überführt: *keine*
Action nimmt den Fallback noch. Der Fallback-Code selbst fällt in Slice 12.

**Regression.** 1148 Tests OK.

**Rollback.** `git revert` — die fünf Actions fallen auf `execute_action` zurück, und der
Umkehrtest müsste mit zurückgenommen werden.

**Restrisiko.** Keines über die bereits genannten hinaus; `app_launcher.launch` bleibt
allowlist-gebunden wie zuvor.

---

## Slice 8 — Gemeinsame Launcher-REST-Adapter

**Ziel und Seam.** Vier Routen (`/commands/app/open`, `/launcher/apps/{id}/toggle`,
`/launcher/apps/{id}/placement`, `/launcher/profiles/{id}/activate`) über **dieselben**
Verträge wie die Stimme führen. Seam: `server._launcher_capability`.

**Erstes beobachtetes ROT.** Von 19 Tests scheiterten genau **2** — die beiden, die
belegen, dass die Routen den Coordinator umgehen. Die übrigen 17 charakterisierten das
Ist-Verhalten (403/400/404/Body/Status) und mussten grün bleiben, was sie taten.

**Eine Ausführung, zwei Projektionen.** `_DelegatedLauncherMutation` legt einen
mitschreibenden Wrapper um den semantischen Mutationsport: die Stimme liest den fertigen
deutschen Satz, die Route die maschinenlesbare Fehlerliste — aus **demselben** Lauf.
Configuration bleibt einziger Writer; Broadcast und Correlation laufen unverändert über
`persist_launcher_intent`.

**Zwei echte Befunde während der Umsetzung:**

1. **Ein belegter Transportunterschied.** `_exec_profile_activate` bricht ab, wenn das
   Profil bereits aktiv ist; die REST-Route hat dagegen **immer** persistiert und
   `launcher_changed` gebroadcastet. Der Legacy-Golden-Test pinnt genau dieses Broadcast
   und **hing** nach der naiven Zusammenlegung (er wartete ewig auf das ausbleibende
   Frame). Das ist ein Unterschied in der **Absicht**, nicht in der Fachlichkeit — er steht
   jetzt als typisiertes `force`-Eingabefeld im Vertrag, nicht als transportabhängige
   zweite Wahrheit. Voice sendet `force=False`, die Route `force=True`.
2. **Die Ziel-Evidenz wird geteilt, nicht kopiert.** Die Launcher-Verträge tragen
   `network-read` (TTS), womit `_safe_target` greift. `capability.target_evidence` ist
   deshalb **öffentlich**: eine zweite Kopie der Fest-vs-modellgesteuert-Unterscheidung in
   der HTTP-Schicht wäre genau die zweite Wahrheit, die §A2.3 verbietet.

**Mutationen.** M36 Route erzwingt nicht mehr (**HANG** = ROT: das Broadcast bleibt aus) ·
M37 Route nimmt falschen Vertrag · M38 Fehlerliste nicht eingefangen. **M38 blieb zunächst
grün** und deckte eine ernste Lücke auf: ohne Einfangen hätte die Route **200 OK auf einen
fehlgeschlagenen Speichervorgang** gemeldet. Nach Ergänzung des Persist-Fehler-Tests sind
alle drei ROT.

**Regression.** 1170 Tests OK.

**Rollback.** `git revert` — die vier Routen kehren zu `_persist_launcher` zurück.

**Restrisiko.** Die Placement-Route kodiert `app_id | monitor | zone` als String, den der
Legacy-Parser wieder zerlegt. Das ist byte-identisch, weil `app_id` ein Slug und
monitor/zone Allowlist-Konstanten sind — ein `|` in einer App-**ID** würde es brechen.
Als Formwart notiert, nicht als offene Lücke.

---

## Slice 9 — Übrige sichere REST-Mutationen

**Ziel und Seam.** `POST /settings`, `POST /music/selection`, `POST /launcher/profiles`,
`POST /launcher/profiles/{id}/duplicate` über den Coordinator führen — unter Erhalt der
empfindlichsten Verträge des Servers.

**Erstes beobachtetes ROT.** 12 Fehler: Census (vier Verträge fehlten) und die drei
Coordinator-Zusicherungen. Die Verhaltenszusicherungen (403/400/404/409/Body) waren
bereits grün und blieben es.

**Eine Strukturentscheidung mit Begründung.** `_live_apply` ist **Runtime-Zustand**, keine
HTTP-Sache: es setzt Persona, Vault-Pfade, Launcher-Registry und Startwarnungen des
laufenden Prozesses. Es ist deshalb nach `Runtime.apply_document` gewandert. Damit
erreicht der Capability-Execute es **ohne einen fünften Binding-Port** — Amendment 2 §A2.4
nennt genau vier, ein fünfter wäre nicht gedeckt gewesen. In `server.py` bleibt ein dünnes
Kompat-Alias.

**Domänenablehnungen sind Ergebnisse.** `ConfigConflict` und `ConfigError` verlassen den
Executor als **Felder** (`conflict`, `error`), nicht als Exceptions. Nur so kann die Route
weiterhin 409 von 500 von 400 unterscheiden, ohne den Coordinator zu umgehen — und nur so
wird ein Konflikt nicht als `FAILED` verwischt.

**Erhaltene Verträge (geprüft).** If-Match/Revision inkl. frischem *und* veraltetem Wert,
`409 Conflict` mit `conflict: true`, `403`, `400` (ungültiges JSON, unbekannter Schlüssel,
schlechter Dateiname, fehlendes Feld), `404`, `applied`/`revision`/`warnings` im Body,
„Profil anlegen aktiviert **nicht**", Broadcast und Correlation.

**Post-Commit-Semantik.** Ein eigener Test lässt `broadcast_health` werfen und belegt, dass
der Commit trotzdem **200** liefert, `assistant_core.CITY` gesetzt bleibt **und** der neue
Wert in der Datei steht: ein gültig persistierter Commit wird durch einen späteren
Broadcast-/Refresh-Fehler **nie** zurückgerollt.

**Scopes.** `settings.update` trägt `config.settings`, `music.selection.set`
`config.music` — `config.launcher` wird nicht für fachfremde Daten missbraucht (geprüft).

**Mutationen.** M40 Konflikt als Erfolg · M41 If-Match ignoriert · M42 `config.launcher`
für Settings missbraucht · M43 Konflikt liefert 200 — **alle vier ROT**.

**Regression.** 1195 Tests OK.

**Rollback.** `git revert`; `Runtime.apply_document` bliebe dabei ungenutzt zurück und
müsste mit zurückgenommen werden.

**Restrisiko.** Keines über die bereits genannten hinaus.

---

## Slice 10 — Context-Refresh vollständig machen

**Ziel und Seam.** Den letzten direkten Refresh-Bypass schließen. Seam:
`assistant_core.process_message`.

**Ausgangsverhalten.** Startup und Settings-Save liefen seit Prompt 19 über
`context.refresh`. Der dritte Auslöser — die Aktivierungsnachricht — rief
[assistant_core.py:431](assistant_core.py#L431) `await asyncio.to_thread(refresh_data)`
**direkt** auf und lief damit an Policy, Timeout, Wirkungsdeklaration und Audit vorbei.

**Erstes beobachtetes ROT.** 2 von 8 Tests: der Capability-Nachweis und der
Quelltext-Wächter. Die übrigen sechs (genau ein Refresh, keine Refresh bei normalen
Nachrichten, Position vor dem Prompt-Bau, kein zusätzlicher Provider-Aufruf) waren bereits
grün — das Ausgangsverhalten war korrekt, nur ungeschützt.

**Minimales GRÜN.** Ein `capabilities.attempt("context.refresh", …)` an **derselben
Stelle**: vor History und Prompt-Bau, damit der Refresh auf *diesen* Prompt wirkt. Die
blockierende Arbeit bleibt im Thread (der Executor selbst nutzt `to_thread`).

**Ein Testbefund.** Der Quelltext-Wächter schlug zunächst auf meinen eigenen **Kommentar**
an, der den alten Aufruf zitiert. Statt den Kommentar umzuformulieren, prüft der Wächter
jetzt nur noch Code — Dokumentation ist kein Bypass.

**Mutationen.** M44 Activate-Refresh entfällt · M45 falscher Vertrag — **beide ROT**.

**Regression.** 1203 Tests OK.

**Rollback.** `git revert`.

**Restrisiko.** Ohne Coordinator (`capabilities is None`, nur in Tests konstruierbar)
findet kein Refresh statt. Produktiv reicht `_run_turn` immer `rt.capabilities` durch.

---

## Slice 11 — Route-Audit und Delete-Ausnahme

**Ziel und Seam.** Ein deterministischer Audit, der jede neue unregistrierte mutierende
Route rot macht. Seam: `server.MUTATING_ROUTE_CAPABILITIES` gegen die **tatsächlich**
registrierten FastAPI-Routen.

**Methodischer Hinweis.** Dieser Slice hat kein Verhaltens-ROT: der Audit beschrieb von
Anfang an korrekt, was ist. Für einen **Wächter** ist das erwartbar — sein Wert liegt
nicht darin, dass er grün startet, sondern darin, dass er bei einer Verletzung rot wird.
Der Beleg ist deshalb ausschließlich mutationsgetrieben.

**Der Audit erhebt aus dem Code, nicht aus einer Zweitliste.** `_actual_mutating_routes()`
liest `server.app.routes` und filtert POST/PUT/PATCH/DELETE. Verglichen wird gegen das
Register — Abweichung in **beide** Richtungen ist ein Fehler.

**Geprüft:** genau **10** mutierende Routen · genau **9** capability-gesteuert · genau
**1** dokumentierte Ausnahme, namentlich `DELETE /launcher/profiles/{profile_id}` · jeder
genannte Vertrag ist registriert · jeder gesteuerte Handler erreicht den Coordinator
tatsächlich (Quelltext) · der Delete-Pfad trägt **keine** Schein-Confirmation
(`confirmed=True`/`Confirmation`/`grant`) · und persistiert weiterhin über den Single
Writer · das Register ist unveränderlich · 22/22 Actions auf 21 Namen.

**Mutationen.** M46 neue mutierende Route ohne Registereintrag · M47 Registereintrag
entfernt · M48 Register zeigt auf unbekannten Vertrag · M49 Delete-Ausnahme wegdefiniert ·
M50 Handler umgeht den Coordinator wieder · M51 Schein-Confirmation im Delete-Pfad —
**alle sechs ROT**.

**Die Ausnahme, ehrlich begründet.** `launcher.profile.delete` bleibt offen, weil der
Zwei-Klick-Dialog **browserlokal** ist und serverseitig nicht überprüft werden kann. Es
gibt keine Preview-/Grant-Laufzeit, die eine echte Bestätigung belegen könnte. Die Route
wird deshalb ausdrücklich **nicht** mit einer Schein-Confirmation versehen — das wäre
Sicherheitstheater. Ziel: **Phase 10**.

**Regression.** 1217 Tests OK.

**Rollback.** `git revert` — Register und Audit entfallen, die Routen bleiben migriert.

---

## Slice 12 — Gespeichertes `risk` und Legacy-Fallback entfernen

**Ziel und Seam.** Die zweite Sicherheitswahrheit auflösen und den produktiven
Rückfallpfad entfernen. Seams: `actions.CONFIRM_ACTIONS`, `ActionSpec.risk`,
`assistant_core.run_action_and_respond`.

**Erstes beobachtetes ROT.** 3 von 10 Tests: gespeichertes Feld, `risk=`-Argument,
Fallback im Quelltext.

**Minimales GRÜN.**
* Das gespeicherte `risk`-Feld und `risk="confirm"` sind entfernt.
* `CONFIRM_ACTIONS` wird aus dem `destructive`-Effekt des kanonischen Vertrags
  abgeleitet — **eine** Wahrheit statt einer handgepflegten Risikospalte daneben.
* `ActionSpec.risk` bleibt als **read-only Property**, die denselben Katalog liest.
  Es gibt keine zweite Risikotabelle und keinen gespeicherten Risikowert.
* Der produktive `asyncio.wait_for(execute_action(...))`-Fallback ist entfernt.

**Der geforderte Beweis (§A2.9).** M52 entfernt den `destructive`-Effekt aus
`memory.forget` — der abgeleitete Confirmation-Status **kippt** und drei Tests werden rot.
Die Ableitung ist damit belastet, nicht dekorativ.

**Zwei Vertragsverschärfungen, bewusst.** `capabilities` ist in `process_message` **und**
`run_action_and_respond` jetzt ein erforderliches Keyword-Argument. Ein Turn ohne
Coordinator wäre exakt der Bypass, den dieser Slice entfernt; ihn als `None` weiter zu
dulden hieße, die Tür offen zu lassen. Der Prompt-19-Test, der `Default None` zusicherte,
ist in seine **Umkehrung** überführt (erforderlich, keyword-only) — planmäßig abgelöst,
nicht gelöscht.

**Ein Befund aus dem Testfall.** `test_action_exception_message_and_traceback_never_logged`
patchte den `ActionSpec`-Executor von SEARCH und lief plötzlich ins Leere: `web.search`
und `memory.forget` trugen als **einzige** noch eine **Kopie** der Fachlogik aus der
Pilotphase statt zu delegieren. Genau das ist Slice 12s Auftrag („bestehende
`execute`-Funktionen nur noch hinter Capability-Adaptern"). Beide delegieren jetzt über
`_Delegated`; die letzten zwei Duplikate sind weg, und der Test greift wieder am richtigen
Seam.

**RFC-0001 bleibt gültig.** `ActionSpec.execute` und `ActionSpec.describe` existieren
unverändert weiter — sie laufen nur noch **hinter** den Adaptern. Prompt-Metadaten wandern
in dieser Phase nicht in den Capability-Vertrag.

**Mutationen.** M52 `destructive` entfernt · M53 Ableitung liefert leere Menge ·
M54 Property immer `low` — **alle drei ROT**.

**Regression.** 1227 Tests OK.

**Rollback.** `git revert` — gespeichertes `risk` und Fallback kehren zurück; die
Signaturverschärfung müsste mit zurückgenommen werden.
