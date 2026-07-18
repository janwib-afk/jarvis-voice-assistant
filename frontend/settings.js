// Jarvis V2 — Einstellungen (inline im Kontrollzentrum)
// Laedt/speichert UI-editierbare Felder ueber GET/POST /settings (Token-Header).
// API-Keys verlassen den Server nie; der Mikrofonmodus ist rein clientseitig.
// Sichtbarkeit steuert main.js ueber den Sub-View (cc-view-settings) — hier
// lebt nur die Formular-Logik.
(function () {
    const form = document.getElementById('settings-form');
    const msg = document.getElementById('settings-msg');
    const TEXT_KEYS = [
        'user_name', 'user_address', 'user_role', 'city',
        'elevenlabs_voice_id', 'obsidian_inbox_path', 'obsidian_inbox_folder',
        'music_folder',
    ];
    let loaded = null; // Stand vom Server — Basis fuer den Diff beim Speichern
    let loadedRevision = '';

    function authHeaders() {
        return {
            'X-Jarvis-Token': window.JARVIS_TOKEN || '',
            'Content-Type': 'application/json',
        };
    }

    // Apps-Zeilenformat: "Name = befehl" oder nur "befehl" pro Zeile.
    // Legacy-Strings aus der Config werden als rohe Befehlszeile angezeigt.
    function appsToLines(apps) {
        return (apps || []).map((a) => {
            if (typeof a === 'string') return a;
            const cmd = a.command || '';
            return (a.name && a.name !== cmd) ? a.name + ' = ' + cmd : cmd;
        }).join('\n');
    }

    function parseAppsLines(text, loadedApps) {
        // Felder eines bestehenden Eintrags mit gleichem Befehl uebernehmen
        // (autostart, id, placement, process_name) — ein Save aus dem Textfeld
        // darf Toggle- und Platzierungs-Einstellungen nie verwerfen.
        // Neue Zeilen und Legacy-Strings gelten als autostart:true.
        const byCommand = {};
        for (const a of loadedApps || []) {
            if (a && typeof a === 'object' && a.command) byCommand[a.command] = a;
        }
        const entries = [];
        for (const rawLine of text.split('\n')) {
            const line = rawLine.trim();
            if (!line) continue;
            let name = '';
            let command = line;
            // Trenner ist das ERSTE " = " mit Leerzeichen — schuetzt URLs mit
            // '=' wie obsidian://open?vault=x.
            const sep = line.indexOf(' = ');
            if (sep > 0) {
                name = line.slice(0, sep).trim();
                command = line.slice(sep + 3).trim();
            }
            if (!command) continue;
            const prev = Object.prototype.hasOwnProperty.call(byCommand, command)
                ? byCommand[command] : null;
            const entry = {
                command: command,
                type: command.includes('://') ? 'url' : 'process',
                autostart: prev ? prev.autostart !== false : true,
            };
            if (name) entry.name = name;
            if (prev) {
                if (prev.id) entry.id = prev.id;
                if (prev.placement) entry.placement = prev.placement;
                if (prev.process_name) entry.process_name = prev.process_name;
                // Doppelte Befehlszeilen erben die ID nicht doppelt —
                // sonst wuerde die Duplikat-ID-Validierung den Save ablehnen.
                delete byCommand[command];
            }
            entries.push(entry);
        }
        return entries;
    }

    function setMsg(text, isError) {
        msg.textContent = text;
        msg.className = isError ? 'error' : 'ok';
        // Fokus-Management (docs/ux A11y §2): bei Fehlern landet der Fokus auf
        // der Meldung — Serverfehler sind global und keinem Feld zuordenbar.
        if (isError && text) {
            msg.tabIndex = -1;
            msg.focus();
        }
    }

    // Ungespeicherte Aenderungen sichtbar machen + Verwerfen absichern.
    const dirtyPill = document.getElementById('settings-dirty');
    const confirmRow = document.getElementById('settings-confirm');
    let dirty = false;
    function setDirty(value) {
        dirty = value;
        if (dirtyPill) dirtyPill.hidden = !value;
        if (!value && confirmRow) confirmRow.hidden = true;
    }
    form.addEventListener('input', () => setDirty(true));

    // Frische Werte vom Server ins Formular laden — wird von main.js beim
    // Wechsel auf den Einstellungen-Sub-View aufgerufen.
    async function openSettings() {
        setMsg('', false);
        setDirty(false);
        const mic = localStorage.getItem('jarvis.micMode') || 'auto';
        const radio = form.querySelector(`input[name="micMode"][value="${mic}"]`);
        if (radio) radio.checked = true;
        try {
            const resp = await JarvisWire.fetchV1('/settings', { headers: authHeaders() });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            loaded = data.settings || {};
            // Revision der geladenen Basis merken (RFC-0003 D6): sie geht beim
            // Speichern als If-Match zurueck, damit eine zwischenzeitliche
            // Aenderung nicht stillschweigend ueberschrieben wird.
            loadedRevision = data.revision || '';
            for (const key of TEXT_KEYS) form.elements[key].value = loaded[key] || '';
            form.elements['apps'].value = appsToLines(loaded.apps);
        } catch (e) {
            loaded = null;
            loadedRevision = '';
            setMsg('Einstellungen konnten nicht geladen werden — läuft der Server?', true);
        }
    }

    // "Schliessen" heisst jetzt: zurueck zur Kontrollzentrum-Übersicht.
    function closeSettings() {
        setDirty(false);
        if (window.applyControlView) window.applyControlView('overview');
        const h = document.getElementById('control-heading');
        if (h) h.focus();
    }

    // Abbrechen mit ungespeicherten Aenderungen: erst rueckfragen
    // (sheet-dismiss-confirm, docs/ux Teil 8).
    function requestClose() {
        if (dirty && confirmRow) {
            confirmRow.hidden = false;
            const keep = document.getElementById('btn-keep');
            if (keep) keep.focus();
            return;
        }
        closeSettings();
    }
    const btnDiscard = document.getElementById('btn-discard');
    const btnKeep = document.getElementById('btn-keep');
    if (btnDiscard) btnDiscard.addEventListener('click', () => { closeSettings(); });
    if (btnKeep) btnKeep.addEventListener('click', () => {
        confirmRow.hidden = true;
        const first = form.querySelector('input[type="text"]');
        if (first) first.focus();
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Mikrofonmodus lokal speichern und sofort anwenden.
        const mic = form.querySelector('input[name="micMode"]:checked');
        if (mic) {
            localStorage.setItem('jarvis.micMode', mic.value);
            if (window.applyMicMode) window.applyMicMode();
        }

        // Nur geaenderte Felder senden.
        const updates = {};
        if (loaded) {
            for (const key of TEXT_KEYS) {
                const val = form.elements[key].value.trim();
                if (val !== (loaded[key] || '')) updates[key] = val;
            }
            // Diff ueber das normalisierte Zeilenformat — vermeidet Fehl-Diffs
            // zwischen Legacy-Strings und Objektform.
            const appsText = form.elements['apps'].value
                .split('\n').map(s => s.trim()).filter(Boolean).join('\n');
            if (appsText !== appsToLines(loaded.apps)) {
                updates.apps = parseAppsLines(appsText, loaded.apps);
            }
        }
        if (Object.keys(updates).length === 0) {
            setMsg('Gespeichert.', false);
            setTimeout(closeSettings, 800);
            return;
        }

        try {
            const headers = authHeaders();
            if (loadedRevision) headers['If-Match'] = loadedRevision;
            const resp = await JarvisWire.fetchV1('/settings', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(updates),
            });
            const data = await resp.json().catch(() => ({}));
            if (resp.status === 409) {
                // Konflikt: NICHT behaupten, gespeichert zu haben. Serverstand neu
                // laden, Formular kontrolliert aktualisieren, Fokus auf die Meldung.
                await openSettings();
                setMsg('Die Einstellungen wurden zwischenzeitlich geändert und neu '
                       + 'geladen. Bitte prüfe deine Eingaben und speichere erneut.', true);
                return;
            }
            if (!resp.ok || !data.ok) {
                setMsg((data.errors || ['Speichern fehlgeschlagen.']).join(' '), true);
                return;
            }
            if (data.revision) loadedRevision = data.revision;
            loaded = Object.assign({}, loaded, updates);
            setDirty(false);
            setMsg('Gespeichert ✓ — wirkt ab der nächsten Antwort.', false);
            // Command Center nachziehen (neue App-Buttons, Musikordner etc.).
            if (window.loadDashboardState) window.loadDashboardState();
            if (window.loadMusic) window.loadMusic();
            setTimeout(closeSettings, 1000);
        } catch (err) {
            if (window.showErrorBanner) {
                window.showErrorBanner({
                    component: 'config',
                    text: 'Einstellungen konnten nicht gespeichert werden.',
                    hint: 'Läuft der Server? Details im Server-Log.',
                });
            }
            setMsg('Netzwerkfehler beim Speichern.', true);
        }
    });

    document.getElementById('btn-settings-cancel').addEventListener('click', requestClose);
    window.openSettings = openSettings;
})();
