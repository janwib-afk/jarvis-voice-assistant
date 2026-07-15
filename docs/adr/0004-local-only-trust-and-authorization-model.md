# ADR 0004 – Local-only Trust- und Autorisierungsmodell

- **Status:** akzeptiert (Phase 2, 2026-07-14) — erstellt unter der ausdrücklichen
  Nutzer-Delegation („wähle bei Fragen immer deine Empfehlung").
- **Betrifft:** [../security/SECURITY_REQUIREMENTS.md](../security/SECURITY_REQUIREMENTS.md),
  [../security/IDENTITY_AND_PRESENCE_MODEL.md](../security/IDENTITY_AND_PRESENCE_MODEL.md),
  Threats TM-001/TM-003/TM-004.

## Warum ADR (3 Kriterien)

1. **Teuer zurückzunehmen:** prägt den gesamten Capability-/Policy-Kernel (Phase 5), die
   Presence-Runtime und jeden künftigen Connector; eine spätere Umkehr bedeutet Re-Design
   der Autorisierung.
2. **Ohne Kontext überraschend:** „Warum darf Voice nicht alles?" / „Warum verweigert
   Jarvis Aktionen bei gesperrtem Desktop?" — braucht Begründung.
3. **Echter Trade-off:** Komfort/Automatisierung vs. Schutz gegen Voice-Spoofing und
   unbeaufsichtigte Wirkung.

## Kontext

Jarvis läuft rein lokal (`server.py:746`) und führt aus untrusted LLM-Ausgabe
`[ACTION:…]`-Aktionen aus. Stimme ist heute ein trusted Eingabekanal ohne Identitätscheck;
der Session-Token ist über `GET /` für lokale Prozesse lesbar (`server.py:723`, TM-003).

## Entscheidung

- **SI-1:** Untrusted Inhalt (Web/Vault/Clipboard/Screen/Recherche/LLM-Ausgabe) darf
  niemals eine Aktion autorisieren, eine Wirkungsklasse erhöhen oder Policy ändern.
- **SI-2:** Eine erkannte Stimme ist kein Identitätsnachweis; Voice allein autorisiert
  keine hochriskante/destruktive/`external-write`-Wirkung.
- **SI-3:** Wirkende Aktionen nur bei lokal entsperrtem Desktop; gesperrt/Remote nur
  passiv lesen.
- Hochrisiko/`external-write`/destruktiv benötigen eine **sichtbare Bestätigung** (heute
  Confirm für `MEMORY_FORGET`; künftig UI-Preview-Bestätigung).

## Alternativen

1. **Voice als vollwertige Autorität** — bequemer, aber Voice-Spoofing/Playback könnten
   Hochrisiko auslösen. Verworfen.
2. **Token als alleinige Autorisierung** — scheitert an lokaler Token-Lesbarkeit (TM-003).
   Verworfen als alleinige Grenze.
3. **Remote-Betrieb zulassen** — widerspricht SYSTEM_CHARTER/ADR 0001; erhöht Angriffs-
   fläche massiv. Verworfen (bleibt Nutzerentscheidung mit neuer ADR).

## Konsequenzen

- Der Capability-Kernel (Phase 5) muss Wirkungsklassen, Presence und Preview-gebundene
  Autorisierung tragen; untrusted Content wird als Vorschlag, nicht als Befehl behandelt.
- Bequemlichkeitsverlust: manche Hochrisiko-Wirkungen brauchen einen UI-Klick.

## Sicherheitsauswirkungen

Neutralisiert Prompt-Injection-zu-Wirkung (TM-001) und Voice-Spoofing (TM-004) für
Hochrisiko; entkoppelt Wirkung von der lokal lesbaren Token-Grenze (TM-003).

## Rücknahmekriterien

Neu bewerten nur bei ausdrücklichem, dokumentiertem Nutzerwunsch nach Remote-/
unbeaufsichtigtem Betrieb — dann Threat-Model-Delta + neue ADR **vor** der Umsetzung.
Beziehung: ergänzt ADR 0001 (Local-only Deployment), kein Konflikt.
