# ADR 0001 – Laufzeit- und Deploymentmodell

- **Status:** akzeptiert (Phase 0, 2026-07-13) — bestätigt im Entscheidungsgate.
- **Betrifft:** [SYSTEM_CHARTER.md](../system/SYSTEM_CHARTER.md) §4/§5.

## Kontext

Jarvis besteht heute aus einer sichtbaren Desktop-Hülle (`jarvis-launcher.pyw`,
pywebview + Tray + Win+J) und einem FastAPI-/uvicorn-Server, der an `127.0.0.1` bindet
(`server.py`). Es gibt keinen unbeaufsichtigten Betrieb, keine Remote-Nutzung und keine
öffentliche Exposition. Der Masterplan verlangt eine verbindliche Prozess-/Deployment-
Entscheidung, bevor Composition Root (Phase 4) und Job-Engine (Phase 6) entstehen.

## Entscheidung

- `jarvis-launcher.pyw` bleibt die **sichtbare Tray-/Desktop-Anwendung**.
- FastAPI läuft als **ausschließlich lokal gebundener Hintergrundprozess** (`127.0.0.1`).
- **Kein Windows-Service** in der ersten produktiven Stufe.
- **Keine öffentliche Exposition** (kein 0.0.0.0-Bind, kein Reverse-Proxy, kein Tunnel).

## Alternativen

1. **Windows-Service jetzt.** Erlaubt unbeaufsichtigten Start ohne Login — aber ohne
   konkreten Use-Case erhöht es Angriffsfläche, Rechte und Komplexität (Session-0-
   Isolation, Audio/Fenster-Interaktion schwierig). Verworfen.
2. **Reiner CLI-Serverstart ohne Tray.** Verliert die etablierte Desktop-UX
   (Panel/Fokus/Vollbild, Tray, Hotkey). Verworfen.
3. **Öffentlich erreichbarer Server.** Widerspricht dem Vertrauens-/Non-Goal-Prinzip.
   Verworfen.

## Konsequenzen

- Phase 4 kann den Lifecycle über FastAPI-Lifespan im lokalen Prozess kapseln, ohne
  Service-Infrastruktur.
- Autostart läuft weiterhin über Task Scheduler + Launcher, nicht über einen Dienst.
- Ein späterer unbeaufsichtigter Anwendungsfall (z.B. geplante Nachtjobs) erfordert eine
  neue ADR, keine stille Umstellung.

## Sicherheitsauswirkungen

- Lokale Bindung + Origin-/Token-Gate begrenzen die Angriffsfläche auf den lokalen
  Nutzerkontext.
- Kein Dienstkonto mit erhöhten Rechten; Jarvis läuft im entsperrten Nutzerkontext.

## Rücknahmekriterien

Neu bewerten, sobald ein konkreter unbeaufsichtigter Betrieb (Hintergrundroutinen ohne
angemeldeten Nutzer) belegt gebraucht wird oder Mehrbenutzer-/Remote-Szenarien
entstehen. Dann: Threat-Model-Delta + neue ADR vor der Umstellung.
