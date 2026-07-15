// Phase-3-UX-Prototyp: Zustandsmaschine + Interaktionssimulation (kein Backend).
(function () {
    'use strict';
    var $ = function (s) { return document.querySelector(s); };
    var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

    var stage = $('#stage'), orb = $('#orb'), orbMirror = document.querySelector('[data-orb-mirror]');
    var stateWord = $('#state-word'), mirrorWord = document.querySelector('[data-state-word-mirror]');
    var runningAction = $('#running-action'), escHint = $('#esc-hint');
    var livePolite = $('#live-polite'), liveAssertive = $('#live-assertive');
    var muted = false, currentState = 'listening';

    // ── Zustandsmodell (STATE_MODEL.md) ─────────────────────────────────
    var STATES = {
        disconnected:     { word: 'Getrennt — verbinde neu (Versuch 2)', orb: 'idle',      server: 'err', action: '' },
        connecting:       { word: 'Verbinde …',                          orb: 'idle',      server: 'off', action: '' },
        idle:             { word: 'Bereit',                              orb: 'idle',      server: 'ok',  action: '' },
        listening:        { word: 'Hört zu',                             orb: 'listening', server: 'ok',  action: '' },
        processing:       { word: 'Verarbeite …',                        orb: 'thinking',  server: 'ok',  action: '' },
        thinking:         { word: 'Denkt nach',                          orb: 'thinking',  server: 'ok',  action: '' },
        'action-running': { word: 'Recherchiert:',                       orb: 'thinking',  server: 'ok',  action: 'Elektroautos Reichweite' },
        speaking:         { word: 'Spricht',                             orb: 'speaking',  server: 'ok',  action: '' },
        stopping:         { word: 'Stoppt …',                            orb: 'idle',      server: 'ok',  action: '' },
        degraded:         { word: 'Eingeschränkt: Sprachausgabe nicht verfügbar', orb: 'listening', server: 'ok', action: '' },
        error:            { word: 'Störung — Details im Banner',         orb: 'error',     server: 'ok',  action: '' }
    };

    // R3: Banner-Simulation (ein Banner je Art, ersetzt Vorgänger)
    function showBanner(kind, title, text, hint, assertive) {
        var stack = $('#banner-stack');
        var old = stack.querySelector('.banner.' + kind); if (old) old.remove();
        var b = document.createElement('div');
        b.className = 'banner ' + kind;
        if (assertive) b.setAttribute('role', 'alert');
        b.innerHTML = '<button class="b-close" aria-label="Meldung schließen">×</button>' +
            '<span class="b-title"></span><span class="b-text"></span>' +
            (hint ? '<span class="b-hint"></span>' : '');
        b.querySelector('.b-title').textContent = title;
        b.querySelector('.b-text').textContent = text;
        if (hint) b.querySelector('.b-hint').textContent = hint;
        b.querySelector('.b-close').addEventListener('click', function () { b.remove(); });
        stack.appendChild(b);
    }

    function setState(name) {
        var s = STATES[name]; if (!s) return;
        currentState = name;
        var mutedNow = muted && (name === 'idle' || name === 'listening');
        var orbClass = 'orb is-' + (mutedNow ? 'muted' : s.orb);
        orb.className = orbClass; if (orbMirror) orbMirror.className = orbClass;
        stateWord.textContent = mutedNow ? 'Mikrofon stumm' : s.word;
        if (mirrorWord) mirrorWord.textContent = stateWord.textContent;
        runningAction.textContent = s.action ? ' ' + s.action : '';
        escHint.hidden = !(name === 'speaking' || name === 'action-running');
        // R5: Statuszeilen-Dot folgt dem Zustand (Klartext steht daneben)
        $('#status-line').className = 'instr-status s-' + (mutedNow ? 'muted' : name);
        $('#dot-server').className = 'f-dot ' + (s.server === 'ok' ? 'ok' : s.server === 'err' ? 'err' : '');
        $('#txt-server').textContent = s.server === 'ok' ? 'Server verbunden' : (name === 'connecting' ? 'Verbinde …' : 'Getrennt');
        var stopPrimary = name === 'speaking' || name === 'action-running';
        $('#btn-stop').classList.toggle('primary-now', stopPrimary);
        livePolite.textContent = stateWord.textContent;
        // R3: Zustaende mit Banner-Pfad zeigen ihn auch
        if (name === 'error') {
            showBanner('error', 'Störung bei der Antwort',
                'Die letzte Anfrage wurde nicht beantwortet.',
                'Erneut fragen — oder Serverlog prüfen, wenn es wieder passiert.', true);
        } else if (name === 'degraded') {
            showBanner('warning', 'Sprachausgabe nicht verfügbar',
                'Antworten stehen weiter als Text im Gespräch.',
                'ElevenLabs-Kontingent in config.json prüfen.');
        } else if (name === 'disconnected') {
            showBanner('error', 'Verbindung getrennt',
                'Jarvis verbindet automatisch neu (Versuch 2).',
                'Nachrichten werden erst nach der Verbindung gesendet.', true);
        }
        $$('[data-state]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.state === name)); });
    }

    $$('[data-state]').forEach(function (b) { b.addEventListener('click', function () { setState(b.dataset.state); }); });

    // Realistische Kette: Frage → Verarbeitung → Aktion → Antwort
    $('#sim-chain').addEventListener('click', function () {
        var steps = [['processing', 400], ['thinking', 900], ['action-running', 1400], ['speaking', 1200], ['listening', 0]];
        var t = 0;
        steps.forEach(function (st) { setTimeout(function () { setState(st[0]); }, t); t += st[1]; });
    });

    // ── Stop / Mute / Escape (Flows 6–8; R2/R6: Kaskade NUR fuer Esc) ───
    var RUNNING = ['speaking', 'action-running', 'processing', 'thinking'];
    function doStop() {
        if (RUNNING.indexOf(currentState) === -1) { livePolite.textContent = 'Nichts zu stoppen'; return; }
        setState('stopping');
        setTimeout(function () { setState('idle'); livePolite.textContent = 'Gestoppt'; }, 500);
    }
    $('#btn-stop').addEventListener('click', doStop); // Not-Halt: immer direkt

    function escCascade(e) {
        var ae = document.activeElement;
        // 1) gefuelltes fokussiertes Textfeld: nur Feld verlassen, kein Stop
        if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA') && ae.type !== 'radio' && ae.value) {
            ae.blur(); return;
        }
        // 2) Inline-Eingabe / Bestaetigungen / Loesch-Confirm
        if ($('#p-inline').classList.contains('on')) { inlineCancel(); return; }
        if ($('#s-confirm').classList.contains('on')) { $('#s-confirm').classList.remove('on'); $('#s-keep').blur(); return; }
        if (pendingDelete) { defuseDelete('Löschen abgebrochen'); return; }
        // 3) sichtbare App-Auswahl (nur Uebersicht sichtbar)
        if (selectedModule && !$('#view-control').hidden && !$('#sub-overview').hidden) { clearSelection(); return; }
        // 4) Stop, falls etwas laeuft
        doStop();
    }
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') escCascade(e); });

    $('#btn-mute').addEventListener('click', function () {
        muted = !muted;
        this.setAttribute('aria-pressed', String(muted));
        this.classList.toggle('danger-active', muted);
        this.setAttribute('aria-label', muted ? 'Mikrofon wieder aktivieren' : 'Mikrofon stummschalten');
        $('#dot-mic').className = 'f-dot ' + (muted ? 'err' : 'ok');
        $('#txt-mic').textContent = muted ? 'Mikrofon stumm' : 'Mikrofon bereit';
        livePolite.textContent = $('#txt-mic').textContent;
        setState(currentState);
    });

    // ── Navigation: Bereiche (Ebene 1) + Subviews in der Werkbank (Ebene 2)
    var currentPage = 'jarvis', currentSub = 'overview';

    function showSub(sub, focusHeading) {
        currentSub = sub;
        $('#sub-overview').hidden = sub !== 'overview';
        $('#view-music').hidden = sub !== 'music';
        $('#view-settings').hidden = sub !== 'settings';
        $$('[data-sub]').forEach(function (t) {
            t.setAttribute('aria-selected', String(t.dataset.sub === sub));
        });
        if (focusHeading) {
            var el = { overview: '#control-heading', music: '#music-heading', settings: '#settings-heading' }[sub];
            var h = $(el); if (h) h.focus();
        }
    }

    function goPage(page, focusHeading) {
        currentPage = page;
        if (page === 'control' && stage.classList.contains('mode-panel')) setWinMode('focus'); // Invariante Flow 32
        $('#view-jarvis').hidden = page !== 'jarvis';
        $('#view-control').hidden = page !== 'control';
        $$('.nav-tab').forEach(function (t) {
            t.setAttribute('aria-selected', String(t.dataset.view === page));
        });
        if (focusHeading !== false) {
            if (page === 'jarvis') { $('#main-heading').focus(); }
            else { showSub(currentSub, true); }
        }
    }
    $$('.nav-tab').forEach(function (t) { t.addEventListener('click', function () { goPage(t.dataset.view); }); });
    $$('[data-sub]').forEach(function (t) {
        t.addEventListener('click', function () {
            if (currentSub === 'settings' && dirty && t.dataset.sub !== 'settings') { $('#s-confirm').classList.add('on'); pendingSub = t.dataset.sub; return; }
            showSub(t.dataset.sub, true);
        });
    });

    function setWinMode(mode) {
        var talked = stage.classList.contains('has-talked');
        stage.className = 'stage mode-' + (mode === 'focus' ? 'focus' : mode) + (talked ? ' has-talked' : '');
        $$('[data-mode]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.mode === mode)); });
        $$('[data-winmode]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.winmode === mode)); });
        if (mode === 'panel' && currentPage !== 'jarvis') goPage('jarvis', false); // Invariante, kein Fokusklau
        // R8: Skip-Link-Ziel je Modus (Panel hat keine Journal-Ueberschrift)
        var skip = document.querySelector('.skip-link');
        if (mode === 'panel') { skip.href = '#ask-field'; skip.textContent = 'Zur Eingabe springen'; }
        else { skip.href = '#main-heading'; skip.textContent = 'Zum Gespräch springen'; }
    }
    $$('[data-mode]').forEach(function (b) { b.addEventListener('click', function () { setWinMode(b.dataset.mode); }); });
    $$('[data-winmode]').forEach(function (b) { b.addEventListener('click', function () { setWinMode(b.dataset.winmode); }); });

    // ── Journal: Suche + Kopieren + Pill (Flows 11–14) ──────────────────
    $('#search').addEventListener('input', function () {
        var q = this.value.trim().toLowerCase();
        var entries = $$('#journal .entry'), hits = 0;
        entries.forEach(function (e) {
            var match = !q || e.textContent.toLowerCase().indexOf(q) !== -1;
            e.classList.toggle('hidden', !match); if (match) hits++;
        });
        $('#search-count').textContent = q ? hits + ' von ' + entries.length + ' Einträgen' : '';
    });
    $$('.entry-copy').forEach(function (b) {
        b.addEventListener('click', function () {
            var old = b.textContent; b.textContent = 'Kopiert';
            livePolite.textContent = 'Antwort kopiert';
            setTimeout(function () { b.textContent = old; }, 2000);
        });
    });
    $('#copy-all').addEventListener('click', function () {
        var n = $$('#journal .entry:not(.hidden)').length, b = this;
        b.textContent = 'Kopiert (' + n + ' Einträge)';
        setTimeout(function () { b.textContent = 'Alles kopieren'; }, 2000);
    });
    var journal = $('#journal');
    journal.addEventListener('scroll', function () {
        var atEnd = journal.scrollTop + journal.clientHeight >= journal.scrollHeight - 8;
        if (atEnd) $('#new-pill').classList.remove('on');
    });
    $('#new-pill').addEventListener('click', function () {
        journal.scrollTop = journal.scrollHeight; this.classList.remove('on');
    });

    // Texteingabe (Flow 9): Strg+Enter simuliert Kette; R3: getrennt = blockiert
    function sendText(field) {
        var text = field.value.trim();
        if (!text) return;
        if (currentState === 'disconnected' || currentState === 'connecting') {
            liveAssertive.textContent = 'Nicht gesendet — keine Verbindung. Jarvis verbindet neu.';
            runningAction.textContent = ' — Nachricht wartet nicht, bitte nach der Verbindung erneut senden';
            return;
        }
        field.value = '';
        stage.classList.add('has-talked'); // R8: Begruessung weicht dem Gespraech
        var div = document.createElement('div');
        div.className = 'entry user';
        div.innerHTML = '<div class="entry-time">14:36</div><div class="entry-body"><div class="entry-speaker">Du</div><div class="entry-text"></div></div>';
        div.querySelector('.entry-text').textContent = text;
        journal.insertBefore(div, $('#new-pill'));
        if (journal.scrollTop + journal.clientHeight < journal.scrollHeight - 40) $('#new-pill').classList.add('on');
        $('#sim-chain').click();
    }
    $('#ask-field').addEventListener('keydown', function (e) {
        if (e.ctrlKey && e.key === 'Enter') sendText(this);
    });
    $('#ask2').addEventListener('keydown', function (e) {
        if (e.ctrlKey && e.key === 'Enter') sendText(this);
    });

    // ── App-Auswahl + Zonen + Selects (Flow 17–19) ──────────────────────
    var selectedModule = $('#mod-obsidian');
    function clearSelection() {
        $$('.app-module').forEach(function (m) { m.classList.remove('selected'); });
        selectedModule = null;
        livePolite.textContent = 'Auswahl aufgehoben';
    }
    $$('.app-module').forEach(function (m) {
        m.addEventListener('click', function (e) {
            if (e.target.closest('button') && !e.target.closest('.am-position')) return;
            $$('.app-module').forEach(function (x) { x.classList.remove('selected'); });
            m.classList.add('selected'); selectedModule = m;
        });
    });
    $$('[data-open]').forEach(function (b) {
        b.addEventListener('click', function () {
            b.disabled = true; var old = b.textContent; b.textContent = 'Öffnet …';
            setTimeout(function () {
                b.textContent = 'Geöffnet ✓'; livePolite.textContent = b.closest('.app-module').querySelector('.am-name').textContent + ' geöffnet';
                setTimeout(function () { b.textContent = old; b.disabled = false; }, 2000);
            }, 700);
        });
    });
    $$('.switch').forEach(function (s) {
        s.addEventListener('click', function () {
            var on = s.getAttribute('aria-checked') === 'true';
            s.setAttribute('aria-checked', String(!on));
            livePolite.textContent = 'Autostart ' + (!on ? 'an' : 'aus');
        });
    });
    // R7: Position speichern — generalisiert je Modul (Weg B)
    $$('.am-position .btn').forEach(function (b) {
        b.addEventListener('click', function () {
            var pos = b.closest('.am-position');
            var msg = pos.querySelector('.am-msg');
            var sels = pos.querySelectorAll('select');
            var name = b.closest('.app-module').querySelector('.am-name').textContent;
            b.disabled = true; msg.textContent = 'Speichert …'; msg.className = 'am-msg';
            setTimeout(function () {
                msg.textContent = 'Gespeichert ✓ — ' + sels[0].value + ' · ' + sels[1].value;
                livePolite.textContent = name + ': Monitor ' + sels[0].value + ', ' + sels[1].value + ' gespeichert';
                $('#bay-msg').textContent = name + ' → ' + sels[0].value + ' · ' + sels[1].value + ' gespeichert.';
                b.disabled = false;
            }, 600);
        });
    });
    // R7: Zonen-Zuweisung (Weg A) — richtige App, Chip wandert, sichtbares Feedback
    $$('.monitor-zones .zone').forEach(function (z) {
        z.addEventListener('click', function () {
            var bayMsg = $('#bay-msg');
            if (!selectedModule) {
                bayMsg.textContent = 'Erst eine App in der rechten Spalte auswählen — oder die Auswahlfelder im App-Modul nutzen.';
                bayMsg.className = 'bay-msg err';
                return;
            }
            var name = selectedModule.querySelector('.am-name').textContent;
            // Chip der App aus alter Zone entfernen, in neue setzen
            $$('.monitor-zones .chip').forEach(function (c) {
                if (c.textContent === name) c.remove();
            });
            var chip = document.createElement('span');
            chip.className = 'chip selected'; chip.textContent = name;
            z.appendChild(chip);
            z.style.borderColor = 'var(--brass-bright)';
            bayMsg.textContent = name + ' → ' + z.getAttribute('aria-label').split(' — ')[0] + ' gespeichert.';
            bayMsg.className = 'bay-msg';
            var modMsg = selectedModule.querySelector('.am-msg');
            if (modMsg) modMsg.textContent = 'Gespeichert ✓ — per Karte zugewiesen';
            livePolite.textContent = name + ': ' + z.getAttribute('aria-label').split(' — ')[0] + ' — gespeichert';
        });
    });

    // ── Profile (Flows 20–22; R6: jede Aktion entschärft offenes Confirm) ──
    var pendingDelete = null, renameTarget = null;
    function defuseDelete(msg) {
        if (!pendingDelete) return;
        pendingDelete.classList.remove('confirm');
        pendingDelete = null;
        $('#p-err').textContent = '';
        if (msg) livePolite.textContent = msg;
    }
    $('#p-new').addEventListener('click', function () {
        defuseDelete('Löschen abgebrochen');
        renameTarget = null;
        $('#p-inline').classList.add('on'); $('#p-name').focus();
    });
    // R7: Duplizieren/Umbenennen verdrahtet
    $$('.p-actions .btn-quiet').forEach(function (b) {
        if (b.id === 'p-new') return;
        b.addEventListener('click', function () {
            defuseDelete('Löschen abgebrochen');
            var active = document.querySelector('.p-tabs .p-tab[aria-selected="true"]');
            if (b.textContent === 'Duplizieren') {
                var copy = active.cloneNode(true);
                copy.textContent = active.textContent + ' (Kopie)';
                copy.setAttribute('aria-selected', 'false');
                active.parentNode.appendChild(copy);
                wireProfileTab(copy);
                livePolite.textContent = 'Profil „' + copy.textContent + '" angelegt';
            } else if (b.textContent === 'Umbenennen') {
                renameTarget = active;
                $('#p-inline').classList.add('on');
                $('#p-name').value = active.textContent;
                $('#p-name').focus(); $('#p-name').select();
            }
        });
    });
    function inlineCancel() { $('#p-inline').classList.remove('on'); $('#p-err').textContent = ''; $('#p-new').focus(); }
    $('#p-name').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') $('#p-ok').click();
        if (e.key === 'Escape') { e.stopPropagation(); inlineCancel(); }
    });
    $('#p-ok').addEventListener('click', function () {
        var name = $('#p-name').value.trim();
        if (!name) { $('#p-err').textContent = 'Name darf nicht leer sein.'; return; }
        if (renameTarget) {
            renameTarget.textContent = name;
            livePolite.textContent = 'Profil umbenannt in „' + name + '"';
            renameTarget = null;
        } else {
            var btn = document.createElement('button');
            btn.className = 'p-tab'; btn.setAttribute('role', 'tab'); btn.setAttribute('aria-selected', 'false');
            btn.textContent = name; $('.p-tabs').appendChild(btn);
            wireProfileTab(btn);
            livePolite.textContent = 'Profil „' + name + '" angelegt';
        }
        $('#p-name').value = ''; inlineCancel();
    });
    function wireProfileTab(t) {
        t.addEventListener('click', function () {
            defuseDelete();
            $$('.p-tabs .p-tab').forEach(function (x) { x.setAttribute('aria-selected', 'false'); });
            t.setAttribute('aria-selected', 'true');
            livePolite.textContent = 'Profil „' + t.textContent + '" aktiv';
        });
    }
    $$('.p-tabs .p-tab').forEach(wireProfileTab);
    $('#p-del').addEventListener('click', function () {
        var active = document.querySelector('.p-tabs .p-tab[aria-selected="true"]');
        var count = $$('.p-tabs .p-tab').length;
        if (count <= 1) { $('#p-err').textContent = 'Mindestens ein Profil bleibt bestehen.'; return; }
        if (pendingDelete === active) {
            active.remove(); pendingDelete = null;
            var first = document.querySelector('.p-tabs .p-tab');
            first.setAttribute('aria-selected', 'true');
            liveAssertive.textContent = 'Profil gelöscht';
        } else {
            pendingDelete = active; active.classList.add('confirm');
            liveAssertive.textContent = 'Nochmal „Löschen" klicken, um „' + active.textContent + '" zu löschen';
            $('#p-err').textContent = 'Nochmal klicken zum Löschen von „' + active.textContent + '".';
        }
    });

    // ── Settings (Flows 25–26): dirty, Validierung, Fokus-Management ────
    var dirty = false, pendingSub = null;
    $$('#view-settings input').forEach(function (i) {
        i.addEventListener('input', function () { dirty = true; $('#unsaved').classList.add('on'); });
    });
    $('#s-city').addEventListener('blur', function () {
        var bad = !this.value.trim();
        $('#f-city-wrap').classList.toggle('invalid', bad);
        this.setAttribute('aria-invalid', String(bad));
    });
    $('#s-save').addEventListener('click', function () {
        var city = $('#s-city');
        if (!city.value.trim()) {
            $('#f-city-wrap').classList.add('invalid');
            liveAssertive.textContent = 'Speichern fehlgeschlagen: Stadt darf nicht leer sein.';
            city.focus(); return;
        }
        var b = this; b.disabled = true;
        $('#s-msg').textContent = 'Speichert …';
        setTimeout(function () {
            $('#s-msg').textContent = 'Gespeichert ✓';
            dirty = false; $('#unsaved').classList.remove('on'); b.disabled = false;
            livePolite.textContent = 'Einstellungen gespeichert';
        }, 600);
    });
    $('#s-cancel').addEventListener('click', function () {
        if (dirty) { $('#s-confirm').classList.add('on'); pendingSub = 'overview'; }
        else { showSub('overview', true); }
    });
    $('#s-discard').addEventListener('click', function () {
        dirty = false; $('#unsaved').classList.remove('on'); $('#s-confirm').classList.remove('on');
        showSub(pendingSub || 'overview', true);
    });
    $('#s-keep').addEventListener('click', function () { $('#s-confirm').classList.remove('on'); $('#s-name').focus(); });

    // ── Musik (Flows 27–28) ─────────────────────────────────────────────
    $$('.music-item').forEach(function (item) {
        item.addEventListener('click', function () {
            $$('.music-item').forEach(function (x) {
                x.setAttribute('aria-pressed', 'false');
                var meta = x.querySelector('.m-meta'); if (meta) meta.remove();
            });
            item.setAttribute('aria-pressed', 'true');
            var meta = document.createElement('span'); meta.className = 'm-meta'; meta.textContent = 'spielt beim Start';
            item.appendChild(meta);
            var name = item.textContent.replace('spielt beim Start', '').trim();
            $('#music-current').textContent = 'Spielt beim nächsten Start: ' + name;
            livePolite.textContent = 'Musik gewählt: ' + name;
        });
    });
    $('#music-clear').addEventListener('click', function () {
        $$('.music-item').forEach(function (x) {
            x.setAttribute('aria-pressed', 'false');
            var meta = x.querySelector('.m-meta'); if (meta) meta.remove();
        });
        $('#music-current').textContent = 'Keine Musik ausgewählt.';
        livePolite.textContent = 'Startmusik entfernt';
    });

    // Orb-Klick = Zuhören toggeln (Flow 2)
    orb.addEventListener('click', function () {
        setState(currentState === 'listening' ? 'idle' : 'listening');
    });

    setState('listening');
})();
