"""Capability Core — WAS es gibt (RFC-0007 §8/§9/§13, D2).

Rein und I/O-frei: kein Netz, keine Datei, keine Uhr, kein Modul-Global. Der Vertrag
beschreibt eine Faehigkeit vollstaendig — **einschliesslich der Folgewirkungen**, die
heute an ``spec.execute()`` vorbeilaufen (D4, Amendment 1 §A1.2).

Zwei Konstruktionsentscheidungen tragen die Sicherheitslage (D2):

* ``effects``/``reads``/``writes`` haben **keine Defaults**. Sie wegzulassen ist ein
  ``TypeError`` beim Registry-Bau — Schweigen ist strukturell unmoeglich.
* ``tier()`` ist **abgeleitet**, nie deklarierbar. Eine Capability wird billig, indem
  sie billig IST.

``secret`` ist strukturell nicht als Datenklasse eines Vertrags darstellbar (SI-5):
der Wert existiert in der Taxonomie, aber jeder Vertrag, der ihn nennt, wird beim Bau
abgelehnt.
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence


# ── Geschlossene Taxonomie (§13) ────────────────────────────────────────────


class EffectClass(enum.Enum):
    """Was eine Wirkung TUT (SECURITY_REQUIREMENTS §3) — sieben Werte."""
    READ_LOCAL = "read-local"
    READ_SENSITIVE = "read-sensitive"
    NETWORK_READ = "network-read"
    LOCAL_WRITE = "local-write"
    LOCAL_EXECUTE = "local-execute"
    EXTERNAL_WRITE = "external-write"
    DESTRUCTIVE = "destructive"


class DataClass(enum.Enum):
    """Wie schutzbeduerftig die beruehrten Daten sind (§2) — fuenf Werte."""
    PUBLIC = "public"
    LOCAL = "local"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


class Scope(enum.Enum):
    """Ressourcenbereich — WORAN, nicht WAS.

    Die drei ``config.settings``/``config.music``/``conversation`` kommen mit
    Amendment 2 §A2.4 hinzu, weil sie durch die Vollmigration **belegt** sind:
    ``config.launcher`` wird nicht fuer fachfremde Daten missbraucht.
    """
    VAULT = "vault"
    CONFIG_LAUNCHER = "config.launcher"
    CONFIG_SETTINGS = "config.settings"
    CONFIG_MUSIC = "config.music"
    CONVERSATION = "conversation"
    WEB = "web"
    SCREEN = "screen"
    CLIPBOARD = "clipboard"
    APPS = "apps"
    CONTEXT = "context"


class Presence(enum.Enum):
    """Beobachtete Aussage ueber den lokalen Desktop (§15).

    ``UNKNOWN`` ist Default UND Nullwert — fehlende Evidenz ist nie
    "wahrscheinlich entsperrt".
    """
    UNKNOWN = "unknown"
    UNLOCKED = "unlocked"
    LOCKED = "locked"
    REMOTE = "remote"


class Provenance(enum.Enum):
    """Woher die Eingabe stammt (§14). Nicht Identitaet, nicht Praesenz."""
    OPERATOR = "operator"
    DERIVED = "derived"


class Tier(enum.Enum):
    """Abgeleitet aus den Wirkungen — **niemals deklarierbar** (D2)."""
    TRIVIAL = "trivial"
    GOVERNED = "governed"


class Retry(enum.Enum):
    """Deklarative EIGNUNG, keine Engine (§19)."""
    NEVER = "never"
    ON_TIMEOUT = "on_timeout"
    ON_TRANSPORT = "on_transport"


class Preview(enum.Enum):
    NONE = "none"
    TEXT = "text"
    DIFF = "diff"
    TRANSFER = "transfer"


class Verify(enum.Enum):
    NONE = "none"
    SELF_REPORTED = "self-reported"
    OBSERVABLE = "observable"


class Health(enum.Enum):
    """Health ist passiv und kostenfrei (§20) — daher genau ein Wert."""
    PASSIVE = "passive"


class Requirement(enum.Enum):
    """Was eine Policy zusaetzlich verlangt, bevor ausgefuehrt werden darf."""
    CONFIRMATION = "confirmation"
    AUTHORIZATION = "authorization"
    PRESENCE_UNLOCKED = "presence:unlocked"
    PREVIEW = "preview"
    SAFE_TARGET = "safe-target"


class OutcomeStatus(enum.Enum):
    """Geschlossenes Ergebnismodell (§11). Domaenenablehnungen sind Ergebnisse."""
    OK = "ok"
    PARTIAL = "partial"
    DENIED = "denied"
    NEEDS = "needs"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILED = "failed"


#: Geschlossene Allowlist der Audit-Metadaten (§20, Amendment 1 §A1.6).
#: Payloads, Inhalte, URLs, Preview-Hashes und Secrets sind hier strukturell
#: nicht nennbar — ein Vertrag, der etwas anderes auditieren will, wird abgelehnt.
AUDIT_FIELDS = frozenset({"name", "version", "effects", "outcome", "duration_ms"})

#: Wirkungen und Datenklassen, die eine Capability trivial halten (§9).
_TRIVIAL_EFFECTS = frozenset({EffectClass.READ_LOCAL, EffectClass.NETWORK_READ})
_TRIVIAL_READS = frozenset({DataClass.PUBLIC, DataClass.LOCAL})

_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)+$")


# ── Schemata ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Field:
    """Ein typisiertes Schemafeld (Amendment 2 §A2.4).

    ``type=None`` bedeutet **untypisiert** — das ist genau die Form, die ein
    schlichter ``str`` im Schema erzeugt, und haelt die Pilotvertraege aus
    Prompt 19 unveraendert gueltig.
    """
    name: str
    type: type | tuple[type, ...] | None = None
    required: bool = True

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Feldname muss ein nichtleerer String sein.")
        if not isinstance(self.required, bool):
            raise TypeError("required muss bool sein.")

    def check(self, value: Any) -> str | None:
        """``None`` = in Ordnung, sonst der Grund. Rein, ohne Seiteneffekt."""
        if self.type is None:
            return None
        # ``bool`` ist in Python ein ``int``. Fachlich ist es das nie — ein
        # Zahlenfeld darf kein True annehmen (keine implizite Umwandlung).
        if isinstance(value, bool) and self.type is not bool:
            return f"{self.name}: erwartet {_type_name(self.type)}, erhielt bool"
        if not isinstance(value, self.type):
            return (f"{self.name}: erwartet {_type_name(self.type)}, "
                    f"erhielt {type(value).__name__}")
        return None


def _type_name(t) -> str:
    if isinstance(t, tuple):
        return "|".join(sorted(x.__name__ for x in t))
    return t.__name__


def _as_fields(raw) -> tuple[Field, ...]:
    """Nimmt Strings (untypisiert, required) **und** ``Field`` — rueckwaertskompatibel."""
    out = []
    for f in raw:
        out.append(f if isinstance(f, Field) else Field(f))
    names = [f.name for f in out]
    if len(set(names)) != len(names):
        raise ValueError("Doppeltes Feld im Schema.")
    return tuple(out)


class _TypedSchema:
    """Gemeinsame Validierung von Ein- und Ausgabe (Amendment 2 §A2.4).

    Die Fehlermeldungen sind **deterministisch**: alle Verletzungen werden
    sortiert gesammelt, nie in Iterationsreihenfolge eines Dicts gemeldet.
    """
    _MISSING = "Fehlende Eingabefelder"
    _NOUN = "Eingabe"
    _CHECK_UNKNOWN = True

    def _validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise SchemaError(f"{self._NOUN} ist keine Abbildung.")
        missing = sorted(f.name for f in self.fields
                         if f.required and f.name not in payload)
        if missing:
            raise SchemaError(f"{self._MISSING}: {', '.join(missing)}")
        if self._CHECK_UNKNOWN:
            declared = {f.name for f in self.fields}
            unknown = sorted(k for k in payload if k not in declared)
            if unknown:
                raise SchemaError(
                    f"Unbekannte Eingabefelder: {', '.join(unknown)}")
        problems = sorted(
            p for p in (f.check(payload[f.name])
                        for f in self.fields if f.name in payload)
            if p is not None)
        if problems:
            raise SchemaError(f"Typfehler: {'; '.join(problems)}")
        return {f.name: payload[f.name] for f in self.fields if f.name in payload}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)


@dataclass(frozen=True)
class InputSchema(_TypedSchema):
    """Deklarative Eingabeform. Adapter wandeln um, der Core validiert (§8).

    ``fields`` nimmt Strings (untypisiert/required, die Pilotform) **oder**
    ``Field``-Eintraege mit Typ und required/optional.
    """
    fields: tuple

    def __post_init__(self):
        object.__setattr__(self, "fields", _as_fields(self.fields))

    def validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Wirft bei Schemaverstoss — ein Adapter, der Unsinn schickt, ist ein Fehler.

        Der Rueckgabewert ist die kanonische Projektion auf die deklarierten Felder;
        alles Unbekannte wird abgelehnt, nicht stillschweigend mitgeschleppt.
        """
        return self._validate(payload)


@dataclass(frozen=True)
class OutputSchema(_TypedSchema):
    """Deklarative Ergebnisform.

    Unbekannte Felder werden hier **nicht** abgelehnt: das Ergebnis eines
    Executors darf mehr tragen, als der Vertrag verspricht — die Projektion
    schneidet es ohnehin auf die deklarierten Felder zu.
    """
    fields: tuple
    _MISSING = "Fehlende Ergebnisfelder"
    _NOUN = "Ergebnis"
    _CHECK_UNKNOWN = False

    def __post_init__(self):
        object.__setattr__(self, "fields", _as_fields(self.fields))

    def validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._validate(payload)


class SchemaError(Exception):
    """Schemaverstoss eines Adapters — ein Programmierfehler, kein ``Outcome`` (§11)."""


class UnknownCapability(KeyError):
    """Unbekannter Name ist ein Fehler, nie ein Fallback (§8)."""


# ── Der Vertrag (§9) ────────────────────────────────────────────────────────


def _frozen(values, kind: str, enum_type) -> frozenset:
    if isinstance(values, (str, bytes)) or not isinstance(values, (Sequence, set, frozenset)):
        raise TypeError(f"{kind} muss eine Sammlung sein.")
    out = frozenset(values)
    bad = [v for v in out if not isinstance(v, enum_type)]
    if bad:
        raise TypeError(f"{kind} enthaelt Werte ausserhalb der Taxonomie: {bad!r}")
    return out


@dataclass(frozen=True)
class CapabilityContract:
    """Eine benannte, versionierte Faehigkeit mit vollstaendig deklarierten Wirkungen.

    ``effects``, ``reads`` und ``writes`` sind Pflicht (D2) und tragen auch die
    Folgewirkungen — Summary-LLM, TTS, sichtbarer Chromium-Prozess, Fokus, Autosave
    (Amendment 1 §A1.2).
    """
    name: str
    version: int
    title: str
    inputs: InputSchema
    output: OutputSchema
    effects: frozenset
    reads: frozenset
    writes: frozenset
    scopes: frozenset
    timeout_s: float
    retry: Retry
    cancellable: bool
    preview: Preview
    verify: Verify
    health: Health
    audit: tuple[str, ...]
    fixture: Mapping[str, Any]
    execute: Callable | None

    def __post_init__(self):
        if not isinstance(self.name, str) or not _NAME_RE.match(self.name):
            raise ValueError(
                f"Ungueltiger Capability-Name {self.name!r} — erwartet punktiert, "
                "kleingeschrieben (z.B. 'web.search')."
            )
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version muss eine positive ganze Zahl sein.")

        object.__setattr__(self, "effects", _frozen(self.effects, "effects", EffectClass))
        object.__setattr__(self, "reads", _frozen(self.reads, "reads", DataClass))
        object.__setattr__(self, "writes", _frozen(self.writes, "writes", DataClass))
        object.__setattr__(self, "scopes", _frozen(self.scopes, "scopes", Scope))

        if not self.effects:
            raise ValueError(
                f"{self.name}: effects darf nicht leer sein — eine Capability ohne "
                "erklaerte Wirkung ist nicht darstellbar."
            )

        # SI-5: strukturell nicht als Capability-Ein- oder -Ausgabe darstellbar.
        if DataClass.SECRET in self.reads or DataClass.SECRET in self.writes:
            raise ValueError(
                f"{self.name}: 'secret' ist als Datenklasse einer Capability nicht "
                "darstellbar (SI-5) — Secrets sind nie Ein- oder Ausgabe."
            )

        if not isinstance(self.inputs, InputSchema):
            raise TypeError("inputs muss ein InputSchema sein.")
        if not isinstance(self.output, OutputSchema):
            raise TypeError("output muss ein OutputSchema sein.")
        for name_, value, kind in (
            ("retry", self.retry, Retry), ("preview", self.preview, Preview),
            ("verify", self.verify, Verify), ("health", self.health, Health),
        ):
            if not isinstance(value, kind):
                raise TypeError(f"{name_} muss ein {kind.__name__} sein.")
        if not isinstance(self.cancellable, bool):
            raise TypeError("cancellable muss bool sein.")
        if not isinstance(self.timeout_s, (int, float)) or isinstance(self.timeout_s, bool):
            raise TypeError("timeout_s muss eine Zahl sein.")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s muss positiv sein.")

        object.__setattr__(self, "audit", tuple(self.audit))
        unknown_audit = sorted(set(self.audit) - AUDIT_FIELDS)
        if unknown_audit:
            raise ValueError(
                f"{self.name}: Audit-Felder ausserhalb der Allowlist: "
                f"{', '.join(unknown_audit)} — Inhalte, URLs und Hashes sind nie auditierbar."
            )
        object.__setattr__(self, "fixture", MappingProxyType(dict(self.fixture)))

    def tier(self) -> Tier:
        """Abgeleitet, nie deklariert (§9). Niemand kann ``trivial`` behaupten."""
        if (self.effects <= _TRIVIAL_EFFECTS
                and not self.writes
                and self.reads <= _TRIVIAL_READS):
            return Tier.TRIVIAL
        return Tier.GOVERNED


# ── Anfrage, Evidenz, Entscheidung, Ergebnis ────────────────────────────────


@dataclass(frozen=True)
class CapabilityRequest:
    """Ein Ausfuehrungswunsch. Traegt Provenance und Eingabe — sonst nichts, was
    die Policy beeinflusst (Amendment 1 §A1.5)."""
    capability: str
    provenance: Provenance
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.provenance, Provenance):
            raise TypeError("provenance muss ein Provenance-Wert sein.")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class InvocationBindings:
    """Request-spezifische Ports eines Versuchs (Amendment 2 §A2.4).

    Bewusst **winzig, unveraenderlich und abgeschlossen**: genau vier schmale
    Ports, die eine Capability nicht selbst besitzen darf. Es gibt hier
    ausdruecklich **kein** Runtime-/Server-Objekt, **keinen** Service Locator,
    **kein** frei erweiterbares Dependency-Dict, **kein** Session-Dictionary und
    **keine** globale Rueckreferenz.

    * ``ai``              — LLM-Client-Port (prod: Anthropic, Test: Fake)
    * ``history``         — unveraenderlicher Snapshot des Sitzungsverlaufs
    * ``mutate_launcher`` — semantischer Launcher-Mutationsport ``(intent, kind)``
    * ``feedback``        — schmaler autorisierter Rueckmeldeport (nur SCREEN)

    Die Bindings sind **nicht** Teil von ``CapabilityRequest``, Input-Schema,
    Payload, ``meta``, Preview-/Idempotency-Hash, Policy-Entscheidung oder
    Auditdaten. Sie werden nie serialisiert.
    """
    ai: Any = None
    history: tuple = ()
    mutate_launcher: Callable | None = None
    feedback: Callable | None = None

    def __post_init__(self):
        object.__setattr__(self, "history", tuple(self.history))


@dataclass(frozen=True)
class Evidence:
    """Beobachtete Umstaende. ``presence`` ist fail-closed vorbelegt (§15).

    ``confirmed`` bedeutet: eine echte Operator-Bestaetigung desselben offenen
    Conversation-Turns liegt vor (Amendment 1 §A1.5). Modellinhalt kann sie nie setzen.
    """
    presence: Presence = Presence.UNKNOWN
    confirmed: bool = False
    target_allowed: bool | None = None

    def __post_init__(self):
        if not isinstance(self.presence, Presence):
            raise TypeError("presence muss ein Presence-Wert sein.")


@dataclass(frozen=True)
class Decision:
    """Ergebnis der reinen Entscheidungsfunktion (§12)."""
    allowed: bool
    denials: frozenset = frozenset()
    requirements: frozenset = frozenset()

    def __post_init__(self):
        object.__setattr__(self, "denials", frozenset(self.denials))
        object.__setattr__(self, "requirements", frozenset(self.requirements))
        if self.allowed and (self.denials or self.requirements):
            raise ValueError("allow ist nur ohne deny und ohne needs darstellbar.")


@dataclass(frozen=True)
class Outcome:
    """Genau ein Ausgang je Attempt (§11)."""
    status: OutcomeStatus
    value: Mapping[str, Any] | None = None
    denials: frozenset = frozenset()
    requirements: frozenset = frozenset()
    error_type: str | None = None
    done: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.status, OutcomeStatus):
            raise TypeError("status muss ein OutcomeStatus sein.")
        object.__setattr__(self, "denials", frozenset(self.denials))
        object.__setattr__(self, "requirements", frozenset(self.requirements))
        if self.value is not None:
            object.__setattr__(self, "value", MappingProxyType(dict(self.value)))


# ── Registry und passives inspect() ─────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityView:
    """Read-only Projektion fuer UI-Ausgrauen, passives /health und Prompt-Filterung.

    Kostenlos und rein — eine teure Vorabpruefung wuerde unterlassen (D2).
    """
    name: str
    version: int
    title: str
    effects: frozenset
    reads: frozenset
    writes: frozenset
    scopes: frozenset
    tier: Tier
    cancellable: bool
    preview: Preview
    verify: Verify


class Registry:
    """Nach Konstruktion eingefroren. Namen sind eindeutig; Unbekanntes wirft (§8)."""

    def __init__(self, contracts):
        by_name: dict[str, CapabilityContract] = {}
        for c in contracts:
            if not isinstance(c, CapabilityContract):
                raise TypeError("Registry nimmt nur CapabilityContract-Eintraege.")
            if c.name in by_name:
                raise ValueError(
                    f"Doppelter Capability-Name {c.name!r} — Namen werden nie fuer "
                    "andere Wirkungen wiederverwendet."
                )
            by_name[c.name] = c
        self._by_name = MappingProxyType(by_name)

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name) -> bool:
        return name in self._by_name

    def __iter__(self):
        return iter(self._by_name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))

    def get(self, name: str) -> CapabilityContract:
        try:
            return self._by_name[name]
        except KeyError:
            raise UnknownCapability(
                f"Unbekannte Capability {name!r} — kein Fallback."
            ) from None

    def inspect(self, name: str | None = None):
        """Passiv: liest nur Registry-Daten. Keine Ausfuehrung, keine Kosten (§20)."""
        if name is None:
            return tuple(self._view(self._by_name[n]) for n in sorted(self._by_name))
        return self._view(self.get(name))

    @staticmethod
    def _view(c: CapabilityContract) -> CapabilityView:
        return CapabilityView(
            name=c.name, version=c.version, title=c.title,
            effects=c.effects, reads=c.reads, writes=c.writes, scopes=c.scopes,
            tier=c.tier(), cancellable=c.cancellable,
            preview=c.preview, verify=c.verify,
        )
