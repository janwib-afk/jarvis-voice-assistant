"""Exakte Wiederherstellung von Umgebungsvariablen im Test (Prompt 20A §6).

Viele Tests setzten ``JARVIS_SKIP_STARTUP_REFRESH`` im Setup und **poppten** es im
Teardown pauschal. War die Variable vorher aber vorhanden (die Suite setzt sie in
``tests/__init__.py``), entfernte das Pop sie ganz — und ein spaeterer, weiter hinten
sortierter Lifespan-Test lief dann OHNE Skip in einen echten ``wttr.in``-Zugriff.
Reihenfolgeabhaengig und kostenwirksam.

``guard_env`` schnappt den EXAKTEN Zustand (vorhanden mit Wert vs. fehlend) und
stellt ihn ueber ``addCleanup`` wieder her — nie ein blanko ``pop()``.
"""
import os

_ABSENT = object()


def guard_env(test, *names):
    """Sichert den exakten Zustand der genannten Variablen und stellt ihn bei
    Erfolg, Fehler UND Setup-Abbruch wieder her (``addCleanup`` laeuft immer,
    sobald es registriert ist).

    Aufrufreihenfolge im ``setUp``: erst ``guard_env(self, NAME)``, DANN den
    gewuenschten Testwert setzen — so ist die Sicherung schon registriert, bevor
    irgendetwas den Wert veraendert.
    """
    snapshot = {n: os.environ.get(n, _ABSENT) for n in names}

    def _restore():
        for name, value in snapshot.items():
            if value is _ABSENT:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    test.addCleanup(_restore)
    return snapshot
