// Jarvis V2 — Musik (Kontrollzentrum-Sub-View)
// Listet .mp3-Dateien aus dem konfigurierten music_folder (GET /music/files)
// und speichert die Auswahl fuer den naechsten Sessionstart (POST /music/selection).
// Sicherheit: ueber die API wandern nur DATEINAMEN, nie Pfade — der Server und
// launch-session.ps1 validieren beide gegen den Musikordner.
(function () {
    const listEl = document.getElementById('music-list');
    const msgEl = document.getElementById('music-msg');
    const folderEl = document.getElementById('music-folder');
    const selectedEl = document.getElementById('music-selected');
    const statusEl = document.getElementById('music-status');

    function authHeaders() {
        return {
            'X-Jarvis-Token': window.JARVIS_TOKEN || '',
            'Content-Type': 'application/json',
        };
    }

    function setMsg(text, isError) {
        msgEl.textContent = text || '';
        msgEl.classList.toggle('err', !!isError);
    }

    // Kleiner Status auf der Jarvis-Seite — leer, wenn nichts gewaehlt ist
    // (das Element kollabiert dann per CSS :empty).
    function renderJarvisStatus(selected) {
        statusEl.textContent = selected ? 'Spielt beim nächsten Start: ' + selected : '';
    }

    function render(data) {
        folderEl.textContent = data.folder || 'Nicht konfiguriert';
        selectedEl.textContent = data.selected || 'Keine Musik';
        renderJarvisStatus(data.selected);
        listEl.textContent = '';
        if (!data.ok) {
            setMsg(data.error || 'Musikordner konnte nicht gelesen werden.', true);
            return;
        }
        if (!data.folder) {
            setMsg('Kein Musikordner konfiguriert — unter Einstellungen setzen.', false);
            return;
        }
        if (!data.files || data.files.length === 0) {
            setMsg('Keine MP3-Dateien im Ordner gefunden.', false);
            return;
        }
        setMsg('', false);
        for (const file of data.files) {
            const li = document.createElement('li');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'music-item' + (file.name === data.selected ? ' selected' : '');
            btn.textContent = file.name;
            btn.title = '„' + file.name + '" für den nächsten Sessionstart auswählen';
            btn.addEventListener('click', () => selectMusic(file.name));
            li.appendChild(btn);
            listEl.appendChild(li);
        }
    }

    async function loadMusic() {
        try {
            const resp = await fetch('/music/files', { headers: authHeaders() });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            render(await resp.json());
        } catch (e) {
            setMsg('Musikliste konnte nicht geladen werden — läuft der Server?', true);
        }
    }

    async function selectMusic(name) {
        try {
            const resp = await fetch('/music/selection', {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({ file: name }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) {
                setMsg((data.errors || ['Auswahl konnte nicht gespeichert werden.']).join(' '), true);
                return;
            }
            await loadMusic();
            setMsg(name
                ? '„' + name + '" spielt beim nächsten Sessionstart.'
                : 'Auswahl entfernt — nächster Start ohne Musik.', false);
        } catch (e) {
            setMsg('Auswahl konnte nicht gespeichert werden — läuft der Server?', true);
        }
    }

    document.getElementById('btn-music-clear').addEventListener('click', () => selectMusic(''));
    document.getElementById('btn-music-reload').addEventListener('click', loadMusic);

    // Fuer main.js: beim Wechsel auf den Musik-Sub-View frisch laden.
    window.loadMusic = loadMusic;
    // Einmalig beim Start: fuellt den "Nächste Musik"-Status der Jarvis-Seite.
    // Bewusst KEIN wiederkehrender Refresh — die Jarvis-Seite pollt keine
    // Verwaltungsdaten; weitere Loads passieren nur im Kontrollzentrum.
    loadMusic();
})();
