"""
Tests fuer das Tab-Management in browser_tools.py — ohne echten Browser.

``_get_browser`` wird durch einen Fake-Context ersetzt; geprueft wird nur die
Cap-/Recovery-Logik von ``_new_page_capped``.
    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_tools
import capability


class FakePage:
    def __init__(self, ctx):
        self._ctx = ctx
        self._closed = False

    def is_closed(self):
        return self._closed

    async def close(self):
        self._closed = True
        self._ctx.pages.remove(self)


class FakeContext:
    """Ahmt Playwright nach: ``pages`` enthaelt nur offene Tabs in Erstellungsreihenfolge."""

    def __init__(self, fail_times=0):
        self.pages = []
        self.new_page_calls = 0
        self._fail_times = fail_times

    async def new_page(self):
        self.new_page_calls += 1
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("Target page, context or browser has been closed")
        page = FakePage(self)
        self.pages.append(page)
        return page


class NewPageCappedTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_get_browser = browser_tools._get_browser
        self._orig_globals = (browser_tools._pw, browser_tools._browser, browser_tools._context)

    def tearDown(self):
        browser_tools._get_browser = self._orig_get_browser
        browser_tools._pw, browser_tools._browser, browser_tools._context = self._orig_globals

    def _install(self, ctx):
        async def fake_get_browser():
            return ctx
        browser_tools._get_browser = fake_get_browser
        return ctx

    async def test_cap_closes_oldest(self):
        ctx = self._install(FakeContext())
        created = [await browser_tools._new_page_capped() for _ in range(6)]
        self.assertEqual(len(ctx.pages), browser_tools.MAX_TABS)
        self.assertTrue(created[0].is_closed())      # aeltester wurde geschlossen
        self.assertFalse(created[1].is_closed())
        self.assertIs(ctx.pages[-1], created[-1])

    async def test_never_more_than_max_tabs(self):
        ctx = self._install(FakeContext())
        for _ in range(10):
            await browser_tools._new_page_capped()
            self.assertLessEqual(len(ctx.pages), browser_tools.MAX_TABS)

    async def test_manually_closed_pages_do_not_count(self):
        ctx = self._install(FakeContext())
        pages = [await browser_tools._new_page_capped() for _ in range(5)]
        # Nutzer schliesst zwei Tabs von Hand.
        await pages[1].close()
        await pages[2].close()
        await browser_tools._new_page_capped()
        # Kein Tab wurde vom Cap geschlossen — aeltester ist noch offen.
        self.assertFalse(pages[0].is_closed())
        self.assertEqual(len(ctx.pages), 4)

    async def test_recovers_when_new_page_fails_once(self):
        ctx = self._install(FakeContext(fail_times=1))
        page = await browser_tools._new_page_capped()
        self.assertFalse(page.is_closed())
        self.assertEqual(ctx.new_page_calls, 2)      # 1 Fehlschlag + 1 Retry

    async def test_raises_when_new_page_fails_twice(self):
        self._install(FakeContext(fail_times=2))
        with self.assertRaises(RuntimeError):
            await browser_tools._new_page_capped()


class StatusTests(unittest.TestCase):
    def test_status_disconnected_without_browser(self):
        # Ohne gestarteten Browser meldet status() nicht-verbunden — und startet nichts.
        self.assertEqual(browser_tools.status(), {"connected": False})


# Ausschnitt einer echten html.duckduckgo.com-Ergebnisseite (gekuerzt):
# uddg-Redirect, HTML im Titel, ein nicht-http-Treffer (wird verworfen).
_DDG_FIXTURE = """
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fssd%2Dtest&amp;rut=abc123">
       Beste <b>SSD</b> 2026 im Test</a>
  </h2>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://example.org/direkt">Direkter Treffer &amp; mehr</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="javascript:alert(1)">Boese</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.net%2Fdritte">Dritte Quelle</a>
</div>
"""


class ParseDdgHtmlTests(unittest.TestCase):
    def test_parses_titles_and_decodes_redirects(self):
        results = browser_tools.parse_ddg_html(_DDG_FIXTURE, limit=4)
        self.assertEqual(len(results), 3)  # javascript:-Treffer verworfen
        self.assertEqual(results[0]["url"], "https://example.com/ssd-test")
        self.assertEqual(results[0]["title"], "Beste SSD 2026 im Test")
        self.assertEqual(results[1]["url"], "https://example.org/direkt")
        self.assertEqual(results[1]["title"], "Direkter Treffer & mehr")
        self.assertEqual(results[2]["url"], "https://example.net/dritte")

    def test_limit_respected(self):
        results = browser_tools.parse_ddg_html(_DDG_FIXTURE, limit=1)
        self.assertEqual(len(results), 1)

    def test_empty_html(self):
        self.assertEqual(browser_tools.parse_ddg_html("", limit=4), [])
        self.assertEqual(browser_tools.parse_ddg_html("<html>nichts</html>", limit=4), [])


class SearchLinksFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_new_page = browser_tools._new_page_capped
        self._orig_fallback = browser_tools._search_links_fallback
        # Permissiver SSRF-Guard: kein echtes DNS in Unit-Tests; jeder Host loest auf
        # eine oeffentliche IP auf. Die Denylist selbst ist in test_capability_ssrf
        # erschoepfend geprueft.
        self._orig_guard = browser_tools._guard
        browser_tools.configure_guard(
            capability.TargetGuard(resolver=lambda h: ["93.184.216.34"]))

    def tearDown(self):
        browser_tools._new_page_capped = self._orig_new_page
        browser_tools._search_links_fallback = self._orig_fallback
        browser_tools.configure_guard(self._orig_guard)

    async def test_fallback_used_when_browser_fails(self):
        async def broken_page():
            raise RuntimeError("Playwright ist nicht installiert.")

        fallback_result = [{"title": "Fallback", "url": "https://example.com"}]
        calls = []

        async def fake_fallback(query, limit):
            calls.append((query, limit))
            return fallback_result

        browser_tools._new_page_capped = broken_page
        browser_tools._search_links_fallback = fake_fallback

        results = await browser_tools.search_links("ssd test", limit=3)
        self.assertEqual(results, fallback_result)
        self.assertEqual(calls, [("ssd test", 3)])

    async def test_no_fallback_when_browser_delivers(self):
        class FakeLink:
            async def get_attribute(self, name):
                return "https://example.com/browser"

            async def inner_text(self):
                return "Browser-Treffer"

        class FakeLocator:
            async def count(self):
                return 1

            def nth(self, i):
                return FakeLink()

        class FakePage:
            url = "about:blank"

            async def route(self, *a, **kw):
                pass

            async def goto(self, *a, **kw):
                return None

            async def wait_for_timeout(self, ms):
                pass

            def locator(self, sel):
                return FakeLocator()

        async def fake_page():
            return FakePage()

        async def fail_fallback(query, limit):
            raise AssertionError("Fallback darf nicht laufen, wenn der Browser liefert")

        browser_tools._new_page_capped = fake_page
        browser_tools._search_links_fallback = fail_fallback
        # _bring_chromium_to_front startet PowerShell — im Test ueberspringen.
        orig_front = browser_tools._bring_chromium_to_front
        browser_tools._bring_chromium_to_front = lambda: None
        try:
            results = await browser_tools.search_links("ssd test", limit=3)
        finally:
            browser_tools._bring_chromium_to_front = orig_front
        self.assertEqual(results, [{"title": "Browser-Treffer", "url": "https://example.com/browser"}])


class ExtractReadableTests(unittest.TestCase):
    def test_extracts_title_and_text(self):
        html = ("<html><head><title>Beispiel &amp; Co</title></head>"
                "<body><p>Hallo Welt</p></body></html>")
        title, text = browser_tools._extract_readable(html)
        self.assertEqual(title, "Beispiel & Co")
        self.assertIn("Hallo Welt", text)

    def test_removes_script_and_style(self):
        html = ("<body><style>.x{color:red}</style>"
                "<script>alert('geheim')</script><p>Sichtbar</p></body>")
        _, text = browser_tools._extract_readable(html)
        self.assertIn("Sichtbar", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("color:red", text)

    def test_decodes_entities_and_normalizes_whitespace(self):
        _, text = browser_tools._extract_readable("<p>viel\n\n   Abstand &amp; mehr</p>")
        self.assertEqual(text, "viel Abstand & mehr")

    def test_caps_at_max_chars(self):
        html = "<p>" + ("A" * 5000) + "</p>"
        _, text = browser_tools._extract_readable(html, max_chars=100)
        self.assertLessEqual(len(text), 100)


class FetchPageFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_http_scheme(self):
        # Kein Netzaufruf: nicht-http(s)-Schemata werden sofort abgelehnt.
        for url in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"):
            result = await browser_tools.fetch_page_text_fallback(url)
            self.assertIn("error", result)
            self.assertEqual(result["url"], url)


class VisitFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_page = browser_tools._new_page_capped
        self._orig_fetch = browser_tools.fetch_page_text_fallback
        self._orig_guard = browser_tools._guard
        browser_tools.configure_guard(
            capability.TargetGuard(resolver=lambda h: ["93.184.216.34"]))

    def tearDown(self):
        browser_tools._new_page_capped = self._orig_page
        browser_tools.fetch_page_text_fallback = self._orig_fetch
        browser_tools.configure_guard(self._orig_guard)

    async def test_falls_back_when_no_browser(self):
        async def broken_page():
            raise RuntimeError("Playwright ist nicht installiert.")

        called = []

        async def fake_fetch(url, max_chars=5000):
            called.append((url, max_chars))
            return {"title": "F", "url": url, "content": "browserlos gelesen"}

        browser_tools._new_page_capped = broken_page
        browser_tools.fetch_page_text_fallback = fake_fetch
        result = await browser_tools.visit("https://example.com", max_chars=1500)
        self.assertEqual(result["content"], "browserlos gelesen")
        self.assertEqual(called, [("https://example.com", 1500)])

    async def test_falls_back_when_page_op_fails(self):
        class FakePage:
            async def route(self, *a, **kw):
                pass

            async def goto(self, *a, **kw):
                raise RuntimeError("Navigation failed")

            async def close(self):
                pass

        async def fake_page():
            return FakePage()

        async def fake_fetch(url, max_chars=5000):
            return {"title": "F", "url": url, "content": "fallback nach fehler"}

        browser_tools._new_page_capped = fake_page
        browser_tools.fetch_page_text_fallback = fake_fetch
        result = await browser_tools.visit("https://example.com")
        self.assertEqual(result["content"], "fallback nach fehler")

    async def test_returns_original_error_when_fallback_also_fails(self):
        class FakePage:
            async def route(self, *a, **kw):
                pass

            async def goto(self, *a, **kw):
                raise RuntimeError("Navigation kaputt")

            async def close(self):
                pass

        async def fake_page():
            return FakePage()

        async def fake_fetch(url, max_chars=5000):
            return {"error": "auch kaputt", "url": url}

        browser_tools._new_page_capped = fake_page
        browser_tools.fetch_page_text_fallback = fake_fetch
        result = await browser_tools.visit("https://example.com")
        self.assertIn("error", result)
        self.assertIn("Navigation kaputt", result["error"])


if __name__ == "__main__":
    unittest.main()
