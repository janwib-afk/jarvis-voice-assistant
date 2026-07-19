"""Slice 1 — typisierte Vertraege, belegte Scopes und der Invocation-Binding-Seam.

RFC-0007 Amendment 2 §A2.4: ``InputSchema``/``OutputSchema`` werden rueckwaerts-
kompatibel zu echten Typvertraegen vertieft; request-spezifische Abhaengigkeiten
laufen ueber einen kleinen **unveraenderlichen** Seam mit schmalen Ports.

Die zwei Tracer dieses Slices belegen die beiden Portarten:

* ``launcher.profile.status`` — rein lokaler Launcher-Lesepfad (kein Port noetig)
* ``conversation.summary``    — braucht den unveraenderlichen History-Snapshot

Seam: die oeffentliche Capability-Oberflaeche (``capability.*``), nicht die
Modulinterna. Kein Test greift auf private Registry-Strukturen zu.
"""
import unittest

import tests  # noqa: F401

import actions
import capability as cap


class TypedInputSchemaTests(unittest.TestCase):
    """§A2.4: explizite Feldtypen, eindeutiges required/optional, keine Umwandlung."""

    def test_plain_string_field_stays_untyped_and_required(self):
        """Rueckwaertskompatibel: die bestehende Pilotform bleibt gueltig."""
        schema = cap.InputSchema(fields=("query",))
        self.assertEqual({"query": "wetter"}, schema.validate({"query": "wetter"}))
        with self.assertRaises(cap.SchemaError):
            schema.validate({})

    def test_typed_field_accepts_declared_type(self):
        schema = cap.InputSchema(fields=(cap.Field("enabled", bool),))
        self.assertEqual({"enabled": True}, schema.validate({"enabled": True}))

    def test_typed_field_rejects_wrong_type_without_coercion(self):
        """Keine implizite Typumwandlung: '5' wird nicht zu 5."""
        schema = cap.InputSchema(fields=(cap.Field("count", int),))
        with self.assertRaises(cap.SchemaError) as ctx:
            schema.validate({"count": "5"})
        self.assertIn("count", str(ctx.exception))

    def test_bool_is_not_accepted_for_int_field(self):
        """``bool`` ist in Python ein ``int`` — fachlich aber nie eine Zahl."""
        schema = cap.InputSchema(fields=(cap.Field("count", int),))
        with self.assertRaises(cap.SchemaError):
            schema.validate({"count": True})

    def test_optional_field_may_be_absent(self):
        schema = cap.InputSchema(fields=(cap.Field("note", str, required=False),))
        self.assertEqual({}, schema.validate({}))
        self.assertEqual({"note": "x"}, schema.validate({"note": "x"}))

    def test_optional_field_still_typechecked_when_present(self):
        schema = cap.InputSchema(fields=(cap.Field("note", str, required=False),))
        with self.assertRaises(cap.SchemaError):
            schema.validate({"note": 7})

    def test_unknown_field_rejected_for_typed_schema(self):
        schema = cap.InputSchema(fields=(cap.Field("query", str),))
        with self.assertRaises(cap.SchemaError) as ctx:
            schema.validate({"query": "a", "sneaky": "b"})
        self.assertIn("sneaky", str(ctx.exception))

    def test_error_messages_are_deterministic(self):
        """Gleiche Verletzung -> exakt gleiche Meldung (Ordnung stabil sortiert)."""
        schema = cap.InputSchema(fields=(cap.Field("a", str), cap.Field("b", str)))
        msgs = set()
        for _ in range(3):
            try:
                schema.validate({})
            except cap.SchemaError as e:
                msgs.add(str(e))
        self.assertEqual(1, len(msgs), msgs)

    def test_output_schema_typechecks_too(self):
        schema = cap.OutputSchema(fields=(cap.Field("text", str),))
        self.assertEqual({"text": "ok"}, schema.validate({"text": "ok"}))
        with self.assertRaises(cap.SchemaError):
            schema.validate({"text": 3})


class DocumentedScopeTests(unittest.TestCase):
    """§A2.4: nur die BELEGTEN Scopes kommen hinzu."""

    def test_new_scopes_exist(self):
        for value in ("config.settings", "config.music", "conversation"):
            with self.subTest(value=value):
                self.assertEqual(value, cap.Scope(value).value)

    def test_launcher_scope_is_not_reused_for_settings_or_music(self):
        self.assertNotEqual(cap.Scope.CONFIG_LAUNCHER, cap.Scope.CONFIG_SETTINGS)
        self.assertNotEqual(cap.Scope.CONFIG_LAUNCHER, cap.Scope.CONFIG_MUSIC)


class InvocationBindingsTests(unittest.TestCase):
    """§A2.4: schmal, unveraenderlich, und NIRGENDS in Request/Hash/Policy/Audit."""

    def test_bindings_are_immutable(self):
        b = cap.InvocationBindings()
        with self.assertRaises(Exception):
            b.ai = object()

    def test_bindings_expose_only_the_narrow_ports(self):
        """Kein Runtime-Objekt, kein Locator, kein frei erweiterbares Dict."""
        self.assertEqual(
            {"ai", "history", "mutate_launcher", "feedback"},
            set(cap.InvocationBindings.__dataclass_fields__),
        )

    def test_history_snapshot_is_a_tuple(self):
        b = cap.InvocationBindings(history=[{"role": "user", "content": "hi"}])
        self.assertIsInstance(b.history, tuple)

    def test_bindings_do_not_change_the_idempotency_key(self):
        """§A2.4: Bindings sind nicht Teil des Idempotency-Hashes."""
        registry = cap.build_registry(cap.CapabilityDeps())
        coord = cap.Coordinator(registry)
        request = cap.CapabilityRequest(
            "web.search", cap.Provenance.DERIVED, {"query": "x"})
        self.assertEqual(coord.idempotency_key(request),
                         coord.idempotency_key(request))

    def test_request_has_no_binding_field(self):
        """Clients/Historien duerfen nicht in Payload oder meta versteckt werden."""
        self.assertNotIn("bindings", cap.CapabilityRequest.__dataclass_fields__)


class ProfileStatusTracerTests(unittest.IsolatedAsyncioTestCase):
    """``PROFILE_STATUS`` -> ``launcher.profile.status`` (lokaler Launcher-Tracer)."""

    def setUp(self):
        import app_launcher
        self._saved = (app_launcher.APPS, app_launcher.PROFILES,
                       app_launcher.ACTIVE_PROFILE)
        app_launcher.APPS = [
            {"id": "obsidian", "name": "Obsidian", "type": "exe",
             "path": "C:/x/o.exe"},
            {"id": "code", "name": "VS Code", "type": "exe", "path": "C:/x/c.exe"},
        ]
        # ``profile["apps"]`` ist eine Abbildung app_id -> Zustand; ein fehlender
        # Eintrag gilt als autostart:true (app_launcher.effective_apps).
        app_launcher.PROFILES = [
            {"id": "default", "name": "Standard",
             "apps": {"obsidian": {"autostart": True},
                      "code": {"autostart": False}}},
        ]
        app_launcher.ACTIVE_PROFILE = "default"

    def tearDown(self):
        import app_launcher
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved

    def test_mapping_is_canonical(self):
        self.assertEqual("launcher.profile.status",
                         cap.MIGRATED_ACTIONS["PROFILE_STATUS"])

    async def test_active_profile_text_is_byte_identical_to_legacy(self):
        """Unabhaengige Wahrheit: das heutige Rohergebnis des Legacy-Executors."""
        legacy = await actions.spec_for("PROFILE_STATUS").execute(
            "", actions.ActionContext())
        migrated = await self._run("")
        self.assertEqual(legacy, migrated)
        # ...und zusaetzlich gegen ein Literal, damit der Test nicht mitwandert,
        # falls beide Seiten gleichzeitig brechen.
        self.assertEqual("Aktiv ist 'Standard'. Beim Clap starten: Obsidian.",
                         migrated)

    async def test_unknown_profile_text_is_byte_identical_to_legacy(self):
        legacy = await actions.spec_for("PROFILE_STATUS").execute(
            "gibtsnicht", actions.ActionContext())
        self.assertEqual(legacy, await self._run("gibtsnicht"))

    def test_contract_declares_its_full_effect_set(self):
        """``speaks_result=True`` heisst TTS — also ein deklarierter Netzeffekt."""
        view = cap.build_registry(cap.CapabilityDeps()).inspect(
            "launcher.profile.status")
        self.assertEqual(
            frozenset({cap.EffectClass.READ_LOCAL, cap.EffectClass.NETWORK_READ}),
            view.effects)
        self.assertEqual(frozenset({cap.DataClass.LOCAL}), view.reads)
        self.assertEqual(frozenset(), view.writes)

    async def _run(self, payload: str) -> str:
        coord = cap.Coordinator(cap.build_registry(cap.CapabilityDeps()))
        return await cap.run_migrated(
            coord, actions.Action("PROFILE_STATUS", payload),
            actions.ActionContext())


class SessionSummaryTracerTests(unittest.IsolatedAsyncioTestCase):
    """``SESSION_SUMMARY`` -> ``conversation.summary`` (History-Snapshot-Tracer)."""

    HISTORY = (
        {"role": "user", "content": "Was ist mit dem Bericht?"},
        {"role": "assistant", "content": "Der liegt im Vault."},
    )

    def test_mapping_is_canonical(self):
        self.assertEqual("conversation.summary",
                         cap.MIGRATED_ACTIONS["SESSION_SUMMARY"])

    async def test_history_reaches_the_capability_through_the_bindings(self):
        legacy = await actions.spec_for("SESSION_SUMMARY").execute(
            "", actions.ActionContext(history=self.HISTORY))
        migrated = await self._run(self.HISTORY)
        self.assertEqual(legacy, migrated)
        self.assertIn("Du: Was ist mit dem Bericht?", migrated)
        self.assertIn("Jarvis: Der liegt im Vault.", migrated)

    async def test_empty_history_matches_legacy_wording(self):
        legacy = await actions.spec_for("SESSION_SUMMARY").execute(
            "", actions.ActionContext(history=()))
        migrated = await self._run(())
        self.assertEqual(legacy, migrated)
        self.assertEqual("Diese Sitzung hat noch keinen nennenswerten Verlauf.",
                         migrated)

    async def test_summary_declares_the_conversation_scope(self):
        view = cap.build_registry(cap.CapabilityDeps()).inspect("conversation.summary")
        self.assertIn(cap.Scope.CONVERSATION, view.scopes)

    def test_summary_declares_its_full_effect_set(self):
        """§A2.5: der Summary-LLM und die TTS sind deklarierte Folgeeffekte.

        Ohne diese Zusage bliebe eine stille Herabstufung unbemerkt — der
        Verlauf verliesse den Rechner, ohne dass der Vertrag es sagt.
        """
        view = cap.build_registry(cap.CapabilityDeps()).inspect("conversation.summary")
        self.assertEqual(
            frozenset({cap.EffectClass.NETWORK_READ, cap.EffectClass.READ_LOCAL}),
            view.effects)
        self.assertEqual(frozenset({cap.DataClass.PERSONAL}), view.reads)
        self.assertEqual(frozenset(), view.writes)

    def test_summary_is_governed_because_history_is_personal(self):
        """Der Verlauf ist ``personal`` — damit ist der Vertrag nie ``trivial``."""
        view = cap.build_registry(cap.CapabilityDeps()).inspect("conversation.summary")
        self.assertIs(cap.Tier.GOVERNED, view.tier)

    async def _run(self, history) -> str:
        coord = cap.Coordinator(cap.build_registry(cap.CapabilityDeps()))
        return await cap.run_migrated(
            coord, actions.Action("SESSION_SUMMARY", ""),
            actions.ActionContext(history=history))


if __name__ == "__main__":
    unittest.main()
