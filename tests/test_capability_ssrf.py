"""SSRF-Transport — TargetGuard + beide Transportfamilien (RFC-0007 §21, Amendment 1 §A1.3).

Der reine ``TargetGuard`` prueft die **tatsaechlich aufgeloeste** Adresse; zwei
Produktionsadapter (httpx + Playwright) erzwingen ihn vor jedem Request und jedem
Redirect-/Navigations-Hop. Getestet ausschliesslich mit **injiziertem Resolver** und
kontrollierten Transport-/Playwright-Doubles — **niemals echtes Internet**.
"""
import asyncio
import unittest

import tests  # noqa: F401

import capability as cap


def _guard(mapping):
    """TargetGuard mit injiziertem Resolver: host -> Liste aufgeloester IPs."""
    def _resolve(host):
        if host in mapping:
            return list(mapping[host])
        raise OSError(f"kein Eintrag: {host}")
    return cap.TargetGuard(resolver=_resolve)


class TargetGuardDenylistTests(unittest.TestCase):
    """Jede Denylist-Kategorie mit erlaubendem UND verweigerndem Fall (§21)."""

    def test_public_ipv4_is_allowed(self):
        g = _guard({"example.com": ["93.184.216.34"]})
        self.assertTrue(g.check_url("https://example.com/x").allowed)

    def test_public_ipv6_is_allowed(self):
        g = _guard({"v6.example": ["2606:2800:220:1:248:1893:25c8:1946"]})
        self.assertTrue(g.check_url("https://v6.example/").allowed)

    def test_loopback_v4_is_denied(self):
        g = _guard({"local.test": ["127.0.0.1"]})
        self.assertFalse(g.check_url("http://local.test/").allowed)

    def test_loopback_v6_is_denied(self):
        g = _guard({"local6.test": ["::1"]})
        self.assertFalse(g.check_url("http://local6.test/").allowed)

    def test_rfc1918_ranges_are_denied(self):
        for ip in ("10.0.0.5", "172.16.3.4", "192.168.1.1"):
            with self.subTest(ip=ip):
                g = _guard({"h": [ip]})
                self.assertFalse(g.check_url("http://h/").allowed)

    def test_link_local_is_denied(self):
        for ip in ("169.254.10.20", "fe80::1"):
            with self.subTest(ip=ip):
                g = _guard({"h": [ip]})
                self.assertFalse(g.check_url("http://h/").allowed)

    def test_ipv6_ula_is_denied(self):
        g = _guard({"h": ["fc00::1"]})
        self.assertFalse(g.check_url("http://h/").allowed)

    def test_cloud_metadata_is_denied(self):
        g = _guard({"metadata": ["169.254.169.254"]})
        self.assertFalse(g.check_url("http://metadata/").allowed)

    def test_ipv4_mapped_loopback_is_denied(self):
        # ::ffff:127.0.0.1 muss wie 127.0.0.1 behandelt werden.
        g = _guard({"h": ["::ffff:127.0.0.1"]})
        self.assertFalse(g.check_url("http://h/").allowed)

    def test_jarvis_self_access_is_hard_blocked(self):
        g = _guard({"h": ["127.0.0.1"]})
        self.assertFalse(g.check_url("http://h:8340/").allowed)
        # auch als Literal-IP
        self.assertFalse(g.check_url("http://127.0.0.1:8340/").allowed)


class TargetGuardResolutionTests(unittest.TestCase):
    """Literal-IP, localhost, gemischte DNS-Antworten (§21)."""

    def test_literal_public_ip_is_allowed(self):
        g = _guard({})  # Literal-IP braucht keinen Resolver-Eintrag
        self.assertTrue(g.check_url("https://93.184.216.34/").allowed)

    def test_literal_private_ip_is_denied(self):
        g = _guard({})
        self.assertFalse(g.check_url("http://10.1.2.3/").allowed)

    def test_localhost_name_is_denied(self):
        g = _guard({"localhost": ["127.0.0.1"]})
        self.assertFalse(g.check_url("http://localhost/").allowed)

    def test_mixed_dns_answer_with_one_private_ip_is_denied(self):
        # Ein oeffentlicher UND ein privater Record -> Ziel wird abgelehnt.
        g = _guard({"rebind.test": ["93.184.216.34", "127.0.0.1"]})
        self.assertFalse(g.check_url("https://rebind.test/").allowed)

    def test_unresolvable_host_is_denied_not_crashed(self):
        g = _guard({})
        v = g.check_url("https://does-not-resolve.invalid/")
        self.assertFalse(v.allowed)


class TargetGuardUrlShapeTests(unittest.TestCase):
    """Userinfo, Ports, ungueltige Hosts und Schemas (§21)."""

    def test_non_http_schemes_are_denied(self):
        g = _guard({"h": ["93.184.216.34"]})
        for url in ("file:///etc/passwd", "gopher://h/", "data:text/plain,x",
                    "javascript:alert(1)", "ftp://h/"):
            with self.subTest(url=url):
                self.assertFalse(g.check_url(url).allowed)

    def test_userinfo_is_rejected(self):
        g = _guard({"example.com": ["93.184.216.34"]})
        self.assertFalse(g.check_url("https://user:pass@example.com/").allowed)
        self.assertFalse(g.check_url("https://evil@example.com/").allowed)

    def test_missing_host_is_denied(self):
        g = _guard({})
        self.assertFalse(g.check_url("http:///path").allowed)

    def test_public_target_with_explicit_port_is_allowed(self):
        g = _guard({"example.com": ["93.184.216.34"]})
        self.assertTrue(g.check_url("https://example.com:8443/").allowed)


class HttpxAdapterTests(unittest.TestCase):
    """httpx: Pruefung vor Request und vor jedem Redirect-Hop; kein Auto-Follow."""

    def _client(self, hops):
        """Ein httpx-artiges Double: liefert der Reihe nach die vorgegebenen Antworten."""
        seq = list(hops)
        gets = []

        class _Resp:
            def __init__(self, status, location=None, text=""):
                self.status_code = status
                self.headers = {"location": location} if location else {}
                self.text = text

            @property
            def is_redirect(self):
                return 300 <= self.status_code < 400 and "location" in self.headers

        class _Client:
            follow_redirects = False

            async def get(self, url):
                gets.append(url)
                status, loc, text = seq.pop(0)
                return _Resp(status, loc, text)

        return _Client(), gets

    def test_allowed_target_is_fetched(self):
        g = _guard({"example.com": ["93.184.216.34"]})
        client, gets = self._client([(200, None, "ok")])
        resp = asyncio.run(cap.httpx_guarded_get(g, client, "https://example.com/"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(gets, ["https://example.com/"])

    def test_redirect_to_loopback_is_blocked_before_the_second_request(self):
        g = _guard({"example.com": ["93.184.216.34"], "evil.test": ["127.0.0.1"]})
        client, gets = self._client([(302, "http://evil.test/", ""), (200, None, "x")])
        with self.assertRaises(cap.SSRFBlocked):
            asyncio.run(cap.httpx_guarded_get(g, client, "https://example.com/"))
        # Der zweite (boesartige) Request wurde NIE gesendet.
        self.assertEqual(gets, ["https://example.com/"])

    def test_public_redirect_chain_is_followed_and_rechecked(self):
        g = _guard({"a.test": ["93.184.216.34"], "b.test": ["93.184.216.35"]})
        client, gets = self._client([(302, "https://b.test/", ""), (200, None, "ziel")])
        resp = asyncio.run(cap.httpx_guarded_get(g, client, "https://a.test/"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(gets, ["https://a.test/", "https://b.test/"])

    def test_redirect_chain_is_bounded(self):
        g = _guard({"loop.test": ["93.184.216.34"]})
        client, gets = self._client([(302, "https://loop.test/", "")] * 20)
        with self.assertRaises(cap.SSRFBlocked):
            asyncio.run(cap.httpx_guarded_get(g, client, "https://loop.test/",
                                              max_redirects=3))


class PlaywrightAdapterTests(unittest.TestCase):
    """Playwright: Pruefung vor Navigation, je Request und der verbundenen IP (§A1.3)."""

    def _page(self, resolved_ip="93.184.216.34"):
        routes = {"handler": None, "aborted": [], "continued": []}

        class _Request:
            def __init__(self, url):
                self.url = url

        class _Route:
            def __init__(self, url):
                self.request = _Request(url)

            async def abort(self):
                routes["aborted"].append(self.request.url)

            async def continue_(self):
                routes["continued"].append(self.request.url)

        class _Response:
            def server_addr(self):
                return {"ipAddress": resolved_ip, "port": 443}

        class _Page:
            async def route(self, pattern, handler):
                routes["handler"] = handler

            async def goto(self, url, **kw):
                return _Response()

            async def fire(self, url):
                await routes["handler"](_Route(url))

        return _Page(), routes

    def test_pre_navigation_check_blocks_a_denied_target(self):
        g = _guard({"evil.test": ["10.0.0.1"]})
        page, _ = self._page()
        with self.assertRaises(cap.SSRFBlocked):
            asyncio.run(cap.guarded_goto(g, page, "http://evil.test/"))

    def test_allowed_navigation_proceeds(self):
        g = _guard({"example.com": ["93.184.216.34"]})
        page, _ = self._page(resolved_ip="93.184.216.34")
        resp = asyncio.run(cap.guarded_goto(g, page, "https://example.com/"))
        self.assertIsNotNone(resp)

    def test_connected_ip_is_rechecked_and_aborts_on_mismatch(self):
        # Rebinding: DNS sagt oeffentlich, die tatsaechlich verbundene IP ist privat.
        g = _guard({"example.com": ["93.184.216.34"]})
        page, _ = self._page(resolved_ip="127.0.0.1")
        with self.assertRaises(cap.SSRFBlocked):
            asyncio.run(cap.guarded_goto(g, page, "https://example.com/"))

    def test_route_handler_aborts_denied_requests_including_redirects(self):
        g = _guard({"example.com": ["93.184.216.34"], "evil.test": ["169.254.169.254"]})
        page, routes = self._page()
        asyncio.run(cap.install_page_guard(g, page))
        asyncio.run(page.fire("https://example.com/asset.js"))
        asyncio.run(page.fire("http://evil.test/redirected"))
        self.assertIn("http://evil.test/redirected", routes["aborted"])
        self.assertIn("https://example.com/asset.js", routes["continued"])


class BrowserToolsWiringTests(unittest.TestCase):
    """Belegt, dass der PRODUKTIVE browser_tools-Pfad den Guard tatsaechlich aufruft."""

    def setUp(self):
        import browser_tools
        self.bt = browser_tools
        self._orig = browser_tools._guard

    def tearDown(self):
        self.bt.configure_guard(self._orig)

    def test_search_links_fallback_blocks_a_loopback_host(self):
        # Der Host loest auf Loopback auf -> der httpx-Fallback darf NICHTS holen.
        self.bt.configure_guard(_guard({"html.duckduckgo.com": ["127.0.0.1"]}))
        results = asyncio.run(self.bt._search_links_fallback("x", 3))
        self.assertEqual(results, [])

    def test_fetch_page_text_fallback_blocks_a_private_host(self):
        self.bt.configure_guard(_guard({"intern.test": ["10.0.0.5"]}))
        result = asyncio.run(self.bt.fetch_page_text_fallback("http://intern.test/"))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
