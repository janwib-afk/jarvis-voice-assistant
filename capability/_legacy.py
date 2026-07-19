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

from ._contract import (
    CapabilityContract,
    CapabilityRequest,
    DataClass,
    EffectClass,
    Evidence,
    Health,
    InputSchema,
    OutcomeStatus,
    OutputSchema,
    Preview,
    Provenance,
    Retry,
    Scope,
    Verify,
)

#: ActionSpec.type -> stabiler Capability-Name der migrierten Piloten.
MIGRATED_ACTIONS: dict[str, str] = {
    "SEARCH": "web.search",
    "MEMORY_FORGET": "memory.forget",
}


def is_migrated(action_type: str) -> bool:
    return action_type in MIGRATED_ACTIONS


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


#: Sprechbare Fehlerform je migrierter Capability, falls das Outcome nicht ``ok`` ist —
#: bewahrt das beobachtbare Verhalten des jeweiligen Alt-Pfades.
_FALLBACK_TEXT = {
    "web.search": "Suche fehlgeschlagen: nicht ausführbar.",
    "memory.forget": "Das konnte ich nicht vergessen.",
}


async def run_migrated(coordinator, action, ctx, confirmed: bool = False) -> str:
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
    request = CapabilityRequest(name, Provenance.DERIVED, {"query": action.payload})
    # target_allowed=True spiegelt die FESTEN Provider-/Suchmaschinen-Hosts (Anthropic,
    # DuckDuckGo) — nicht nutzergesteuert. SSRF auf jede tatsaechliche Navigation
    # erzwingt der Transport-Guard (Slice 6). ``confirmed`` kommt ausschliesslich aus
    # dem gesprochenen „Ja" (Operator), nie aus Modellinhalt.
    evidence = Evidence(target_allowed=True, confirmed=confirmed)
    outcome = await coordinator.attempt(request, evidence)
    if outcome.status is OutcomeStatus.OK:
        return outcome.value["text"]
    if outcome.status is OutcomeStatus.TIMEOUT and name == "web.search":
        return "Suche fehlgeschlagen: Zeitüberschreitung."
    # denied/needs/failed/partial/timeout: sprechbare Fehlerform des Alt-Pfades.
    return _FALLBACK_TEXT.get(name, "Das konnte ich nicht ausführen.")
