// Jarvis V2 — Settings-Overlay
// Laedt/speichert UI-editierbare Felder ueber GET/POST /settings (Token-Header).
// API-Keys verlassen den Server nie; der Mikrofonmodus ist rein clientseitig.
(function () {
    const view = document.getElementById('settings-view');
    const form = document.getElementById('settings-form');
    const msg = document.getElementById('settings-msg');
    const TEXT_KEYS = [
        'user_name', 'user_address', 'user_role', 'city',
        'elevenlabs_voice_id', 'obsidian_inbox_path', 'obsidian_inbox_folder',
    ];
    let loaded = null; // Stand vom Server — Basis fuer den Diff beim Speichern

    function authHeaders() {
        return {
            'X-Jarvis-Token': window.JARVIS_TOKEN || '',
            'Content-Type': 'application/json',
        };
    }

    function setMsg(text, isError) {
        msg.textContent = text;
        msg.className = isError ? 'error' : 'ok';
    }

    async function openSettings() {
        setMsg('', false);
        view.classList.remove('hidden');
        const mic = localStorage.getItem('jarvis.micMode') || 'auto';
        const radio = form.querySelector(`input[name="micMode"][value="${mic}"]`);
        if (radio) radio.checked = true;
        try {
            const resp = await fetch('/settings', { headers: authHeaders() });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            loaded = data.settings || {};
            for (const key of TEXT_KEYS) form.elements[key].value = loaded[key] || '';
            form.elements['apps'].value = (loaded.apps || []).join('\n');
        } catch (e) {
            loaded = null;
            setMsg('Einstellungen konnten nicht geladen werden — läuft der Server?', true);
        }
    }

    function closeSettings() {
        view.classList.add('hidden');
    }

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
            const apps = form.elements['apps'].value
                .split('\n').map(s => s.trim()).filter(Boolean);
            if (JSON.stringify(apps) !== JSON.stringify(loaded.apps || [])) updates.apps = apps;
        }
        if (Object.keys(updates).length === 0) {
            setMsg('Gespeichert.', false);
            setTimeout(closeSettings, 800);
            return;
        }

        try {
            const resp = await fetch('/settings', {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify(updates),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) {
                setMsg((data.errors || ['Speichern fehlgeschlagen.']).join(' '), true);
                return;
            }
            loaded = Object.assign({}, loaded, updates);
            setMsg('Einstellungen gespeichert — wirken ab der nächsten Antwort.', false);
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

    document.getElementById('btn-settings-cancel').addEventListener('click', closeSettings);
    view.addEventListener('click', (e) => { if (e.target === view) closeSettings(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !view.classList.contains('hidden')) closeSettings();
    });
    document.getElementById('btn-settings').addEventListener('click', openSettings);
    window.openSettings = openSettings;
})();
