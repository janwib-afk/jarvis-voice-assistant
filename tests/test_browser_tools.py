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


if __name__ == "__main__":
    unittest.main()
