# ADR 0003 – Test-Config-Seam (`JARVIS_CONFIG_PATH`)

- **Status:** akzeptiert (Phase 0, 2026-07-13) — bestätigt im Entscheidungsgate.
- **Betrifft:** [QUALITY_BASELINE.md](../quality/QUALITY_BASELINE.md) §4, `server.py`,
  `config_loader.py`, `tests/`.

## Kontext

`server.py` lud `config.json` beim Import fest von `os.path.dirname(__file__)/config.json`.
Fehlte/ungültig, brach der Import ab (`ConfigError`→`sys.exit`), und 12 Testdateien
übersprangen per `@unittest.skipIf(server is None)` **still** ganze Klassen. Damit war die
grüne Suite an eine gültige **persönliche** `config.json` gekoppelt — ein Phase-0-Blocker.
Der volle Composition-Root-Umbau bleibt Phase 4 vorbehalten; hier ist nur die kleinste
kontrollierte Seam gefragt.

## Entscheidung

- Neue pure Funktion `config_loader.resolve_config_path(environ, default)`:
  liefert `JARVIS_CONFIG_PATH` (falls gesetzt, nicht leer), sonst den Default.
- `server.py` nutzt sie: `CONFIG_PATH = resolve_config_path(os.environ, <repo>/config.json)`.
- Eingecheckte, **synthetische** Fixture `tests/fixtures/config.test.json` (Dummy-Keys,
  keine persönlichen Pfade, minimale Apps/Launcher).
- Auswahl im Test: `tests/__init__.py` setzt `JARVIS_CONFIG_PATH` (setdefault) auf die
  Fixture; jede server-importierende Testdatei macht `import tests` als ersten Import
  (vor `import server`); der Smoke-Test setzt die Variable ebenfalls am Kopf.
- Kein stiller Rückfall: fehlt/ungültig die gewählte Config, bleibt es ein harter
  `ConfigError`.

## Alternativen

1. **Monkeypatch von `load_config`** (wie im Baseline-Harness). Funktioniert, ist aber
   unexplizit und pro Test zu wiederholen. Verworfen als Standardmechanik.
2. **Nur `tests/__init__.py`** ohne `import tests` je Modul. `unittest discover -s tests`
   importiert Module top-level (`test_x`, nicht `tests.test_x`), sodass das Paket-`__init__`
   nicht läuft — empirisch bestätigt. Allein unzureichend; daher zusätzlich `import tests`.
3. **Große App-Factory jetzt.** Über Phase-0-Scope hinaus; Phase 4 vorbehalten.

## Konsequenzen

- Suite und Smoke laufen ohne persönliche `config.json` (503 Tests, 0 Skips, Exit 0).
- Smoke validiert die **aktive** (Fixture-)Config, nicht mehr zwingend die persönliche;
  Produktions-Config wird beim echten Serverstart hart geprüft.
- Der Smoke-Test **scheitert** jetzt bei unerwarteten Skips (u.a. `server import nicht
  moeglich`) — negativ nachgewiesen (Exit 1, 131 unerwartete Skips bei falschem Pfad).
- 13 Testdateien erhielten die eine Zeile `import tests`; Wire-/REST-/UI-Verträge
  unverändert.

## Sicherheitsauswirkungen

- Produktion setzt `JARVIS_CONFIG_PATH` **nicht** und nutzt immer die echte `config.json`
  — kein Weg, unbemerkt eine Dummy-Config produktiv zu verwenden.
- Fixture enthält nur Dummy-Keys/keine persönlichen Pfade (durch Test abgesichert:
  `test_config_seam.SyntheticFixtureTests`).

## Rücknahmekriterien

Ablösen, sobald Phase 4 die Composition Root mit explizitem Config-Objekt und
Lifespan-Injektion einführt; `resolve_config_path` kann dann in den Startup-Pfad der
App-Factory wandern. Bis dahin bleibt die Env-Seam die einzige kontrollierte Auswahl.
