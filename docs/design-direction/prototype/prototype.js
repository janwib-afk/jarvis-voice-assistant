// Phase-2-Prototyp: minimale Interaktion, nur zur Designvalidierung.
// Spiegelt den produktiven Klassen-Kontrakt (mode-*/Seiten-Umschaltung),
// enthaelt aber KEINE Backend-, WebSocket- oder Sprachlogik.

(function () {
    'use strict';

    var stage = document.getElementById('stage');
    var viewJarvis = document.getElementById('view-jarvis');
    var viewControl = document.getElementById('view-control');
    var orb = document.getElementById('stage-orb');
    var orbMirror = document.querySelector('[data-orb-mirror]');
    var statusEl = document.getElementById('stage-status');
    var statusText = document.getElementById('stage-status-text');

    var STATUS_TEXT = {
        idle: 'Bereit',
        listening: 'Hört zu',
        thinking: 'Denkt nach',
        speaking: 'Spricht',
        muted: 'Mikrofon stumm',
        error: 'Störung — Details im Gespräch'
    };

    function pressGroup(buttons, active) {
        buttons.forEach(function (b) {
            b.setAttribute('aria-pressed', b === active ? 'true' : 'false');
        });
    }

    // Fenstermodus (Prototyp-Steuerung)
    var modeButtons = Array.prototype.slice.call(document.querySelectorAll('[data-mode]'));
    modeButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            stage.className = 'stage mode-' + btn.dataset.mode;
            pressGroup(modeButtons, btn);
            // Panel zeigt immer die Gespraechsseite (wie produktiv).
            if (btn.dataset.mode === 'panel') showPage('jarvis');
        });
    });

    // Seite (Prototyp-Steuerung + Kopfleisten-Nav)
    var pageButtons = Array.prototype.slice.call(document.querySelectorAll('[data-page]'));
    var navTabs = Array.prototype.slice.call(document.querySelectorAll('.nav-tab'));

    function showPage(page) {
        viewJarvis.hidden = page !== 'jarvis';
        viewControl.hidden = page !== 'control';
        pageButtons.forEach(function (b) {
            b.setAttribute('aria-pressed', b.dataset.page === page ? 'true' : 'false');
        });
        navTabs.forEach(function (t) {
            t.setAttribute('aria-selected', t.dataset.view === page ? 'true' : 'false');
        });
    }
    pageButtons.forEach(function (btn) {
        btn.addEventListener('click', function () { showPage(btn.dataset.page); });
    });
    navTabs.forEach(function (tab) {
        tab.addEventListener('click', function () { showPage(tab.dataset.view); });
    });

    // Orb-Zustand (Prototyp-Steuerung)
    var orbButtons = Array.prototype.slice.call(document.querySelectorAll('[data-orb]'));
    orbButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var state = btn.dataset.orb;
            [orb, orbMirror].forEach(function (o) {
                if (o) o.className = 'orb is-' + state;
            });
            statusEl.className = 'instr-status is-' + state;
            statusText.textContent = STATUS_TEXT[state];
            pressGroup(orbButtons, btn);
        });
    });
})();
