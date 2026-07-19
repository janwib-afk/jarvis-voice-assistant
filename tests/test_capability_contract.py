"""SEAM-CAPABILITY — reiner Capability Contract (RFC-0007 §9/§13, Amendment 1 §A1.7).

Geprueft wird ausschliesslich die oeffentliche Oberflaeche von ``capability``:
Vertragsbau, Schemavalidierung, abgeleiteter ``tier()``, Secret-Verbot,
Registry-Verhalten (Duplicate/Unknown fail-closed) und das passive ``inspect()``.

Verboten (TEST_SEAMS): kein Zugriff auf Registry-Interna, keine Call-Count-Assertions,
keine Assertions auf private Helfer. Reines Modul — keine Grenze zu ersetzen.
"""
import unittest

import tests  # noqa: F401  — setzt JARVIS_CONFIG_PATH auf die synthetische Fixture

import capability as cap


def _contract(**over):
    """Minimaler gueltiger Vertrag; einzelne Felder pro Test ueberschreibbar."""
    base = dict(
        name="test.thing",
        version=1,
        title="Testfaehigkeit",
        inputs=cap.InputSchema(fields=("query",)),
        output=cap.OutputSchema(fields=("text",)),
        effects=(cap.EffectClass.NETWORK_READ,),
        reads=(cap.DataClass.PUBLIC,),
        writes=(),
        scopes=(cap.Scope.WEB,),
        timeout_s=30,
        retry=cap.Retry.NEVER,
        cancellable=True,
        preview=cap.Preview.NONE,
        verify=cap.Verify.SELF_REPORTED,
        health=cap.Health.PASSIVE,
        audit=("name", "version", "outcome"),
        fixture={"query": "wetter"},
        execute=None,
    )
    base.update(over)
    return cap.CapabilityContract(**base)


class ContractConstructionTests(unittest.TestCase):
    """Der Vertrag traegt Identitaet und Wirkungen; Schweigen ist unmoeglich (D2)."""

    def test_contract_carries_stable_identity(self):
        c = _contract()
        self.assertEqual(c.name, "test.thing")
        self.assertEqual(c.version, 1)

    def test_effects_reads_writes_have_no_defaults(self):
        # D2: Weglassen ist ein TypeError beim Registry-Bau, kein stiller Default.
        for missing in ("effects", "reads", "writes"):
            with self.subTest(field=missing):
                kwargs = dict(
                    name="test.thing", version=1, title="T",
                    inputs=cap.InputSchema(fields=("query",)),
                    output=cap.OutputSchema(fields=("text",)),
                    effects=(cap.EffectClass.READ_LOCAL,),
                    reads=(cap.DataClass.LOCAL,), writes=(),
                    scopes=(), timeout_s=5, retry=cap.Retry.NEVER,
                    cancellable=False, preview=cap.Preview.NONE,
                    verify=cap.Verify.NONE, health=cap.Health.PASSIVE,
                    audit=(), fixture={}, execute=None,
                )
                del kwargs[missing]
                with self.assertRaises(TypeError):
                    cap.CapabilityContract(**kwargs)

    def test_contract_is_immutable(self):
        c = _contract()
        with self.assertRaises(Exception):
            c.name = "andere"

    def test_declared_collections_are_frozen_sets(self):
        # Reihenfolge darf keine Bedeutung tragen und nichts nachtraeglich wachsen.
        c = _contract()
        self.assertIsInstance(c.effects, frozenset)
        self.assertIsInstance(c.reads, frozenset)
        self.assertIsInstance(c.writes, frozenset)


class TierDerivationTests(unittest.TestCase):
    """tier() ist abgeleitet — niemand kann 'trivial' behaupten (D2/§9)."""

    def test_tier_is_not_a_declarable_field(self):
        with self.assertRaises(TypeError):
            _contract(tier=cap.Tier.TRIVIAL)

    def test_read_only_public_network_capability_is_trivial(self):
        c = _contract(effects=(cap.EffectClass.NETWORK_READ,),
                      reads=(cap.DataClass.PUBLIC,), writes=())
        self.assertIs(c.tier(), cap.Tier.TRIVIAL)

    def test_any_write_makes_it_governed(self):
        c = _contract(effects=(cap.EffectClass.NETWORK_READ,),
                      reads=(cap.DataClass.PUBLIC,),
                      writes=(cap.DataClass.LOCAL,))
        self.assertIs(c.tier(), cap.Tier.GOVERNED)

    def test_sensitive_read_makes_it_governed(self):
        c = _contract(effects=(cap.EffectClass.READ_LOCAL,),
                      reads=(cap.DataClass.SENSITIVE,), writes=())
        self.assertIs(c.tier(), cap.Tier.GOVERNED)

    def test_destructive_effect_makes_it_governed(self):
        c = _contract(effects=(cap.EffectClass.DESTRUCTIVE,),
                      reads=(cap.DataClass.PUBLIC,), writes=())
        self.assertIs(c.tier(), cap.Tier.GOVERNED)

    def test_screen_and_clipboard_shaped_capability_is_not_trivial(self):
        # Der zentrale Ist-Befund (§2.2): heute sind SCREEN/CLIPBOARD von SEARCH
        # nicht unterscheidbar. Ueber den Vertrag sind sie es.
        screen = _contract(name="screen.describe",
                           effects=(cap.EffectClass.READ_SENSITIVE,
                                    cap.EffectClass.NETWORK_READ),
                           reads=(cap.DataClass.SENSITIVE,), writes=())
        search = _contract(name="web.search",
                           effects=(cap.EffectClass.NETWORK_READ,),
                           reads=(cap.DataClass.PUBLIC,), writes=())
        self.assertIs(screen.tier(), cap.Tier.GOVERNED)
        self.assertIs(search.tier(), cap.Tier.TRIVIAL)


class SecretProhibitionTests(unittest.TestCase):
    """SI-5: 'secret' ist strukturell keine Capability-Ein- oder -Ausgabe."""

    def test_secret_as_read_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _contract(reads=(cap.DataClass.SECRET,))
        self.assertIn("secret", str(ctx.exception))

    def test_secret_as_write_is_rejected(self):
        with self.assertRaises(ValueError):
            _contract(writes=(cap.DataClass.SECRET,))

    def test_secret_remains_part_of_the_taxonomy(self):
        # Der Wert existiert (Doku-Treue), er ist nur nicht vertraglich darstellbar.
        self.assertEqual(cap.DataClass.SECRET.value, "secret")


class SchemaValidationTests(unittest.TestCase):
    """Ein Adapter, der Unsinn schickt, ist ein Fehler und bekommt kein Outcome (§11)."""

    def test_missing_input_field_raises(self):
        c = _contract()
        with self.assertRaises(cap.SchemaError):
            c.inputs.validate({})

    def test_unknown_input_field_raises(self):
        c = _contract()
        with self.assertRaises(cap.SchemaError):
            c.inputs.validate({"query": "x", "schmuggel": "y"})

    def test_valid_input_is_projected_canonically(self):
        c = _contract()
        self.assertEqual(c.inputs.validate({"query": "wetter"}), {"query": "wetter"})

    def test_effects_outside_the_taxonomy_are_rejected(self):
        with self.assertRaises(TypeError):
            _contract(effects=("destructive",))

    def test_empty_effects_are_rejected(self):
        with self.assertRaises(ValueError):
            _contract(effects=())

    def test_audit_fields_outside_the_allowlist_are_rejected(self):
        # Inhalte, URLs und Preview-Hashes sind strukturell nicht auditierbar.
        for forbidden in ("url", "payload", "preview_hash", "query"):
            with self.subTest(field=forbidden):
                with self.assertRaises(ValueError):
                    _contract(audit=("name", forbidden))

    def test_invalid_name_is_rejected(self):
        for bad in ("Search", "web search", "websearch", "", "web."):
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    _contract(name=bad)


class RegistryTests(unittest.TestCase):
    """Duplicate und Unknown sind fail-closed (§8)."""

    def test_duplicate_name_is_rejected(self):
        with self.assertRaises(ValueError):
            cap.Registry([_contract(name="web.search"), _contract(name="web.search")])

    def test_unknown_name_raises_and_is_never_a_fallback(self):
        r = cap.Registry([_contract(name="web.search")])
        with self.assertRaises(cap.UnknownCapability):
            r.get("web.nope")

    def test_registry_reports_its_contents(self):
        r = cap.Registry([_contract(name="web.search"), _contract(name="memory.forget")])
        self.assertEqual(len(r), 2)
        self.assertEqual(r.names(), ("memory.forget", "web.search"))
        self.assertIn("web.search", r)

    def test_registry_is_frozen_after_construction(self):
        r = cap.Registry([_contract(name="web.search")])
        before = r.names()
        with self.assertRaises(Exception):
            r._by_name["web.injected"] = _contract(name="web.injected")
        self.assertEqual(r.names(), before)


class InspectTests(unittest.TestCase):
    """inspect() ist passiv, kostenfrei und rein (§20, D2)."""

    def test_inspect_reports_declared_facts_and_derived_tier(self):
        r = cap.Registry([_contract(name="web.search")])
        view = r.inspect("web.search")
        self.assertEqual(view.name, "web.search")
        self.assertIs(view.tier, cap.Tier.TRIVIAL)
        self.assertEqual(view.effects, frozenset({cap.EffectClass.NETWORK_READ}))

    def test_inspect_never_executes(self):
        calls = []

        def _boom(*a, **k):
            calls.append(1)
            raise AssertionError("inspect darf nie ausfuehren")

        r = cap.Registry([_contract(name="web.search", execute=_boom)])
        r.inspect()
        r.inspect("web.search")
        self.assertEqual(calls, [])

    def test_inspect_all_is_sorted_and_complete(self):
        r = cap.Registry([_contract(name="web.search"), _contract(name="memory.forget")])
        self.assertEqual([v.name for v in r.inspect()], ["memory.forget", "web.search"])

    def test_inspect_unknown_raises(self):
        r = cap.Registry([_contract(name="web.search")])
        with self.assertRaises(cap.UnknownCapability):
            r.inspect("web.nope")


class EffectCensusTests(unittest.TestCase):
    """Der Wirkungs-Zensus (§23): eine Herabstufung erscheint als roter Test im Diff.

    Hier wird die MECHANIK festgenagelt. Den Zensus der vier echten Piloten tragen
    die Pilot-Slices bei (5/7/8/9), damit jeder Slice seinen eigenen Nachweis fuehrt.
    """

    #: Eingefrorene, geprueft aufgestellte Erwartung.
    EXPECTED = {
        "web.search": {cap.EffectClass.NETWORK_READ},
        "memory.forget": {cap.EffectClass.DESTRUCTIVE, cap.EffectClass.NETWORK_READ},
    }

    def _registry(self, forget_effects=(cap.EffectClass.DESTRUCTIVE,
                                        cap.EffectClass.NETWORK_READ)):
        return cap.Registry([
            _contract(name="web.search", effects=(cap.EffectClass.NETWORK_READ,),
                      reads=(cap.DataClass.PUBLIC,), writes=()),
            _contract(name="memory.forget", effects=forget_effects,
                      reads=(cap.DataClass.PERSONAL,),
                      writes=(cap.DataClass.PERSONAL,)),
        ])

    @staticmethod
    def _census(registry):
        return {v.name: set(v.effects) for v in registry.inspect()}

    def test_census_matches_the_frozen_expectation(self):
        self.assertEqual(self._census(self._registry()), self.EXPECTED)

    def test_downgrading_an_effect_turns_the_census_red(self):
        # Mutationsnachweis: wer 'destructive' zu 'read-local' herabstuft, faellt auf.
        mutated = self._registry(forget_effects=(cap.EffectClass.READ_LOCAL,
                                                 cap.EffectClass.NETWORK_READ))
        self.assertNotEqual(self._census(mutated), self.EXPECTED)

    def test_downgrading_an_effect_also_changes_the_derived_tier(self):
        # Zweite, unabhaengige Sichtbarkeit derselben Herabstufung.
        honest = self._registry().inspect("memory.forget")
        mutated = self._registry(
            forget_effects=(cap.EffectClass.NETWORK_READ,)).inspect("memory.forget")
        self.assertIs(honest.tier, cap.Tier.GOVERNED)
        self.assertIs(mutated.tier, cap.Tier.GOVERNED)  # writes halten es governed
        self.assertNotEqual(honest.effects, mutated.effects)


class ImportPurityTests(unittest.TestCase):
    """Der Core ist rein: kein I/O, keine Uhr, kein Modul-Global (§9/§28.1)."""

    def test_module_exposes_no_mutable_module_state(self):
        import capability._contract as mod
        mutable = [
            n for n, v in vars(mod).items()
            if not n.startswith("__")
            and isinstance(v, (list, dict, set))
        ]
        self.assertEqual(mutable, [], f"Veraenderliches Modul-Global gefunden: {mutable}")

    def test_import_performs_no_io(self):
        """Frischer Interpreter, Netz/Datei/Prozess als Fallen — dann erst importieren.

        Bewusst im Subprozess: ein ``importlib.reload`` im laufenden Prozess erzeugt
        eine ZWEITE Enum-Klasse und laesst jeden spaeteren ``isinstance``-Vergleich
        fehlschlagen. Der Subprozess ist ausserdem der staerkere Nachweis, weil er
        auch den allerersten Import erfasst.
        """
        import os
        import subprocess
        import sys

        probe = (
            "import builtins, socket, subprocess as sp\n"
            "def trip(kind):\n"
            "    def f(*a, **k):\n"
            "        raise SystemExit('IO:' + kind)\n"
            "    return f\n"
            "builtins.open = trip('open')\n"
            # socket.socket muss eine VERERBBARE Klasse bleiben: ssl.py definiert
            # beim Import 'class SSLSocket(socket)'. Eine Funktion als Ersatz
            # wuerde schon diese Klassendefinition sprengen und nichts ueber das
            # gepruefte Modul aussagen.
            "_RealSocket = socket.socket\n"
            "class _TrapSocket(_RealSocket):\n"
            "    def __init__(self, *a, **k):\n"
            "        raise SystemExit('IO:socket')\n"
            "socket.socket = _TrapSocket\n"
            "socket.create_connection = trip('connect')\n"
            "socket.getaddrinfo = trip('dns')\n"
            # Gleiches Problem wie bei socket: asyncio.windows_utils definiert
            # beim Import 'class Popen(subprocess.Popen)'.
            "_RealPopen = sp.Popen\n"
            "class _TrapPopen(_RealPopen):\n"
            "    def __init__(self, *a, **k):\n"
            "        raise SystemExit('IO:subprocess')\n"
            "sp.Popen = _TrapPopen\n"
            "import capability\n"
            "c = capability.CapabilityContract(\n"
            "    name='probe.thing', version=1, title='T',\n"
            "    inputs=capability.InputSchema(fields=('q',)),\n"
            "    output=capability.OutputSchema(fields=('t',)),\n"
            "    effects=(capability.EffectClass.NETWORK_READ,),\n"
            "    reads=(capability.DataClass.PUBLIC,), writes=(),\n"
            "    scopes=(capability.Scope.WEB,), timeout_s=5,\n"
            "    retry=capability.Retry.NEVER, cancellable=True,\n"
            "    preview=capability.Preview.NONE, verify=capability.Verify.NONE,\n"
            "    health=capability.Health.PASSIVE, audit=(), fixture={}, execute=None)\n"
            "c.tier()\n"
            "capability.Registry([c]).inspect()\n"
            "print('PURE')\n"
        )
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, env=env, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout} stderr={proc.stderr}")
        self.assertIn("PURE", proc.stdout)


if __name__ == "__main__":
    unittest.main()
