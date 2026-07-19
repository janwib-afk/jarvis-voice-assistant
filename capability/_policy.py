"""Policy Kernel — OB es darf (RFC-0007 §12, Amendment 1 §A1.5).

``decide(contract, request, evidence, rules) -> Decision`` ist **rein, deterministisch,
total und reihenfolgeunabhaengig** — strukturell derselbe Modultyp wie
``conversation/_core.py``. Kein I/O, keine Uhr, kein Netz, kein Modul-Zustand. Aus
Domaenengruenden wird **nie** geworfen.

Komposition (§12):

* ``deny`` gewinnt vor ``needs``
* ``needs`` akkumuliert als Menge
* ``allow`` nur, wenn weder ``deny`` noch ``needs`` vorliegt

Damit ist die Regelmenge eine **Tabelle** und die Sicherheitslage ein Tabellentest.

**Nur erfuellbare Regeln sind aktiv (D6).** Eine Regel, deren Anforderung in Phase 5
niemand erfuellen kann, wird nicht aktiviert, sondern mit Phasen-Datum in
``DATED_RULES`` gefuehrt. ``unknown`` als "erlaubt" durchzuwinken ist ausdruecklich
abgelehnt — das waere fail-open unter fail-closed-Namen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ._contract import (
    CapabilityContract,
    CapabilityRequest,
    Decision,
    EffectClass,
    Evidence,
    Provenance,
    Requirement,
)


@dataclass(frozen=True)
class Rule:
    """Eine benannte, reine Teilentscheidung.

    ``apply`` liefert ``(denials, requirements)``. Regeln kennen einander nicht und
    duerfen in beliebiger Reihenfolge laufen.
    """
    name: str
    why: str
    apply: Callable[[CapabilityContract, CapabilityRequest, Evidence], tuple]


# ── Aktive Regeln (Phase 5) ─────────────────────────────────────────────────


def _provenance(contract, request, evidence):
    """SI-1/SI-2: untrusted Inhalt autorisiert nie und hebt nie an.

    Wirkungen und Scopes stammen ausschliesslich aus der eingefrorenen Registry
    (Amendment 1 §A1.5) — die Anfrage kann sie nicht beeinflussen. Wirksam bleibt
    hier genau eine Aussage: ``external-write`` ist aus abgeleiteter Quelle
    **hart verweigert**, aus Bedienerquelle **autorisierungspflichtig**.

    Fuer ``network-read`` fuegt Provenance ausdruecklich **nichts** hinzu — sonst
    wuerde jede Sprachsuche bestaetigungspflichtig und das beobachtbare Verhalten
    sich aendern (§28.4).
    """
    if EffectClass.EXTERNAL_WRITE not in contract.effects:
        return (), ()
    if request.provenance is Provenance.DERIVED:
        # Voice/LLM koennen einen Grant nie erfuellen (SI-2) — also gar nicht erst
        # als Anforderung stellen, sondern verweigern.
        return (Requirement.AUTHORIZATION,), ()
    return (), (Requirement.AUTHORIZATION,)


def _confirm_destructive(contract, request, evidence):
    """SI-7: destruktive Wirkung nur nach ausdruecklicher Bestaetigung.

    Erfuellt wird sie ausschliesslich durch eine echte Operator-Bestaetigung
    desselben offenen Conversation-Turns (Amendment 1 §A1.5); Modellinhalt kann
    ``evidence.confirmed`` nicht setzen.
    """
    if EffectClass.DESTRUCTIVE not in contract.effects:
        return (), ()
    if evidence.confirmed:
        return (), ()
    return (), (Requirement.CONFIRMATION,)


def _safe_target(contract, request, evidence):
    """D7: ``network-read`` verlangt ein zulaessiges Ziel.

    Die Policy **deklariert**; erzwungen wird im Transport (Amendment 1 §A1.3).
    ``None`` heisst "nicht festgestellt" und ist fail-closed: es wird zur
    Anforderung, nie zur Erlaubnis.
    """
    if EffectClass.NETWORK_READ not in contract.effects:
        return (), ()
    if evidence.target_allowed is True:
        return (), ()
    if evidence.target_allowed is False:
        return (Requirement.SAFE_TARGET,), ()
    return (), (Requirement.SAFE_TARGET,)


#: Die drei in Phase 5 aktiven Regeln (§12, D6).
ACTIVE_RULES: tuple[Rule, ...] = (
    Rule("provenance", "SI-1/SI-2: untrusted Inhalt autorisiert nie", _provenance),
    Rule("confirm-destructive", "SI-7: destruktiv nur nach Bestaetigung",
         _confirm_destructive),
    Rule("safe-target", "D7: network-read nur auf zulaessiges Ziel", _safe_target),
)

#: Benannt und datiert, aber **nicht aktiv** (D6/R3). Sie stehen hier, damit die
#: Luecke belegt und nicht versehentlich ist — Scheinsicherheit ist der Fehlermodus,
#: den dieses RFC vermeiden will.
DATED_RULES: dict[str, str] = {
    "presence-unlocked": "Phase 9 — braucht Win32-Lock-/RDP-Erkennung",
    "preview-transfer": "Phase 9 — braucht die Screen-/Clipboard-Vorschau-UI",
    "budget": "Phase 6 — gehoert zur Job-Engine",
    "grant": "Phase 10 — Grant-Laufzeit, solange external-write leer ist",
    "connector-principal": "Phase 10 — Connectoren existieren nicht",
}


# ── Die Entscheidungsfunktion ───────────────────────────────────────────────


def decide(contract: CapabilityContract,
           request: CapabilityRequest,
           evidence: Evidence,
           rules=ACTIVE_RULES) -> Decision:
    """Rein, deterministisch, total, reihenfolgeunabhaengig.

    Fuer eine ``TRIVIAL``-Capability faellt hier ``allow`` mit **leerer**
    Anforderungsmenge heraus: der triviale Pfad ueberspringt die Policy nicht —
    er besteht sie mit nichts zu tun (§10).
    """
    denials: set = set()
    requirements: set = set()
    for rule in rules:
        d, r = rule.apply(contract, request, evidence)
        denials.update(d)
        requirements.update(r)
    # deny gewinnt: was verweigert ist, wird nicht zusaetzlich als erfuellbare
    # Anforderung ausgewiesen.
    requirements -= denials
    allowed = not denials and not requirements
    return Decision(allowed=allowed,
                    denials=frozenset(denials),
                    requirements=frozenset(requirements))
