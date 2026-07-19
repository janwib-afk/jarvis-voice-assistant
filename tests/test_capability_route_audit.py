"""Slice 11 — Route-Audit und die einzige Delete-Ausnahme (Amendment 2 §A2.1).

Der Audit ist deterministisch und **vollstaendig aus dem Code erhoben**: er zaehlt
nicht gegen eine gepflegte Liste, sondern vergleicht die tatsaechlich in der App
registrierten mutierenden Routen mit dem Register. Eine neue, nicht eingetragene
mutierende Route macht ihn rot — damit kann kein Wirkungspfad still am Coordinator
vorbei entstehen.
"""
import inspect
import unittest

import tests  # noqa: F401

import capability as cap
import server

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _walk(routes):
    """Traversiert Routen **versionsrobust**.

    Bis FastAPI 0.136 legte ``include_router`` die Router-Routen flach in
    ``app.routes``. Ab 0.139/Starlette 1.3 steht dort stattdessen ein einzelnes
    ``_IncludedRouter``, das seine Routen unter ``original_router`` fuehrt. Ein
    Audit, der nur die flache Liste liest, findet auf neueren Versionen **null**
    Routen — und waere damit stillschweigend wirkungslos.
    """
    for route in routes:
        nested = getattr(route, "routes", None)
        if nested is None:
            included = getattr(route, "original_router", None)
            nested = getattr(included, "routes", None) if included is not None else None
        if nested:
            yield from _walk(nested)
            continue
        path = getattr(route, "path", None)
        if path is None:
            continue
        methods = getattr(route, "methods", None) or set()
        for method in methods & _MUTATING_METHODS:
            yield method, path, route.endpoint


def _mutating_entries():
    """``{(method, path): endpoint}`` — aus App **und** eigenem Router.

    Der eigene ``server.router`` ist die stabile Quelle; ``server.app`` faengt
    zusaetzlich eine Route, die jemand direkt per ``@app.post`` registriert und
    damit am Router vorbeigefuehrt haette.
    """
    entries = {}
    for method, path, endpoint in _walk(server.app.routes):
        entries[(method, path)] = endpoint
    for method, path, endpoint in _walk(server.router.routes):
        entries.setdefault((method, path), endpoint)
    return entries


def _actual_mutating_routes():
    """Alle mutierenden Routen DIREKT aus dem Code — keine Zweitliste."""
    return set(_mutating_entries())


class RouteInventoryTests(unittest.TestCase):
    def test_exactly_ten_mutating_routes_exist(self):
        self.assertEqual(10, len(_actual_mutating_routes()),
                         sorted(_actual_mutating_routes()))

    def test_register_and_reality_agree(self):
        """Der Kern des Audits: keine unregistrierte mutierende Route."""
        self.assertEqual(_actual_mutating_routes(),
                         set(server.MUTATING_ROUTE_CAPABILITIES))

    def test_exactly_nine_routes_are_capability_governed(self):
        governed = [k for k, v in server.MUTATING_ROUTE_CAPABILITIES.items()
                    if v is not None]
        self.assertEqual(9, len(governed), sorted(governed))

    def test_exactly_one_documented_exception(self):
        exceptions = [k for k, v in server.MUTATING_ROUTE_CAPABILITIES.items()
                      if v is None]
        self.assertEqual([server.DELETE_EXCEPTION], exceptions)

    def test_the_exception_is_the_profile_delete(self):
        self.assertEqual(("DELETE", "/launcher/profiles/{profile_id}"),
                         server.DELETE_EXCEPTION)

    def test_every_named_capability_is_registered(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        for route, name in server.MUTATING_ROUTE_CAPABILITIES.items():
            if name is None:
                continue
            with self.subTest(route=route):
                self.assertIn(name, registry)

    def test_the_register_is_immutable(self):
        with self.assertRaises(TypeError):
            server.MUTATING_ROUTE_CAPABILITIES[("POST", "/neu")] = "x"


class HandlersActuallyUseTheCoordinatorTests(unittest.TestCase):
    """Der Eintrag im Register genuegt nicht — der Handler muss ihn auch gehen."""

    def _handler_source(self, method, path):
        endpoint = _mutating_entries().get((method, path))
        if endpoint is None:
            self.fail(f"Route {method} {path} nicht gefunden")
        return inspect.getsource(endpoint)

    def test_each_governed_handler_reaches_the_coordinator(self):
        for (method, path), name in server.MUTATING_ROUTE_CAPABILITIES.items():
            if name is None:
                continue
            with self.subTest(route=(method, path)):
                source = self._handler_source(method, path)
                reaches = ("capabilities.attempt" in source
                           or "_launcher_capability" in source)
                self.assertTrue(reaches,
                                f"{method} {path} erreicht den Coordinator nicht")

    def test_the_delete_route_has_no_sham_confirmation(self):
        """§A2.1: der direkte DELETE wird NICHT umetikettiert."""
        source = self._handler_source(*server.DELETE_EXCEPTION)
        for forbidden in ("confirmed=True", "Confirmation", "grant", "Grant"):
            self.assertNotIn(forbidden, source,
                             f"Schein-Bestaetigung im Delete-Pfad: {forbidden}")

    def test_the_delete_route_still_persists_through_the_single_writer(self):
        """Ungeschuetzt heisst nicht ungeordnet: Configuration bleibt der Writer."""
        source = self._handler_source(*server.DELETE_EXCEPTION)
        self.assertIn("_persist_launcher", source)


class TraversalIsVersionRobustTests(unittest.TestCase):
    """Regression: der Audit darf nicht von der Router-Abflachung abhaengen.

    Bis FastAPI 0.136 legte ``include_router`` die Routen flach in ``app.routes``.
    Ab 0.139/Starlette 1.3 steht dort ein ``_IncludedRouter`` mit
    ``original_router``. Ein Audit, der nur die flache Liste liest, fand auf den
    neueren Versionen **null** Routen — und war damit stillschweigend wirkungslos,
    obwohl er lokal gruen aussah. Genau das ist auf dem Hosted-Gate passiert.
    """

    def test_walk_descends_into_an_included_router(self):
        class _FakeRoute:
            path = "/schatten"
            methods = {"POST"}

            @staticmethod
            def endpoint():
                return None

        class _FakeIncludedRouter:
            """Spiegelt die neue FastAPI-Form: Routen nur ueber ``original_router``."""
            original_router = type("R", (), {"routes": [_FakeRoute()]})()

        found = [(m, p) for m, p, _ in _walk([_FakeIncludedRouter()])]
        self.assertEqual([("POST", "/schatten")], found)

    def test_walk_still_reads_a_flat_route_list(self):
        class _FlatRoute:
            path = "/flach"
            methods = {"DELETE"}

            @staticmethod
            def endpoint():
                return None

        found = [(m, p) for m, p, _ in _walk([_FlatRoute()])]
        self.assertEqual([("DELETE", "/flach")], found)

    def test_the_audit_actually_finds_routes(self):
        """Die schaerfste Zusage: ein blinder Audit ist schlimmer als keiner."""
        self.assertGreater(len(_actual_mutating_routes()), 0,
                           "der Audit findet gar keine Routen — er ist blind")


class NewRouteWouldBreakTheAuditTests(unittest.TestCase):
    """Belegt, dass der Audit auf eine NEUE Route reagiert — nicht nur zaehlt."""

    def test_an_unregistered_mutating_route_is_detected(self):
        registered = set(server.MUTATING_ROUTE_CAPABILITIES)
        simulated = _actual_mutating_routes() | {("POST", "/schattenpfad")}
        self.assertNotEqual(simulated, registered,
                            "der Audit wuerde eine neue Route nicht bemerken")
        self.assertEqual({("POST", "/schattenpfad")}, simulated - registered)


class ActionMappingAuditTests(unittest.TestCase):
    """Die zweite Haelfte des Audits: 22/22 Actions (Amendment 2 §A2.2)."""

    def test_every_action_is_mapped(self):
        import actions
        self.assertEqual(set(actions.REGISTRY), set(cap.MIGRATED_ACTIONS))
        self.assertEqual(22, len(actions.REGISTRY))

    def test_shared_names_are_allowed(self):
        """21 Namen fuer 22 Actions — AUTOSTART_ON/OFF teilen einen Vertrag."""
        self.assertEqual(21, len(set(cap.MIGRATED_ACTIONS.values())))

    def test_every_mapped_capability_is_registered(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        for action_type, name in cap.MIGRATED_ACTIONS.items():
            with self.subTest(action_type=action_type):
                self.assertIn(name, registry)


if __name__ == "__main__":
    unittest.main()
