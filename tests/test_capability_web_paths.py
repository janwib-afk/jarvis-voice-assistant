"""Slice 3 — Web-Pfade BROWSE, OPEN, NEWS, RESEARCH (Amendment 2 §A2.6).

Hier faellt die pauschale ``target_allowed=True``-Zusage der Pilotphase. Ab jetzt gilt:

* **feste** Provider-Ziele (DuckDuckGo, worldmonitor.app) duerfen adapterseitig als
  feste Ziele belegt werden — sie stehen im Code, nicht in der Eingabe;
* **nutzer- oder modellgesteuerte** URLs (``BROWSE``, ``OPEN``) brauchen eine vom
  runtime-eigenen ``TargetGuard`` **abgeleitete** Evidenz;
* Payload und LLM-Inhalt duerfen sich **niemals selbst** als sicher deklarieren.

Kontrollierte Grenzen: ``browser_tools.*`` (Provider) und der injizierte DNS-Resolver
des ``TargetGuard``. **Kein** echter Netzaufruf, keine echte Navigation.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import actions
import capability as cap


#: Ein oeffentlicher Kontroll-Record und ein privater — beide synthetisch.
def _resolver(public=True):
    return lambda host: ["93.184.216.34"] if public else ["127.0.0.1"]


def _guard(public=True):
    return cap.TargetGuard(resolver=_resolver(public))


def _coord(guard=None):
    deps = cap.CapabilityDeps(target_guard=guard or _guard())
    return cap.Coordinator(cap.build_registry(deps), cap.ACTIVE_RULES,
                           audit=lambda *a, **k: None, deps=deps)


class _Action:
    def __init__(self, type_, payload=""):
        self.type = type_
        self.payload = payload


def _ctx():
    return actions.ActionContext()


def _run(coord, action):
    return asyncio.run(cap.run_migrated(coord, action, _ctx()))


class CanonicalMappingTests(unittest.TestCase):
    def test_all_four_web_actions_are_mapped(self):
        self.assertEqual("web.browse", cap.MIGRATED_ACTIONS["BROWSE"])
        self.assertEqual("web.open", cap.MIGRATED_ACTIONS["OPEN"])
        self.assertEqual("web.news", cap.MIGRATED_ACTIONS["NEWS"])
        self.assertEqual("web.research", cap.MIGRATED_ACTIONS["RESEARCH"])


class ByteIdenticalResultTests(unittest.TestCase):
    """Das rohe Ergebnis bleibt exakt das des Alt-Pfades."""

    def test_browse_result_is_byte_identical(self):
        page = {"title": "Titel", "content": "Inhalt. " * 500}

        async def _visit(url, **kw):
            return dict(page)

        with mock.patch("browser_tools.visit", _visit):
            legacy = asyncio.run(
                actions.spec_for("BROWSE").execute("https://x.test/a", _ctx()))
            migrated = _run(_coord(), _Action("BROWSE", "https://x.test/a"))
        self.assertEqual(legacy, migrated.text)
        self.assertTrue(migrated.ok)

    def test_browse_error_wording_is_preserved(self):
        async def _visit(url, **kw):
            return {"error": "timeout"}

        with mock.patch("browser_tools.visit", _visit):
            legacy = asyncio.run(
                actions.spec_for("BROWSE").execute("https://x.test/a", _ctx()))
            migrated = _run(_coord(), _Action("BROWSE", "https://x.test/a"))
        self.assertEqual(legacy, migrated.text)
        self.assertIn("nicht erreichbar", migrated.text)

    def test_open_result_is_byte_identical(self):
        opened = []

        async def _open(url):
            opened.append(url)

        with mock.patch("browser_tools.open_url", _open):
            migrated = _run(_coord(), _Action("OPEN", "https://x.test/z"))
        self.assertEqual("Geöffnet: https://x.test/z", migrated.text)
        self.assertEqual(["https://x.test/z"], opened)

    def test_news_result_is_byte_identical(self):
        async def _news():
            return "World Monitor Nachrichten:\nAlles ruhig."

        with mock.patch("browser_tools.fetch_news", _news):
            legacy = asyncio.run(actions.spec_for("NEWS").execute("", _ctx()))
            migrated = _run(_coord(), _Action("NEWS", ""))
        self.assertEqual(legacy, migrated.text)

    def test_research_result_is_byte_identical(self):
        links = [{"url": f"https://q{i}.test/", "title": f"Q{i}"} for i in range(5)]

        async def _links(q, limit=5):
            return list(links)

        async def _visit(url, max_chars=1500):
            return {"title": f"T-{url}", "content": "Fakten."}

        with mock.patch("browser_tools.search_links", _links), \
                mock.patch("browser_tools.visit", _visit):
            legacy = asyncio.run(
                actions.spec_for("RESEARCH").execute("thema", _ctx()))
            migrated = _run(_coord(), _Action("RESEARCH", "thema"))
        self.assertEqual(legacy, migrated.text)
        self.assertIn(actions.RESEARCH_SOURCE_PREFIX, migrated.text)


class TargetGuardEvidenceTests(unittest.TestCase):
    """§A2.6: modellgesteuerte URLs brauchen abgeleitete Evidenz — nie pauschal True."""

    def test_browse_to_a_private_address_is_denied_and_never_executes(self):
        visited = []

        async def _visit(url, **kw):
            visited.append(url)
            return {"title": "t", "content": "c"}

        # Der Resolver liefert Loopback — der Guard muss das Ziel verwerfen.
        with mock.patch("browser_tools.visit", _visit):
            result = _run(_coord(_guard(public=False)),
                          _Action("BROWSE", "https://intern.test/"))
        self.assertFalse(result.ok, "privates Ziel darf nicht als Erfolg gelten")
        self.assertEqual([], visited, "die Wirkung lief trotz Ablehnung")

    def test_open_to_a_private_address_is_denied_and_never_executes(self):
        opened = []

        async def _open(url):
            opened.append(url)

        with mock.patch("browser_tools.open_url", _open):
            result = _run(_coord(_guard(public=False)),
                          _Action("OPEN", "http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(result.ok)
        self.assertEqual([], opened)

    def test_browse_to_a_public_address_is_allowed(self):
        """Das erlaubte oeffentliche Kontrollziel — sonst waere der Test vakuum."""
        async def _visit(url, **kw):
            return {"title": "ok", "content": "inhalt"}

        with mock.patch("browser_tools.visit", _visit):
            result = _run(_coord(_guard(public=True)),
                          _Action("BROWSE", "https://example.test/"))
        self.assertTrue(result.ok)

    def test_missing_guard_is_fail_closed(self):
        """Ohne Guard gibt es keine Evidenz — und ohne Evidenz keine Navigation."""
        visited = []

        async def _visit(url, **kw):
            visited.append(url)
            return {"title": "t", "content": "c"}

        deps = cap.CapabilityDeps(target_guard=None)
        coord = cap.Coordinator(cap.build_registry(deps), cap.ACTIVE_RULES,
                                audit=lambda *a, **k: None, deps=deps)
        with mock.patch("browser_tools.visit", _visit):
            result = _run(coord, _Action("BROWSE", "https://example.test/"))
        self.assertFalse(result.ok)
        self.assertEqual([], visited)

    def test_dns_resolution_does_not_block_the_event_loop(self):
        """Die Aufloesung ist blockierend — sie gehoert deshalb in einen Thread.

        Liefe ``check_url`` direkt auf der Event-Loop, haette ein langsamer
        DNS-Server die gesamte WS-Empfangsschleife angehalten. Der Beleg: eine
        parallele Coroutine muss waehrend der Aufloesung Fortschritt machen.
        """
        import time

        ticks = []
        ticks_when_resolved = []

        def _slow_resolver(host):
            time.sleep(0.15)
            # Entscheidend ist der Stand GENAU JETZT, nicht am Ende des Laufs:
            # am Ende haetten beide Seiten ohnehin fertig getickt.
            ticks_when_resolved.append(len(ticks))
            return ["93.184.216.34"]

        async def _visit(url, **kw):
            return {"title": "t", "content": "c"}

        async def _ticker():
            for _ in range(30):
                await asyncio.sleep(0.005)
                ticks.append(1)

        async def _both():
            guard = cap.TargetGuard(resolver=_slow_resolver)
            deps = cap.CapabilityDeps(target_guard=guard)
            coord = cap.Coordinator(cap.build_registry(deps), cap.ACTIVE_RULES,
                                    audit=lambda *a, **k: None, deps=deps)
            await asyncio.gather(
                cap.run_migrated(coord, _Action("BROWSE", "https://x.test/"), _ctx()),
                _ticker())

        with mock.patch("browser_tools.visit", _visit):
            asyncio.run(_both())
        self.assertTrue(ticks_when_resolved, "der Resolver wurde nie aufgerufen")
        self.assertGreater(
            ticks_when_resolved[0], 0,
            "die Event-Loop stand waehrend der DNS-Aufloesung still — "
            "check_url gehoert in einen Thread")

    def test_payload_cannot_declare_itself_safe(self):
        """Ein Modell darf sich die Freigabe nicht in die Eingabe schreiben."""
        registry = cap.build_registry(cap.CapabilityDeps(target_guard=_guard()))
        contract = registry.get("web.browse")
        self.assertNotIn("target_allowed", contract.inputs.names)
        self.assertNotIn("safe", contract.inputs.names)

    def test_fixed_provider_targets_need_no_url_evidence(self):
        """NEWS hat ein festes, im Code stehendes Ziel — es steht nie in der Eingabe."""
        async def _news():
            return "Nachrichten."

        # Selbst mit einem Guard, der ALLES verwirft, laeuft der feste Zielpfad:
        # die SSRF-Pruefung dieses Ziels passiert transportseitig beim goto.
        with mock.patch("browser_tools.fetch_news", _news):
            result = _run(_coord(_guard(public=False)), _Action("NEWS", ""))
        self.assertTrue(result.ok)


class ResearchFollowOnTests(unittest.TestCase):
    """RESEARCH-Quellen und Autosave nur im zulaessigen Erfolgsverlauf (§A2.5)."""

    def test_research_without_readable_sources_is_not_a_success_wording(self):
        async def _links(q, limit=5):
            return [{"url": "https://q.test/", "title": "Q"}]

        async def _visit(url, max_chars=1500):
            return {"error": "blockiert"}

        with mock.patch("browser_tools.search_links", _links), \
                mock.patch("browser_tools.visit", _visit):
            result = _run(_coord(), _Action("RESEARCH", "thema"))
        self.assertIn("fehlgeschlagen", result.text)

    def test_research_thin_source_warning_is_preserved(self):
        async def _links(q, limit=5):
            return [{"url": "https://q1.test/", "title": "Q1"},
                    {"url": "https://q2.test/", "title": "Q2"}]

        calls = {"n": 0}

        async def _visit(url, max_chars=1500):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"title": "T", "content": "Fakt."}
            return {"error": "weg"}

        with mock.patch("browser_tools.search_links", _links), \
                mock.patch("browser_tools.visit", _visit):
            result = _run(_coord(), _Action("RESEARCH", "thema"))
        self.assertIn("Quellenlage dünn", result.text)


class WebEffectCensusTests(unittest.TestCase):
    """Wirkungen direkt aus dem Produktionscode erhoben (§A2.5)."""

    def _view(self, name):
        return cap.build_registry(
            cap.CapabilityDeps(target_guard=_guard())).inspect(name)

    def test_browse_declares_network_and_visible_browser(self):
        view = self._view("web.browse")
        self.assertEqual(
            frozenset({cap.EffectClass.NETWORK_READ, cap.EffectClass.LOCAL_EXECUTE}),
            view.effects)

    def test_open_declares_network_and_visible_browser(self):
        view = self._view("web.open")
        self.assertIn(cap.EffectClass.LOCAL_EXECUTE, view.effects)
        self.assertIn(cap.EffectClass.NETWORK_READ, view.effects)

    def test_research_declares_the_autosave_local_write(self):
        """Der Autosave in die Inbox ist ein echter lokaler Schreibeffekt."""
        view = self._view("web.research")
        self.assertIn(cap.EffectClass.LOCAL_WRITE, view.effects)
        self.assertIn(cap.DataClass.PERSONAL, view.writes)

    def test_web_paths_carry_the_web_scope(self):
        for name in ("web.browse", "web.open", "web.news", "web.research"):
            with self.subTest(name=name):
                self.assertIn(cap.Scope.WEB, self._view(name).scopes)

    def test_timeouts_match_the_action_specs(self):
        registry = cap.build_registry(cap.CapabilityDeps(target_guard=_guard()))
        for action_type, name in (("BROWSE", "web.browse"), ("OPEN", "web.open"),
                                  ("NEWS", "web.news"), ("RESEARCH", "web.research")):
            with self.subTest(action_type=action_type):
                self.assertEqual(actions.spec_for(action_type).timeout,
                                 registry.get(name).timeout_s)


if __name__ == "__main__":
    unittest.main()
