// Jarvis V2 — Frontend
const orb = document.getElementById('orb');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');

if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    status.textContent = 'Oeffne Jarvis ueber http://localhost:8340 — Mikrofon funktioniert nur auf localhost.';
}

const SVG_MIC = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/>
  <path d="M19 10v1a7 7 0 0 1-14 0v-1"/>
  <line x1="12" y1="18" x2="12" y2="22"/>
</svg>`;

const SVG_MIC_MUTED = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <line x1="2" y1="2" x2="22" y2="22"/>
  <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V5a3 3 0 0 0-5.94-.6"/>
  <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2"/>
  <line x1="12" y1="19" x2="12" y2="22"/>
</svg>`;

let ws;
let audioQueue = [];
let isPlaying = false;
let audioUnlocked = false;
let isMuted = false;
let hasGreeted = false;
let reconnectAttempts = 0;

// Mikrofonmodus: 'auto' (immer zuhoeren), 'ptt' (Leertaste halten), 'off' (Start stumm)
let micMode = localStorage.getItem('jarvis.micMode') || 'auto';

// Zentraler UI-Zustand fuers Status-Center
const uiState = { connected: false, micMuted: false, jarvisState: 'idle', lastError: '', warnings: '' };

function renderStatusCenter() {
    const labels = { idle: 'Bereit', listening: 'Hört zu', thinking: 'Denkt', speaking: 'Spricht', muted: 'Stumm', error: 'Fehler' };
    document.getElementById('sc-conn').className = 'sc-dot ' + (uiState.connected ? 'ok' : 'err');
    document.getElementById('sc-mic').className = 'sc-dot ' + (uiState.micMuted ? 'off' : 'ok');
    document.getElementById('sc-state').textContent =
        uiState.connected ? (labels[uiState.jarvisState] || 'Bereit') : 'Getrennt';
    const scError = document.getElementById('sc-error');
    const msg = uiState.lastError || uiState.warnings;
    scError.textContent = msg;
    scError.title = msg;
    scError.classList.toggle('warn', !uiState.lastError && !!uiState.warnings);
}

function reportError(msg) {
    uiState.lastError = msg;
    renderStatusCenter();
}

// ── Fehler-Banner ────────────────────────────────────────────────────────────
// Verstaendliche, dismissible Fehleranzeige — nicht nur die Status-Center-Zeile.
const ERROR_LABELS = {
    tts: 'Sprachausgabe', llm: 'KI', mic: 'Mikrofon', browser: 'Browser',
    action: 'Aktion', config: 'Konfiguration', audio: 'Audio', ws: 'Verbindung',
};
const PERSISTENT_ERRORS = ['mic', 'config', 'ws'];
const MAX_BANNERS = 3;

function showErrorBanner(err) {
    const component = err.component || '';
    const text = err.text || '';
    const hint = err.hint || '';
    const stack = document.getElementById('error-stack');

    // Dedupe: gleicher Fehler ersetzt den alten Banner statt sich zu stapeln.
    stack.querySelectorAll('.error-banner').forEach(b => {
        if (b.dataset.component === component && b.dataset.text === text) b.remove();
    });
    while (stack.children.length >= MAX_BANNERS) stack.removeChild(stack.firstChild);

    const banner = document.createElement('div');
    banner.className = 'error-banner';
    banner.dataset.component = component;
    banner.dataset.text = text;

    const label = document.createElement('span');
    label.className = 'eb-label';
    label.textContent = ERROR_LABELS[component] || 'Fehler';
    const msg = document.createElement('span');
    msg.className = 'eb-text';
    msg.textContent = text;
    const close = document.createElement('button');
    close.className = 'eb-close';
    close.title = 'Schließen';
    close.textContent = '×';
    close.addEventListener('click', () => banner.remove());

    banner.appendChild(label);
    banner.appendChild(msg);
    if (hint) {
        const hintEl = document.createElement('div');
        hintEl.className = 'eb-hint';
        hintEl.textContent = hint;
        banner.appendChild(hintEl);
    }
    banner.appendChild(close);
    stack.appendChild(banner);

    if (!PERSISTENT_ERRORS.includes(component)) {
        setTimeout(() => banner.remove(), 10000);
    }
    reportError(text);
    if (component === 'llm' || component === 'ws') flashOrbError();
}
window.showErrorBanner = showErrorBanner;

function dismissErrorBanners(component) {
    document.querySelectorAll('#error-stack .error-banner').forEach(b => {
        if (b.dataset.component === component) b.remove();
    });
}

// ── UI-Modus: Panel (kompakt, always-on-top) / Fokus (gross) ────────────────
const btnMode = document.getElementById('btn-mode');

function currentUiMode() {
    return localStorage.getItem('jarvis.uiMode') === 'panel' ? 'panel' : 'focus';
}

function updateModeButton() {
    const mode = currentUiMode();
    btnMode.textContent = mode === 'panel' ? '⛶' : '⊡';
    btnMode.title = mode === 'panel' ? 'Fokus-Modus' : 'Panel-Modus';
}

function applyUiMode(mode, callNative = true) {
    document.documentElement.className = 'mode-' + mode;
    localStorage.setItem('jarvis.uiMode', mode);
    updateModeButton();
    // Natives Fenster nachziehen — im Browser (ohne pywebview) nur CSS-Layout.
    if (callNative && window.pywebview && window.pywebview.api && window.pywebview.api.set_window_mode) {
        window.pywebview.api.set_window_mode(mode);
    }
}

btnMode.addEventListener('click', () => {
    applyUiMode(currentUiMode() === 'panel' ? 'focus' : 'panel');
});
// Sobald die pywebview-Bruecke bereit ist, Fenstergroesse an den Modus anpassen.
window.addEventListener('pywebviewready', () => applyUiMode(currentUiMode()));

// Gemeinsamer Sendepfad fuer Sprache und Texteingabe.
function sendUtterance(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        reportError('Jarvis-Server nicht erreichbar — Nachricht nicht gesendet.');
        return false;
    }
    addTranscript('user', text);
    setOrbState('thinking');
    status.textContent = 'Jarvis denkt nach...';
    ws.send(JSON.stringify({ text }));
    return true;
}

// Unlock audio on ANY user interaction
function unlockAudio() {
    if (!audioUnlocked) {
        const silent = new Audio('data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA');
        silent.play().then(() => {
            audioUnlocked = true;
            console.log('[jarvis] Audio unlocked');
        }).catch(() => {});
    }
}
document.addEventListener('click', unlockAudio, { once: false });
document.addEventListener('touchstart', unlockAudio, { once: false });
document.addEventListener('keydown', unlockAudio, { once: false });

function connect() {
    // Session-Token wird vom Server in die Seite injiziert (window.JARVIS_TOKEN).
    const token = encodeURIComponent(window.JARVIS_TOKEN || '');
    ws = new WebSocket(`ws://${location.host}/ws?token=${token}`);
    ws.onopen = () => {
        console.log('[jarvis] WebSocket connected');
        uiState.connected = true;
        uiState.lastError = '';
        reconnectAttempts = 0;
        dismissErrorBanners('ws');
        renderStatusCenter();
        status.textContent = '';
        if (!hasGreeted) {
            // Begruessung nur einmal — nicht bei jedem Reconnect wiederholen.
            hasGreeted = true;
            setOrbState('thinking');
            ws.send(JSON.stringify({ text: 'Jarvis activate' }));
        } else {
            status.textContent = 'Wieder verbunden.';
            if (!isPlaying) resumeListening(0);
        }
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'response') {
            addTranscript('jarvis', data.text);
            if (data.audio && data.audio.length > 0) {
                queueAudio(data.audio);
            } else {
                setOrbState('idle');
                resumeListening(500);
            }
        } else if (data.type === 'status') {
            status.textContent = data.text;
        } else if (data.type === 'health') {
            uiState.warnings = (data.warnings || []).join(' · ');
            renderStatusCenter();
        } else if (data.type === 'action') {
            addActionEntry(data);
        } else if (data.type === 'error') {
            showErrorBanner(data);
            if (!isPlaying) {
                setOrbState('idle');
                resumeListening(500);
            }
        }
    };
    ws.onerror = () => {
        reportError('Verbindungsfehler');
    };
    ws.onclose = () => {
        uiState.connected = false;
        reportError('Verbindung verloren');
        reconnectAttempts++;
        // Kein Banner pro Reconnect-Versuch (Server-Neustart!) — erst wenn es haengt.
        if (reconnectAttempts === 3) {
            showErrorBanner({
                component: 'ws',
                text: 'Verbindung zum Jarvis-Server verloren.',
                hint: 'Läuft der Server? Es wird automatisch neu verbunden — das Mikrofon bleibt nutzbar.',
            });
        }
        // Exponentielles Backoff (3s → 30s Cap) statt Dauerfeuer alle 3s.
        const delay = Math.min(3000 * 2 ** (reconnectAttempts - 1), 30000);
        status.textContent = `Server nicht erreichbar — neuer Versuch in ${Math.round(delay / 1000)}s`;
        setTimeout(connect, delay);
    };
}

function queueAudio(base64Audio) {
    audioQueue.push(base64Audio);
    if (!isPlaying) playNext();
}

function playNext() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        setOrbState('idle');
        status.textContent = '';
        resumeListening(500);
        return;
    }
    isPlaying = true;
    setOrbState('speaking');
    status.textContent = '';
    if (isListening) {
        recognition.stop();
        isListening = false;
    }

    const b64 = audioQueue.shift();
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => { URL.revokeObjectURL(url); playNext(); };
    audio.onerror = () => { URL.revokeObjectURL(url); playNext(); };
    audio.play().catch(err => {
        console.warn('[jarvis] Autoplay blocked, waiting for click...');
        status.textContent = 'Klicke irgendwo damit Jarvis sprechen kann.';
        showErrorBanner({ component: 'audio', text: 'Audio blockiert — Klick benötigt.', hint: 'Einmal irgendwo in das Fenster klicken.' });
        setOrbState('idle');
        // Wait for click then retry
        document.addEventListener('click', function retry() {
            document.removeEventListener('click', retry);
            audio.play().then(() => {
                dismissErrorBanners('audio');
                setOrbState('speaking');
                status.textContent = '';
            }).catch(() => playNext());
        });
    });
}

// Speech Recognition
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
let isListening = false;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'de-DE';
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
        const last = event.results[event.results.length - 1];
        if (last.isFinal) {
            const text = last[0].transcript.trim();
            if (!text) return;
            const muteOff = /\b(mikro(fon)? (an|ein)|entstummen|stummschaltung (aufheben|aus))\b/i;
            const muteOn  = /\b(stumm|mikro(fon)? aus|stummschalten)\b/i;
            if (muteOff.test(text)) { isMuted = false; updateMuteButton(); if (!isPlaying && micMode === 'auto') startListening(); return; }
            if (muteOn.test(text))  { isMuted = true;  updateMuteButton(); setOrbState('idle'); status.textContent = 'Mikrofon stumm'; return; }
            if (isMuted) return;
            sendUtterance(text);
        }
    };

    recognition.onend = () => {
        isListening = false;
        if (!isPlaying && micMode === 'auto') setTimeout(startListening, 300);
    };

    recognition.onerror = (event) => {
        isListening = false;
        if (event.error === 'not-allowed' || event.error === 'audio-capture') {
            setOrbState('error');
            status.textContent = 'Kein Mikrofon-Zugriff. Erlaube das Mikrofon in der Adressleiste und lade die Seite neu.';
            showErrorBanner({ component: 'mic', text: 'Kein Mikrofon-Zugriff.', hint: 'Mikrofon in der Adressleiste erlauben und Seite neu laden.' });
        } else if (event.error === 'no-speech' || event.error === 'aborted') {
            if (!isPlaying && micMode === 'auto') setTimeout(startListening, 300);
        } else {
            if (micMode === 'auto') setTimeout(startListening, 1000);
        }
    };
}

function startListening() {
    if (isPlaying || !recognition) return;
    try { recognition.start(); } catch (e) { /* laeuft ggf. schon */ }
    isListening = true;
    // Bei Stummschaltung laeuft die Erkennung weiter (Sprach-Entstummen),
    // der Orb zeigt aber 'muted' statt 'listening'.
    setOrbState(isMuted ? 'idle' : 'listening');
    if (!isMuted) status.textContent = '';
}

// Zuhoeren fortsetzen — nur im Auto-Modus (ptt/off starten nicht von selbst).
function resumeListening(delay) {
    if (micMode !== 'auto') {
        if (!isPlaying) setOrbState('idle');
        return;
    }
    setTimeout(startListening, delay);
}

// Mikrofonmodus anwenden (wird auch von settings.js nach dem Speichern gerufen).
function applyMicMode() {
    micMode = localStorage.getItem('jarvis.micMode') || 'auto';
    if (micMode === 'auto') {
        if (!isPlaying && !isListening) startListening();
    } else {
        if (isListening && recognition) { recognition.stop(); isListening = false; }
        if (uiState.jarvisState === 'listening') setOrbState('idle');
    }
}
window.applyMicMode = applyMicMode;

// Push-to-Talk: Leertaste halten (nicht in Eingabefeldern).
document.addEventListener('keydown', (e) => {
    if (micMode !== 'ptt' || e.code !== 'Space' || e.repeat) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
    e.preventDefault();
    startListening();
});
document.addEventListener('keyup', (e) => {
    if (micMode !== 'ptt' || e.code !== 'Space') return;
    if (isListening && recognition) {
        // stop() statt abort(): das finale Ergebnis wird noch geliefert.
        recognition.stop();
        isListening = false;
    }
    if (uiState.jarvisState === 'listening') setOrbState('idle');
});

orb.addEventListener('click', () => {
    if (isPlaying) return;
    if (isListening) {
        recognition.stop();
        isListening = false;
        setOrbState('idle');
        status.textContent = 'Pausiert. Klicke zum Fortsetzen.';
    } else {
        startListening();
    }
});

// ── Orb-Zustaende: idle / listening / thinking / speaking / muted / error ──
function setOrbState(state) {
    // 'idle' + Stummschaltung wird als eigener Zustand 'muted' angezeigt.
    const effective = (state === 'idle' && isMuted) ? 'muted' : state;
    orb.className = effective;
    uiState.jarvisState = effective;
    renderStatusCenter();
    status.classList.toggle('active', effective !== 'idle' && effective !== 'muted');
}

let orbErrorRevert = null;
function flashOrbError() {
    const cur = uiState.jarvisState;
    // Laufende Antwort nicht unterbrechen; persistenten Fehler nicht ueberschreiben.
    if (cur === 'speaking' || cur === 'thinking' || cur === 'error') return;
    const prev = (cur === 'muted') ? 'idle' : cur;
    setOrbState('error');
    clearTimeout(orbErrorRevert);
    orbErrorRevert = setTimeout(() => {
        if (uiState.jarvisState === 'error') setOrbState(prev);
    }, 2500);
}

function updateMuteButton() {
    uiState.micMuted = isMuted;
    const btn = document.getElementById('mute-btn');
    if (isMuted) {
        btn.innerHTML = SVG_MIC_MUTED;
        btn.classList.add('muted');
    } else {
        btn.innerHTML = SVG_MIC;
        btn.classList.remove('muted');
    }
    // Orb-Anzeige mit dem Mute-Zustand synchronisieren.
    if (uiState.jarvisState === 'idle' || uiState.jarvisState === 'muted') {
        setOrbState('idle');
    } else {
        renderStatusCenter();
    }
}

function toggleMute() {
    isMuted = !isMuted;
    updateMuteButton();
    if (isMuted) {
        setOrbState('idle');
        status.textContent = 'Mikrofon stumm';
    } else {
        status.textContent = '';
        if (!isPlaying && micMode === 'auto') startListening();
    }
}

document.getElementById('mute-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleMute();
});

// ── Transcript: letzte 20 Nachrichten, Suche, Kopieren, Timestamps ─────────
const MAX_TRANSCRIPT = 20;
let transcriptLog = [];
const transcriptSearch = document.getElementById('transcript-search');

function addTranscript(role, text) {
    const time = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    transcriptLog.push({ role, text, time });
    if (transcriptLog.length > MAX_TRANSCRIPT) transcriptLog.shift();
    if (role === 'jarvis') {
        // Letzte Antwort fuer den Panel-Modus spiegeln.
        document.getElementById('panel-answer').textContent = text;
    }
    renderTranscript();
}

function renderTranscript() {
    const filter = (transcriptSearch.value || '').trim().toLowerCase();
    transcript.textContent = '';
    for (const entry of transcriptLog) {
        if (filter && !entry.text.toLowerCase().includes(filter)) continue;
        const row = document.createElement('div');
        row.className = 'msg ' + entry.role;
        const t = document.createElement('span');
        t.className = 'msg-time';
        t.textContent = entry.time;
        const txt = document.createElement('span');
        txt.className = 'msg-text';
        txt.textContent = (entry.role === 'user' ? 'Du: ' : 'Jarvis: ') + entry.text;
        const copy = document.createElement('button');
        copy.className = 'msg-copy';
        copy.title = 'Kopieren';
        copy.textContent = '⧉';
        copy.addEventListener('click', () => copyToClipboard(entry.text, copy));
        row.appendChild(t);
        row.appendChild(txt);
        row.appendChild(copy);
        transcript.appendChild(row);
    }
    if (!filter) transcript.scrollTop = transcript.scrollHeight;
}

function copyToClipboard(text, feedbackEl) {
    const done = () => {
        if (feedbackEl) {
            feedbackEl.classList.add('copied');
            setTimeout(() => feedbackEl.classList.remove('copied'), 1000);
        }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
        fallbackCopy(text, done);
    }
}

function fallbackCopy(text, done) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) {}
    ta.remove();
}

transcriptSearch.addEventListener('input', renderTranscript);
document.getElementById('btn-copy-all').addEventListener('click', (e) => {
    const filter = (transcriptSearch.value || '').trim().toLowerCase();
    const lines = transcriptLog
        .filter(entry => !filter || entry.text.toLowerCase().includes(filter))
        .map(entry => `${entry.time} ${entry.role === 'user' ? 'Du' : 'Jarvis'}: ${entry.text}`);
    copyToClipboard(lines.join('\n'), e.target);
});

// ── Aktionshistorie (Fokus-Modus) ───────────────────────────────────────────
const MAX_ACTIONS = 15;

function addActionEntry(data) {
    const list = document.getElementById('action-list');
    if (data.phase === 'start') {
        const li = document.createElement('li');
        li.className = 'ae run';
        li.dataset.action = data.action;
        const dot = document.createElement('span');
        dot.className = 'ae-dot';
        const time = document.createElement('span');
        time.className = 'ae-time';
        time.textContent = new Date((data.ts ? data.ts : Date.now() / 1000) * 1000)
            .toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
        const label = document.createElement('span');
        label.className = 'ae-label';
        label.textContent = data.label || data.action;
        const detail = document.createElement('span');
        detail.className = 'ae-detail';
        detail.textContent = data.detail || '';
        detail.title = data.detail || '';
        li.appendChild(dot);
        li.appendChild(time);
        li.appendChild(label);
        li.appendChild(detail);
        list.appendChild(li);
        while (list.children.length > MAX_ACTIONS) list.removeChild(list.firstChild);
        list.scrollTop = list.scrollHeight;
    } else {
        // Juengsten offenen Eintrag gleichen Typs abschliessen.
        const open = list.querySelectorAll('li.run[data-action="' + data.action + '"]');
        const li = open[open.length - 1];
        if (!li) return;
        li.classList.remove('run');
        li.classList.add(data.phase === 'done' ? 'ok' : 'err');
        if (data.phase === 'error' && data.detail) {
            const d = li.querySelector('.ae-detail');
            if (d) { d.textContent = data.detail; d.title = data.detail; }
        }
    }
}

// Texteingabe als Fallback: Senden nur per Strg+Enter, einfaches Enter tut nichts.
// Mute gilt fuers Mikro, nicht fuers Tippen — daher kein isMuted-Check.
const textInput = document.getElementById('text-input');
document.getElementById('text-form').addEventListener('submit', (e) => e.preventDefault());
textInput.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        const text = textInput.value.trim();
        if (!text) return;
        if (sendUtterance(text)) textInput.value = '';
    }
});

// ── Start ────────────────────────────────────────────────────────────────────
if (micMode === 'off') isMuted = true;
updateMuteButton();
updateModeButton();
if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => { stream.getTracks().forEach(t => t.stop()); })
        .catch(() => {
            status.textContent = 'Mikrofon-Zugriff verweigert. Bitte Erlaubnis in der Adressleiste erteilen und Seite neu laden.';
            setOrbState('error');
            showErrorBanner({ component: 'mic', text: 'Kein Mikrofon-Zugriff.', hint: 'Mikrofon in der Adressleiste erlauben und Seite neu laden.' });
        });
}
connect();
