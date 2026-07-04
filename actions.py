"""
Jarvis V2 — Action-Parsing & Validierung

Kapselt die fragile `[ACTION:...]`-Textauswertung der LLM-Antwort in eine
validierte, testbare Struktur. Bewusst ohne Netzwerk-/Config-Seiteneffekte,
damit es isoliert (ohne Serverstart) getestet werden kann.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Gleiche Regex wie bisher: [ACTION:TYP] optionaler payload bis Zeilenende.
ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)


@dataclass(frozen=True)
class ActionSpec:
    """Alle Metadaten einer Aktion an einer Stelle (Registry-Eintrag).

    - ``payload``: "required" | "optional" | "none"
    - ``is_url``: Payload muss eine gueltige http(s)-URL sein
    - ``risk``: "low" | "confirm" — confirm-Aktionen brauchen ein muendliches Ja
    - ``timeout``: Gesamt-Cap in Sekunden fuer die Ausfuehrung
    - ``is_browser``: Fehler werden dem Frontend als Browser-Problem gemeldet
    - ``summary_task``: aktionsspezifische Aufgabe fuer den Zusammenfassungs-Schritt
      (None = generische Kurz-Zusammenfassung)
    """
    type: str
    label: str
    payload: str = "required"
    is_url: bool = False
    risk: str = "low"
    timeout: int = 60
    is_browser: bool = False
    summary_task: str | None = None
    summary_max_tokens: int = 250


DEFAULT_SUMMARY_TASK = "Fasse die folgenden Informationen KURZ zusammen, maximal 3 Saetze."

# Zentrale Registry: nur hier eingetragene Aktionen werden geparst/ausgefuehrt.
REGISTRY: dict[str, ActionSpec] = {spec.type: spec for spec in (
    ActionSpec("SEARCH", "Websuche", is_browser=True),
    ActionSpec("BROWSE", "Seite lesen", is_url=True, is_browser=True),
    ActionSpec("OPEN", "Browser öffnen", is_url=True, is_browser=True),
    ActionSpec("SCREEN", "Bildschirm ansehen", payload="optional"),
    ActionSpec("NEWS", "Nachrichten", payload="none", is_browser=True),
    ActionSpec(
        "INBOX_READ", "Inbox lesen", payload="none", summary_max_tokens=350,
        summary_task=(
            "Gib einen kurzen, strukturierten Tagesrueckblick ueber die heutigen Notizen: "
            "gruppiere nach Kategorie (Idee, Aufgabe, Termin, Recherche, Erinnerung, Notiz) "
            "und fasse knapp zusammen. Maximal 5 Saetze."
        ),
    ),
    ActionSpec("INBOX_WRITE", "Inbox-Eintrag"),
    ActionSpec("MEMORY_WRITE", "Merken"),
    ActionSpec(
        "RESEARCH", "Recherche", is_browser=True, timeout=180, summary_max_tokens=350,
        summary_task=(
            "Fasse die Rechercheergebnisse aus den Quellen zu einer praezisen Antwort "
            "zusammen. Maximal 5 Saetze. Nenne KEINE URLs im Text."
        ),
    ),
    ActionSpec(
        "CLIPBOARD", "Zwischenablage", payload="optional",
        summary_task=(
            "Fuehre den genannten Auftrag auf dem Inhalt der Zwischenablage aus. "
            "Antworte kurz und praezise."
        ),
    ),
    ActionSpec("CLIPBOARD_NOTE", "Clipboard-Notiz", payload="none"),
    ActionSpec(
        "NOTES_RECENT", "Letzte Notizen", payload="none", summary_max_tokens=350,
        summary_task=(
            "Fasse die zuletzt bearbeiteten Notizen kurz zusammen und nenne dabei die "
            "Notiznamen, damit klar ist woran zuletzt gearbeitet wurde. Maximal 5 Saetze."
        ),
    ),
    ActionSpec(
        "SESSION_SUMMARY", "Sitzungsfazit", payload="none", summary_max_tokens=350,
        summary_task=(
            "Fasse kurz zusammen, was in dieser Sitzung besprochen und erledigt wurde. "
            "Maximal 5 Saetze."
        ),
    ),
)}

# Abgeleitete Views — bestehende Aufrufer/Tests arbeiten weiter mit Sets.
ALLOWED_ACTIONS = frozenset(REGISTRY)
PAYLOAD_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.payload == "required")
NO_PAYLOAD_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.payload == "none")
OPTIONAL_PAYLOAD_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.payload == "optional")
URL_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.is_url)
BROWSER_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.is_browser)

# Aktionen, die erst nach muendlicher Bestaetigung ausgefuehrt werden.
# Aktuell leer — kuenftige riskante Aktionen bekommen risk="confirm" in der
# Registry und sind damit automatisch abgesichert.
CONFIRM_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.risk == "confirm")


def spec_for(action_type: str) -> ActionSpec:
    """Registry-Eintrag einer (bereits validierten) Aktion."""
    return REGISTRY[action_type]


def label_for(action_type: str) -> str:
    """Anzeige-Label; unbekannte Typen fallen auf den Typnamen zurueck."""
    spec = REGISTRY.get(action_type)
    return spec.label if spec else action_type

# Kategorien fuer Inbox-Eintraege; unbekannte/fehlende Kategorie => "Notiz".
INBOX_CATEGORIES = ("Idee", "Aufgabe", "Termin", "Recherche", "Erinnerung")
INBOX_FALLBACK_CATEGORY = "Notiz"

# Hosts, die als lokaler Origin fuer den WebSocket erlaubt sind
_ALLOWED_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Erfasst ein fuehrendes "schema:" (mit oder ohne //). Wird genutzt, um
# gefaehrliche Schemata (javascript:, data:, file: ...) sicher zu erkennen.
_SCHEME_RE = re.compile(r'^([a-zA-Z][a-zA-Z0-9+.\-]*):(.*)$', re.DOTALL)


@dataclass(frozen=True)
class Action:
    """Eine validierte, ausfuehrbare Aktion."""
    type: str
    payload: str = ""


def normalize_url(raw: str) -> str | None:
    """Normalisiert und validiert eine URL.

    - Fehlt das Schema, wird ``https://`` vorangestellt (LLM liefert oft bare Domains).
    - Erlaubt sind ausschliesslich ``http`` und ``https`` (blockt ``javascript:``,
      ``file:``, ``data:`` u.ae.).
    - Gibt die normalisierte URL zurueck oder ``None``, wenn sie ungueltig ist.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    m = _SCHEME_RE.match(raw)
    if m:
        scheme = m.group(1).lower()
        rest = m.group(2)
        if scheme in ("http", "https"):
            # Vollstaendige URL — Authority (netloc) muss vorhanden sein.
            try:
                parsed = urlparse(raw)
            except ValueError:
                return None
            return raw if parsed.netloc else None
        # Kein echtes Schema, sondern "host:port" (rest = nur Ziffern)?
        # Dann unten https:// voranstellen. Sonst ist es ein fremdes Schema
        # (javascript:, data:, file:, mailto: ...) und wird abgelehnt.
        if not rest.isdigit():
            return None

    raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if not parsed.netloc:
        return None
    return raw


def parse_action(text: str) -> tuple[str, Action | None, str | None]:
    """Trennt gesprochenen Text und Aktion aus einer LLM-Antwort.

    Rueckgabe: ``(spoken_text, action_or_None, error_or_None)``.

    - ``spoken_text`` ist die Antwort ohne den Action-Tag.
    - Ist kein Tag vorhanden, sind ``action`` und ``error`` ``None``.
    - Ist der Tag vorhanden aber ungueltig (unbekannter Typ, fehlender Payload,
      ungueltige URL), ist ``action`` ``None`` und ``error`` enthaelt den Grund.
      Der Aufrufer spricht dann nur ``spoken_text`` und fuehrt nichts aus.
    """
    match = ACTION_PATTERN.search(text)
    if not match:
        return text.strip(), None, None

    spoken = text[:match.start()].strip()
    action_type = match.group(1).upper()
    payload = match.group(2).strip()

    if action_type not in ALLOWED_ACTIONS:
        return spoken, None, f"unbekannter Action-Typ: {action_type}"

    if action_type in NO_PAYLOAD_ACTIONS:
        payload = ""
    elif action_type in OPTIONAL_PAYLOAD_ACTIONS:
        pass  # Payload darf leer sein (z.B. SCREEN ohne Kontextfrage)
    elif not payload:
        return spoken, None, f"fehlender Payload fuer {action_type}"

    if action_type in URL_ACTIONS:
        url = normalize_url(payload)
        if url is None:
            return spoken, None, f"ungueltige URL fuer {action_type}"
        payload = url

    return spoken, Action(action_type, payload), None


# Fuehrendes "[Kategorie]" am Anfang eines INBOX_WRITE-Payloads.
_CATEGORY_RE = re.compile(r'^\[([^\]]{1,30})\]\s*(.*)$', re.DOTALL)


def split_inbox_category(payload: str) -> tuple[str, str]:
    """Trennt ein fuehrendes ``[Kategorie]`` vom Eintragstext.

    Rueckgabe: ``(kategorie, text)``. Die Kategorie wird case-insensitiv gegen
    ``INBOX_CATEGORIES`` geprueft; bei unbekannter/fehlender Kategorie oder
    leerem Resttext bleibt der Payload unveraendert und die Kategorie ist
    ``INBOX_FALLBACK_CATEGORY`` — es geht nie Text verloren.
    """
    text = (payload or "").strip()
    m = _CATEGORY_RE.match(text)
    if m:
        candidate = m.group(1).strip()
        rest = m.group(2).strip()
        if rest:
            for cat in INBOX_CATEGORIES:
                if candidate.lower() == cat.lower():
                    return cat, rest
    return INBOX_FALLBACK_CATEGORY, text


# Ja/Nein-Erkennung fuer den Bestaetigungs-Dialog riskanter Aktionen.
_YES_WORDS = frozenset({
    "ja", "jawohl", "jep", "jup", "yes", "genau", "gerne", "bestaetige",
    "bestätige", "einverstanden", "natuerlich", "natürlich", "sicher",
    "ok", "okay", "mach", "tu", "los",
})
_NO_WORDS = frozenset({
    "nein", "ne", "nö", "noe", "nicht", "niemals", "abbrechen", "abbruch",
    "stopp", "stop", "lass", "vergiss", "no", "kein", "keine",
})


def is_confirmation(text: str) -> bool | None:
    """Deutet eine Nutzerantwort als Bestaetigung.

    Rueckgabe: ``True`` (Ja), ``False`` (Nein) oder ``None`` (weder — der
    Aufrufer behandelt die Nachricht dann als normale Anfrage). Verneinungen
    gewinnen: "Nein, mach das nicht" ist ein Nein, obwohl "mach" vorkommt.
    """
    words = re.findall(r"\w+", (text or "").lower())
    if not words:
        return None
    if any(w in _NO_WORDS for w in words[:6]):
        return False
    if words[0] in _YES_WORDS:
        return True
    if len(words) <= 6 and any(w in _YES_WORDS for w in words):
        return True
    return None


def is_allowed_origin(origin: str | None) -> bool:
    """Prueft, ob ein WebSocket-``Origin``-Header lokal (erlaubt) ist.

    Erlaubt nur ``http``/``https`` mit Hostname localhost/127.0.0.1/::1.
    Fehlt der Origin oder ist er fremd, wird ``False`` zurueckgegeben.
    """
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if host is None:
        return False
    return host.lower() in _ALLOWED_ORIGIN_HOSTS


def is_origin_acceptable(origin: str | None, token_valid: bool) -> bool:
    """Origin-Policy fuer den WebSocket-Handshake.

    - Lokale Origins (localhost/127.0.0.1/::1) sind erlaubt (``is_allowed_origin``).
    - Der literale Origin ``"null"`` wird **ausschliesslich** mit gueltigem Token
      akzeptiert. Grund: manche pywebview/WebView2-Sandbox-Kontexte senden ``null``
      statt eines echten Origins; ohne diese Ausnahme koennte sich das Fenster nicht
      verbinden. Das Token (Same-Origin-Secret) verhindert Missbrauch durch Fremde.
    - Ein komplett fehlender Origin (``None``) sowie fremde Hosts bleiben abgelehnt
      (Browser senden bei WebSockets immer einen Origin-Header).
    """
    if is_allowed_origin(origin):
        return True
    if origin == "null" and token_valid:
        return True
    return False
