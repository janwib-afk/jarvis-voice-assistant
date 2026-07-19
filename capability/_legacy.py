"""Legacy-Adapter: ``[ACTION:…]`` -> Capability (RFC-0007 §22, Amendment 1 §A1.1).

Bildet **migrierte** Actions auf Capability-Requests ab und projiziert das ``Outcome``
zurueck auf den rohen Ergebnis-String, den ``assistant_core.run_action_and_respond``
erwartet. Das ``[ACTION:…]``-Wire-Format und ``ActionSpec`` bleiben unveraendert
(RFC-0001 bleibt bindend); der Prompt und die Selbstbeschreibung aendern sich nicht.

In der **Pilotphase** ist genau eine Voice-Action migriert: ``SEARCH`` -> ``web.search``.
Die uebrigen 20 Actions laufen unveraendert ueber ``execute_action`` (Prompt 20,
Amendment 1 §A1.1).

``execute`` importiert ``browser_tools`` **lazy**, damit ``import capability`` I/O-frei
und leicht bleibt.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ._contract import (
    CapabilityContract,
    CapabilityRequest,
    DataClass,
    EffectClass,
    Evidence,
    Field,
    Health,
    InputSchema,
    InvocationBindings,
    OutcomeStatus,
    OutputSchema,
    Preview,
    Provenance,
    Retry,
    Scope,
    Verify,
)

#: ActionSpec.type -> stabiler Capability-Name (Amendment 2 §A2.2).
#: Mehrere Actions duerfen denselben semantischen Vertrag benutzen — es werden
#: ausdruecklich **nicht** 22 verschiedene Namen erzwungen.
#: **Unveraenderlich**: die Zuordnung ist eine Sicherheitsentscheidung. Waere sie
#: zur Laufzeit biegbar, koennte ein Pfad still an seinem Vertrag vorbeigefuehrt
#: werden (Amendment 2 §A2.7).
MIGRATED_ACTIONS: Mapping[str, str] = MappingProxyType({
    "SEARCH": "web.search",
    "MEMORY_FORGET": "memory.forget",
    "PROFILE_STATUS": "launcher.profile.status",
    "SESSION_SUMMARY": "conversation.summary",
    "BROWSE": "web.browse",
    "OPEN": "web.open",
    "NEWS": "web.news",
    "RESEARCH": "web.research",
})


def is_migrated(action_type: str) -> bool:
    return action_type in MIGRATED_ACTIONS


@dataclass(frozen=True)
class _Delegated:
    """Fuehrt den bestehenden ``ActionSpec``-Executor **hinter** dem Vertrag aus.

    Die Fachlogik wird nicht kopiert: eine zweite Kopie waere eine zweite Wahrheit,
    die auseinanderlaufen kann. Neu ist ausschliesslich, dass Policy, Timeout,
    Wirkungsdeklaration und Ergebnisprojektion jetzt davor liegen — das Rohergebnis
    bleibt byte-identisch (Amendment 2 §A2.1, Slice 12).

    ``field`` benennt das Eingabefeld, das der Legacy-Executor als String erwartet;
    ``None`` heisst: dieser Pfad hat keine Eingabe.
    """
    action_type: str
    field: str | None = None

    async def __call__(self, payload, ctx):
        import actions
        text = await actions.spec_for(self.action_type).execute(
            payload.get(self.field, "") if self.field else "",
            actions.ActionContext(
                ai=ctx.bindings.ai,
                history=ctx.bindings.history,
                mutate_launcher=ctx.bindings.mutate_launcher,
            ),
        )
        return {"text": text}


async def _exec_web_search(payload, ctx):
    """Deckungsgleich mit ``actions._exec_search``: byte-identisches rohes Ergebnis."""
    import browser_tools
    result = await browser_tools.search_and_read(payload["query"])
    if "error" not in result:
        text = (f"Seite: {result.get('title', '')}\nURL: {result.get('url', '')}"
                f"\n\n{result.get('content', '')[:2000]}")
    else:
        text = f"Suche fehlgeschlagen: {result.get('error', '')}"
    return {"text": text}


def web_search_contract(deps=None) -> CapabilityContract:
    """Der Pilot-Vertrag fuer ``SEARCH``. Version 1 (Amendment 1 §A1.7 G1)."""
    return CapabilityContract(
        name="web.search", version=1, title="Websuche",
        inputs=InputSchema(fields=("query",)),
        output=OutputSchema(fields=("text",)),
        # Folgeeffekte vollstaendig deklariert (Amendment 1 §A1.2): Suche, Summary-LLM
        # und TTS sind network-read; der sichtbare Chromium-Prozess und der
        # PowerShell-SetForegroundWindow-Fokus sind local-execute.
        effects=(EffectClass.NETWORK_READ, EffectClass.LOCAL_EXECUTE),
        reads=(DataClass.PUBLIC,), writes=(),
        scopes=(Scope.WEB,),
        timeout_s=60,  # identisch zu ActionSpec("SEARCH").timeout (Default 60)
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={"query": "wetter"},
        execute=_exec_web_search,
    )


async def _exec_memory_forget(payload, ctx):
    """Deckungsgleich mit ``actions._exec_memory_forget``: byte-identisches Ergebnis."""
    import asyncio
    import memory
    result = await asyncio.to_thread(memory.forget_memory, payload["query"])
    return {"text": result}


def memory_forget_contract(deps=None) -> CapabilityContract:
    """Der Pilot-Vertrag fuer ``MEMORY_FORGET`` (Version 1). Bleibt Confirmation,
    wird nicht zu einem Grant umetikettiert (§16)."""
    return CapabilityContract(
        name="memory.forget", version=1, title="Vergessen",
        inputs=InputSchema(fields=("query",)),
        output=OutputSchema(fields=("text",)),
        # destructive (die Loeschung) + network-read (Summary-LLM + TTS als
        # deklarierte Folgeeffekte, Amendment 1 §A1.2).
        effects=(EffectClass.DESTRUCTIVE, EffectClass.NETWORK_READ),
        reads=(DataClass.PERSONAL,), writes=(DataClass.PERSONAL,),
        scopes=(Scope.VAULT,),
        timeout_s=60,
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={"query": "urlaub"},
        execute=_exec_memory_forget,
    )


async def _exec_profile_rename(payload, ctx):
    """REST-Pilot: Profil umbenennen ueber den EINZIGEN Writer (Configuration).

    Keine direkte Mutationsumgehung — die Persistenz laeuft ausschliesslich durch
    ``runtime.persist_launcher`` (``configuration.mutate``); die Wire-Correlation fuer
    den Broadcast kommt aus den opaken Transport-Metadaten (``ctx.meta``), nicht aus der
    Capability-Eingabe.
    """
    import configuration
    rt = ctx.deps.runtime
    intent = configuration.RenameProfile(payload["profile_id"], payload["name"])
    correlation_id = (ctx.meta or {}).get("correlation_id")
    errors = await rt.persist_launcher(intent, "profile", correlation_id)
    return {"errors": tuple(errors)}


def launcher_profile_rename_contract(deps=None) -> CapabilityContract:
    """Der REST-Pilot ``launcher.profile.rename`` (Version 1, Amendment 1 §A1.4).

    Ersetzt ``launcher.profile.delete`` als Pilot: gleiche Adapterform, aber
    ``local-write`` statt ``destructive`` — ohne neue UI, Wire-Form oder Grant-Runtime.
    """
    return CapabilityContract(
        name="launcher.profile.rename", version=1, title="Profil umbenennen",
        inputs=InputSchema(fields=("profile_id", "name")),
        output=OutputSchema(fields=("errors",)),
        effects=(EffectClass.LOCAL_WRITE,),
        reads=(DataClass.LOCAL,), writes=(DataClass.LOCAL,),
        scopes=(Scope.CONFIG_LAUNCHER,),
        timeout_s=15,
        retry=Retry.NEVER, cancellable=False,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={"profile_id": "default", "name": "Neu"},
        execute=_exec_profile_rename,
    )


async def _exec_context_refresh(payload, ctx):
    """Kein Nutzerausloeser: Wetter (wttr.in) + Vault-Scan neu laden.

    Deckungsgleich mit dem bisherigen ``asyncio.to_thread(assistant_core.refresh_data)``;
    die blockierende Arbeit laeuft im Thread und blockiert die Event-Loop nicht.
    """
    import asyncio
    import assistant_core
    await asyncio.to_thread(assistant_core.refresh_data)
    return {}


def context_refresh_contract(deps=None) -> CapabilityContract:
    """Der Pilot ``context.refresh`` (Version 1) — Serverstart und Post-Settings-Save.

    Vollstaendig deklariert (Amendment 1 §A1.2): network-read (wttr.in) und
    read-sensitive (Vault-Scan). Kein Nutzerausloeser (§2.6.3); Provenance ``operator``
    (systeminitiiert, nicht aus untrusted Inhalt abgeleitet).
    """
    return CapabilityContract(
        name="context.refresh", version=1, title="Kontextdaten aktualisieren",
        inputs=InputSchema(fields=()),
        output=OutputSchema(fields=()),
        effects=(EffectClass.NETWORK_READ, EffectClass.READ_SENSITIVE),
        reads=(DataClass.PUBLIC, DataClass.PERSONAL), writes=(),
        scopes=(Scope.WEB, Scope.VAULT),
        timeout_s=30,
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={},
        execute=_exec_context_refresh,
    )


def launcher_profile_status_contract(deps=None) -> CapabilityContract:
    """``PROFILE_STATUS`` — rein lokaler Launcher-Lesepfad (Slice 1 Tracer).

    ``network-read`` steht hier, weil ``speaks_result=True`` das Ergebnis direkt
    ueber ElevenLabs-TTS spricht: ein deklarierter Folgeeffekt, kein Primaereffekt
    (Amendment 2 §A2.5 — "sechs Launcher-Actions sprechen das Ergebnis direkt").
    """
    return CapabilityContract(
        name="launcher.profile.status", version=1, title="Profil-Status",
        inputs=InputSchema(fields=(Field("profile_query", str, required=False),)),
        output=OutputSchema(fields=(Field("text", str),)),
        effects=(EffectClass.READ_LOCAL, EffectClass.NETWORK_READ),
        reads=(DataClass.LOCAL,), writes=(),
        scopes=(Scope.CONFIG_LAUNCHER, Scope.APPS),
        timeout_s=15,  # identisch zu ActionSpec("PROFILE_STATUS").timeout
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={"profile_query": ""},
        execute=_Delegated("PROFILE_STATUS", "profile_query"),
    )


def conversation_summary_contract(deps=None) -> CapabilityContract:
    """``SESSION_SUMMARY`` — braucht den unveraenderlichen History-Snapshot (Tracer).

    Der Verlauf ist ``personal``: er enthaelt alles, was der Nutzer in der Sitzung
    gesagt hat. Damit ist der Vertrag ``governed``, nicht ``trivial``.
    """
    return CapabilityContract(
        name="conversation.summary", version=1, title="Sitzungsfazit",
        inputs=InputSchema(fields=()),
        output=OutputSchema(fields=(Field("text", str),)),
        # network-read: Summary-LLM (summary_task) + TTS (Amendment 2 §A2.5).
        effects=(EffectClass.NETWORK_READ, EffectClass.READ_LOCAL),
        reads=(DataClass.PERSONAL,), writes=(),
        scopes=(Scope.CONVERSATION,),
        timeout_s=60,
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture={},
        execute=_Delegated("SESSION_SUMMARY"),
    )


# ── Web-Pfade (Phase 5C Slice 3) ────────────────────────────────────────────


def _web_contract(name, title, action_type, *, field, effects, reads, writes,
                  timeout_s, fixture, scopes=(Scope.WEB,)) -> CapabilityContract:
    """Gemeinsame Form der vier Web-Vertraege — die Wirkungen bleiben je Pfad eigen."""
    return CapabilityContract(
        name=name, version=1, title=title,
        inputs=InputSchema(fields=(Field(field, str),) if field else ()),
        output=OutputSchema(fields=(Field("text", str),)),
        effects=effects, reads=reads, writes=writes, scopes=scopes,
        timeout_s=timeout_s,
        retry=Retry.NEVER, cancellable=True,
        preview=Preview.NONE, verify=Verify.SELF_REPORTED, health=Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms", "effects"),
        fixture=fixture,
        execute=_Delegated(action_type, field),
    )


def web_browse_contract(deps=None) -> CapabilityContract:
    """``BROWSE`` — eine **modellgesteuerte** URL lesen (§A2.6)."""
    return _web_contract(
        "web.browse", "Seite lesen", "BROWSE", field="url",
        # network-read (Abruf + Summary-LLM + TTS) und local-execute (der
        # sichtbare Chromium-Prozess samt Fokuswechsel).
        effects=(EffectClass.NETWORK_READ, EffectClass.LOCAL_EXECUTE),
        reads=(DataClass.PUBLIC,), writes=(),
        timeout_s=60, fixture={"url": "https://example.test/"})


def web_open_contract(deps=None) -> CapabilityContract:
    """``OPEN`` — eine **modellgesteuerte** URL sichtbar oeffnen (§A2.6)."""
    return _web_contract(
        "web.open", "Browser öffnen", "OPEN", field="url",
        effects=(EffectClass.NETWORK_READ, EffectClass.LOCAL_EXECUTE),
        reads=(DataClass.PUBLIC,), writes=(),
        timeout_s=60, fixture={"url": "https://example.test/"})


def web_news_contract(deps=None) -> CapabilityContract:
    """``NEWS`` — **festes** Ziel (worldmonitor.app), im Code, nie in der Eingabe."""
    return _web_contract(
        "web.news", "Nachrichten", "NEWS", field=None,
        effects=(EffectClass.NETWORK_READ, EffectClass.LOCAL_EXECUTE),
        reads=(DataClass.PUBLIC,), writes=(),
        timeout_s=60, fixture={})


def web_research_contract(deps=None) -> CapabilityContract:
    """``RESEARCH`` — feste Sucheinstiegs-Quelle, danach entdeckte Links.

    ``local-write``/``writes personal`` stehen hier, weil der Autosave des
    Rechercheergebnisses in die persoenliche Inbox ein deklarierter Folgeeffekt
    dieser Capability ist (Amendment 2 §A2.5) — er laeuft in ``_finish_research``
    und darf deshalb nach einem Nicht-Erfolg nicht stattfinden.
    """
    return _web_contract(
        "web.research", "Recherche", "RESEARCH", field="query",
        effects=(EffectClass.NETWORK_READ, EffectClass.LOCAL_EXECUTE,
                 EffectClass.LOCAL_WRITE),
        reads=(DataClass.PUBLIC,), writes=(DataClass.PERSONAL,),
        scopes=(Scope.WEB, Scope.VAULT),
        timeout_s=180, fixture={"query": "thema"})


#: Capabilities mit **festen**, im Code stehenden Provider-Zielen. Ihre Ziel-URL
#: kommt nie aus Eingabe oder Modellinhalt; die SSRF-Pruefung der tatsaechlichen
#: Navigation erledigt der Transport-Guard (Amendment 2 §A2.6).
_FIXED_TARGET_CAPS = frozenset({"web.search", "web.news", "web.research"})

#: Capabilities mit **nutzer-/modellgesteuerter** URL. Sie brauchen eine vom
#: runtime-eigenen ``TargetGuard`` ABGELEITETE Evidenz — nie eine behauptete.
_URL_FIELD = {"web.browse": "url", "web.open": "url"}


async def _target_evidence(coordinator, name: str, payload: dict) -> bool | None:
    """``True`` erlaubt, ``False`` verworfen, ``None`` unbekannt (fail-closed).

    ``None`` fuehrt in der Policy zu ``needs:safe-target`` und damit zu einem
    Nicht-Erfolg — ohne Guard gibt es keine Evidenz, und ohne Evidenz keine
    Navigation.

    ``check_url`` loest DNS **blockierend** auf. Es laeuft deshalb in einem
    Thread — genau wie in ``guarded_goto``/``install_page_guard``. Direkt auf der
    Event-Loop haette ein langsamer DNS-Server die WS-Empfangsschleife angehalten.
    """
    if name in _FIXED_TARGET_CAPS:
        return True
    field = _URL_FIELD.get(name)
    if field is None:
        return True
    guard = getattr(getattr(coordinator, "deps", None), "target_guard", None)
    if guard is None:
        return None
    import asyncio
    verdict = await asyncio.to_thread(guard.check_url, payload.get(field) or "")
    return verdict.allowed


#: Eingabeform je Action. Fehlt ein Eintrag, gilt die Pilotform ``{"query": payload}``.
_PAYLOAD_BUILDERS = {
    "PROFILE_STATUS": lambda a: {"profile_query": a.payload or ""},
    "SESSION_SUMMARY": lambda a: {},
    "BROWSE": lambda a: {"url": a.payload},
    "OPEN": lambda a: {"url": a.payload},
    "NEWS": lambda a: {},
    "RESEARCH": lambda a: {"query": a.payload},
}


def _payload_for(action) -> dict:
    build = _PAYLOAD_BUILDERS.get(action.type)
    return build(action) if build else {"query": action.payload}


#: Sprechbare Fehlerform je migrierter Capability, falls das Outcome nicht ``ok`` ist —
#: bewahrt das beobachtbare Verhalten des jeweiligen Alt-Pfades.
_FALLBACK_TEXT = {
    "web.search": "Suche fehlgeschlagen: nicht ausführbar.",
    "memory.forget": "Das konnte ich nicht vergessen.",
    "launcher.profile.status": "Den Profil-Status konnte ich nicht abrufen.",
    "conversation.summary": "Die Sitzung konnte ich nicht zusammenfassen.",
    "web.browse": "Seite nicht erreichbar: Ziel nicht zulässig.",
    "web.open": "Das konnte ich nicht öffnen.",
    "web.news": "News konnten nicht geladen werden.",
    "web.research": "Recherche fehlgeschlagen: nicht ausführbar.",
}

#: Letzte Zuflucht: jeder Ausgang hat einen sprechbaren Text — nie ein leerer String.
_GENERIC_FALLBACK = "Das konnte ich nicht ausführen."


def _fallback_text(name: str) -> str:
    return _FALLBACK_TEXT.get(name) or _GENERIC_FALLBACK


def _bindings(ctx) -> InvocationBindings:
    """Die schmalen Ports aus dem request-scoped ``ActionContext`` (Amendment 2 §A2.4).

    Ausschliesslich die vier deklarierten Ports werden uebernommen — die Runtime,
    die Session und der Server bleiben aussen vor.
    """
    return InvocationBindings(
        ai=getattr(ctx, "ai", None),
        history=getattr(ctx, "history", ()),
        mutate_launcher=getattr(ctx, "mutate_launcher", None),
        feedback=getattr(ctx, "feedback", None),
    )


@dataclass(frozen=True)
class LegacyResult:
    """Interne typisierte Projektion eines ``Outcome`` (Amendment 2 §A2.7).

    **Kein Wire-Format**: sie verlaesst den Prozess nie. Ihr einziger Zweck ist,
    dem Legacy-Adapter zu sagen, ob ein Erfolg vorliegt — vorher trug der
    migrierte Pfad nur einen String, und ein ``denied`` sah am Draht aus wie ein
    gelungenes ``done``.
    """
    text: str
    status: OutcomeStatus
    error_type: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is OutcomeStatus.OK

    @property
    def degraded(self) -> bool:
        """``partial`` — ausdruecklich degradiert, nie uneingeschraenkter Erfolg."""
        return self.status is OutcomeStatus.PARTIAL


async def run_migrated(coordinator, action, ctx,
                       confirmed: bool = False) -> LegacyResult:
    """Eine migrierte Action ueber den Coordinator fuehren; ``Outcome`` -> roher String.

    Provenance ist **derived**: ein ``[ACTION:…]`` stammt aus der LLM-Antwort — zwischen
    Nutzer und Tag liegt das Modell (§14). Der Coordinator ist der **einzige**
    Timeout-Owner dieses Pfades (Amendment 1 §A1.6 F1): hier gibt es kein zweites
    ``asyncio.wait_for``.

    ``confirmed`` traegt die **echte** Operator-Bestaetigung desselben offenen
    Conversation-Turns (das gesprochene „Ja"): nur sie erfuellt die
    ``needs:confirmation`` einer destruktiven Capability. Modellinhalt setzt sie nie
    (§16, Amendment 1 §A1.5).
    """
    name = MIGRATED_ACTIONS[action.type]
    payload = _payload_for(action)
    request = CapabilityRequest(name, Provenance.DERIVED, payload)
    # target_allowed=True spiegelt die FESTEN Provider-/Suchmaschinen-Hosts (Anthropic,
    # DuckDuckGo) — nicht nutzergesteuert. SSRF auf jede tatsaechliche Navigation
    # erzwingt der Transport-Guard (Slice 6). ``confirmed`` kommt ausschliesslich aus
    # dem gesprochenen „Ja" (Operator), nie aus Modellinhalt.
    evidence = Evidence(
        target_allowed=await _target_evidence(coordinator, name, payload),
        confirmed=confirmed)
    outcome = await coordinator.attempt(request, evidence, bindings=_bindings(ctx))
    if outcome.status is OutcomeStatus.OK:
        return LegacyResult(outcome.value["text"], outcome.status)
    if outcome.status is OutcomeStatus.PARTIAL and outcome.value:
        # Degradiert: das Teilergebnis ist echt, aber es ist kein voller Erfolg.
        text = outcome.value.get("text") or _fallback_text(name)
        return LegacyResult(text, outcome.status)
    if outcome.status is OutcomeStatus.TIMEOUT and name == "web.search":
        return LegacyResult("Suche fehlgeschlagen: Zeitüberschreitung.",
                            outcome.status)
    # denied/needs/failed/partial/timeout/cancelled: sprechbare Fehlerform des
    # Alt-Pfades — der Text bleibt erhalten, nur der falsche Erfolg faellt weg.
    return LegacyResult(_fallback_text(name), outcome.status,
                        error_type=outcome.error_type)
