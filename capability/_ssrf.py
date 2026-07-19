"""SSRF-TargetGuard und beide Transportfamilien (RFC-0007 §21, Amendment 1 §A1.3).

**Policy deklariert, Transport erzwingt** (D7). Der reine ``TargetGuard`` prueft die
**tatsaechlich aufgeloeste** Adresse gegen eine Denylist; zwei Produktionsadapter
erzwingen ihn:

* ``httpx_guarded_get`` — prueft vor jedem Request und vor jedem manuell behandelten
  Redirect-Hop; **kein** unkontrolliertes ``follow_redirects=True``.
* ``install_page_guard`` + ``guarded_goto`` — prueft vor jeder Navigation, je Request/
  Redirect (Route-Handler) und zusaetzlich die von Playwright offengelegte **verbundene
  IP** (``response.server_addr``); bei Abweichung Abbruch.

Der Kern (``TargetGuard``) ist rein bis auf **den einen** DNS-Resolver, der injiziert
wird — in Produktion ``socket.getaddrinfo``, im Test kontrolliert. Kein anderes I/O.

**Ehrliche Grenze (D7/R7):** Ohne IP-Pinning wird nicht behauptet, die tatsaechlich
verbundene IP kryptografisch zu binden. DNS-Rebinding bleibt Restrisiko; die
Pro-Verbindungs- und Pro-Hop-Pruefung erschwert es erheblich, schliesst es aber nicht.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urljoin

ALLOWED_SCHEMES = ("http", "https")

#: Cloud-Metadata-Adressen — durch is_link_local bereits gedeckt, hier explizit
#: benannt (Robustheit + Beleg).
_METADATA_IPS = frozenset({"169.254.169.254", "fd00:ec2::254"})

#: Jarvis' eigener lokaler Port — hart blockiert (§21).
JARVIS_SELF_PORT = 8340


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""


class SSRFBlocked(Exception):
    """Ein Ziel wurde als unzulaessig abgewiesen (kein ``Outcome`` — ein harter Abbruch)."""


def _default_resolver(host: str) -> list[str]:
    import socket
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


class TargetGuard:
    """Prueft URLs/IPs gegen die SSRF-Denylist. Rein bis auf den injizierten Resolver."""

    def __init__(self, resolver=_default_resolver, *,
                 allowed_schemes=ALLOWED_SCHEMES, self_port: int = JARVIS_SELF_PORT):
        self._resolve = resolver
        self._schemes = tuple(allowed_schemes)
        self._self_port = self_port

    # ── URL-Ebene ───────────────────────────────────────────────────────────

    def check_url(self, url: str) -> Verdict:
        try:
            parts = urlsplit(url)
        except Exception:
            return Verdict(False, "unparsebare URL")
        if parts.scheme.lower() not in self._schemes:
            return Verdict(False, f"Schema nicht erlaubt: {parts.scheme or 'kein'}")
        # Userinfo ist ein klassischer SSRF-/Phishing-Trick — hart ablehnen.
        if parts.username or parts.password:
            return Verdict(False, "Userinfo im Host nicht erlaubt")
        host = parts.hostname
        if not host:
            return Verdict(False, "kein Host")
        try:
            port = parts.port
        except ValueError:
            return Verdict(False, "ungueltiger Port")

        ips = self._resolve_host(host)
        if ips is None:
            return Verdict(False, f"Host nicht aufloesbar: {host}")
        # Gemischte Antworten: EIN unzulaessiger Record verwirft das ganze Ziel.
        for ip in ips:
            v = self.check_ip(ip, port)
            if not v.allowed:
                return v
        return Verdict(True)

    def ensure(self, url: str) -> None:
        """Wie ``check_url``, wirft aber ``SSRFBlocked`` bei Ablehnung."""
        v = self.check_url(url)
        if not v.allowed:
            raise SSRFBlocked(v.reason)

    # ── IP-Ebene ────────────────────────────────────────────────────────────

    def check_ip(self, ip: str, port: int | None = None) -> Verdict:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return Verdict(False, f"keine IP: {ip}")
        # IPv4-mapped IPv6 (::ffff:127.0.0.1) auf die IPv4 zurueckfuehren.
        mapped = getattr(addr, "ipv4_mapped", None)
        if mapped is not None:
            addr = mapped
        # Defense-in-depth: die folgenden Kategorien ueberlappen bewusst. In CPython
        # ist ``is_private`` ein Catch-all, das Loopback, Link-local und ipv4-mapped
        # bereits einschliesst (empirisch geprueft). Die expliziten Zweige bleiben
        # dennoch: sie machen die Absicht lesbar und halten den Schutz aufrecht, falls
        # sich die ``ipaddress``-Semantik je aendert. Der Jarvis-Selbstzugriff auf
        # 127.0.0.1:8340 ist damit bereits durch ``is_loopback`` hart blockiert (§21).
        if addr.is_loopback:
            return Verdict(False, "Loopback (inkl. Jarvis-Selbstzugriff 127.0.0.1:8340)")
        if addr.is_private:  # RFC1918 (v4) + ULA fc00::/7 (v6) — tragende Pruefung
            return Verdict(False, "privates Netz")
        if addr.is_link_local:  # 169.254/16 + fe80::/10
            return Verdict(False, "Link-local")
        if addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            return Verdict(False, "reservierte/nicht-unicast Adresse")
        if str(addr) in _METADATA_IPS:
            return Verdict(False, "Cloud-Metadata")
        return Verdict(True)

    # ── intern ──────────────────────────────────────────────────────────────

    def _resolve_host(self, host: str):
        # Literal-IP braucht keine DNS-Aufloesung.
        try:
            ipaddress.ip_address(host)
            return [host]
        except ValueError:
            pass
        try:
            ips = list(self._resolve(host))
        except Exception:
            return None
        return ips or None


# ── httpx-Adapter ────────────────────────────────────────────────────────────

async def httpx_guarded_get(guard: TargetGuard, client, url: str, *, max_redirects: int = 5):
    """GET mit manueller, gepruefter Redirect-Behandlung.

    Der ``client`` MUSS ``follow_redirects=False`` haben; die Kette wird hier gefahren
    und **jeder Hop** vor dem Request geprueft (Amendment 1 §A1.3). Der Resolver ist
    blockierend, deshalb laeuft die Pruefung im Thread und blockiert die Event-Loop nicht.
    """
    import asyncio

    current = url
    for _ in range(max_redirects + 1):
        v = await asyncio.to_thread(guard.check_url, current)
        if not v.allowed:
            raise SSRFBlocked(v.reason)
        resp = await client.get(current)
        if getattr(resp, "is_redirect", False):
            location = resp.headers.get("location")
            if not location:
                return resp
            current = urljoin(current, location)
            continue
        return resp
    raise SSRFBlocked("Zu viele Redirects")


# ── Playwright-Adapter ───────────────────────────────────────────────────────

async def install_page_guard(guard: TargetGuard, page) -> None:
    """Route-Handler, der JEDEN Request (inkl. Redirects/Subresourcen) prueft.

    Zulaessige Requests laufen unveraendert weiter (``continue_``); unzulaessige werden
    **abgebrochen** (``abort``). Fuer erlaubte oeffentliche Ziele ist das Verhalten
    damit identisch zu vorher.
    """
    import asyncio

    async def _route(route):
        try:
            v = await asyncio.to_thread(guard.check_url, route.request.url)
        except Exception:
            await route.abort()
            return
        if v.allowed:
            await route.continue_()
        else:
            await route.abort()

    await page.route("**/*", _route)


async def guarded_goto(guard: TargetGuard, page, url: str, **kwargs):
    """Navigation mit Vorab-Pruefung UND Pruefung der verbundenen IP.

    1. Vor der Navigation wird das aufgeloeste Ziel geprueft.
    2. Nach der Antwort wird die von Playwright offengelegte **verbundene IP**
       (``response.server_addr``) geprueft — weicht sie ab (Rebinding), wird abgebrochen.
    """
    import asyncio

    v = await asyncio.to_thread(guard.check_url, url)
    if not v.allowed:
        raise SSRFBlocked(v.reason)
    response = await page.goto(url, **kwargs)
    if response is not None:
        server_addr = response.server_addr
        addr = server_addr() if callable(server_addr) else server_addr
        if addr and addr.get("ipAddress"):
            ipv = guard.check_ip(addr["ipAddress"])
            if not ipv.allowed:
                raise SSRFBlocked(f"Verbundene IP unzulaessig: {ipv.reason}")
    return response
