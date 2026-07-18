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
let currentAudio = null;   // laufendes Audio-Element — fuer den Stopp-Pfad
let currentAudioUrl = null;

// Mikrofonmodus: 'auto' (immer zuhoeren), 'ptt' (Leertaste halten), 'off' (Start stumm)
let micMode = localStorage.getItem('jarvis.micMode') || 'auto';

// Zentraler UI-Zustand fuers Status-Center
const uiState = { connected: false, micMuted: false, jarvisState: 'idle', lastError: '', warnings: '' };

// Zustandsworte gemaess docs/ux/STATE_MODEL.md — ein Vokabular fuer
// Statuszeile, Fussleiste und Screenreader (Klartext, nie Farbe allein).
const STATE_WORDS = {
    idle: 'Bereit', listening: 'Hört zu', thinking: 'Denkt nach',
    speaking: 'Spricht', muted: 'Mikrofon stumm', error: 'Störung — Details im Banner',
};

function setStatusWord() {
    status.textContent = STATE_WORDS[uiState.jarvisState] || 'Bereit';
}

function renderStatusCenter() {
    document.getElementById('sc-conn').className = 'sc-dot ' + (uiState.connected ? 'ok' : 'err');
    document.getElementById('sc-mic').className = 'sc-dot ' + (uiState.micMuted ? 'off' : 'ok');
    const connText = document.getElementById('sc-conn-text');
    const micText = document.getElementById('sc-mic-text');
    if (connText) connText.textContent = uiState.connected ? 'Server verbunden' : 'Getrennt';
    if (micText) micText.textContent = uiState.micMuted ? 'Mikrofon stumm' : 'Mikrofon bereit';
    // Zustandswort lebt allein in der Statuszeile (#status) — keine Fußleisten-Dopplung.
    const row = document.getElementById('status-row');
    if (row) {
        row.className = uiState.connected ? ('s-' + uiState.jarvisState) : 's-disconnected';
    }
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
    // Vier Meldungsfamilien (DESIGN §9): tts-Ausfall ist eine Warnung mit
    // Text-Fallback, Konfiguration ebenso; echte Stoerungen bleiben Fehler.
    const KIND_CLASS = { tts: ' eb-warning', config: ' eb-warning' };
    const isWarning = !!KIND_CLASS[component];
    banner.className = 'error-banner' + (KIND_CLASS[component] || '');
    // Warnungen hoeflich, echte Stoerungen assertiv ankuendigen (jeder Banner
    // ist seine eigene Live-Region — der Stack-Container traegt keine mehr).
    banner.setAttribute('role', isWarning ? 'status' : 'alert');
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
    close.type = 'button';
    close.title = 'Schließen';
    close.setAttribute('aria-label', 'Meldung schließen');
    close.textContent = '×';
    close.addEventListener('click', () => removeBanner(banner));

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
        setTimeout(() => removeBanner(banner), 10000);
    }
    reportError(text);
    if (component === 'llm' || component === 'ws') flashOrbError();
}
window.showErrorBanner = showErrorBanner;

// Banner-Exit: kurzer Opacity-Ausklang (WAAPI, unterbrechungsfrei), Exit
// schneller als Enter; ohne animate()-Support sofortiges Entfernen.
function removeBanner(banner) {
    if (!banner.isConnected) return;
    if (banner.animate) {
        const fade = banner.animate([{ opacity: 1 }, { opacity: 0 }],
            { duration: 120, easing: 'ease' });
        fade.onfinish = () => banner.remove();
    } else {
        banner.remove();
    }
}

function dismissErrorBanners(component) {
    document.querySelectorAll('#error-stack .error-banner').forEach(b => {
        if (b.dataset.component === component) removeBanner(b);
    });
}

// ── UI-Zustand: Seite × Fenstergroesse ───────────────────────────────────────
// Die Seite (jarvis/control) bestimmt den Inhalt, die Fenstergroesse
// (fullscreen/focus/panel) nur das native Fenster. In-memory State, kein
// localStorage — jeder Launcher-Start beginnt im Vollbild auf der Jarvis-Seite.
const UI_MODES = ['fullscreen', 'focus', 'panel'];
const APP_PAGES = ['jarvis', 'control'];
// Sub-Views des Kontrollzentrums: Übersicht, Einstellungen, Musik.
const CONTROL_VIEWS = ['overview', 'settings', 'music'];
let uiMode = 'fullscreen';
let appPage = 'jarvis';
let controlView = 'overview';
const modeSwitch = document.getElementById('window-mode-switch');
const pageNav = document.getElementById('page-nav');
const ccSubnav = document.getElementById('cc-subnav');

function isControlPage() {
    return appPage === 'control';
}

// Kontrollzentrum-Daten (Dashboard-State) nur laden, wenn das Kontrollzentrum
// auch sichtbar ist — die Jarvis-Seite braucht sie nicht.
function shouldLoadControlData() {
    return isControlPage();
}

// Root-Klasse aus Seite + Fenstergroesse (+ Sub-View im Kontrollzentrum).
// Das Kontrollzentrum nutzt das bestehende Dashboard-CSS (mode-focus) plus den
// Marker page-control und den aktiven Sub-View (cc-view-overview/-settings);
// mode-fullscreen bleibt reiner Marker fuer die native Fenstergroesse.
// Die Jarvis-Seite nutzt das zentrierte Basis-Layout, im Panel das kompakte
// mode-panel.
function rootClass() {
    if (isControlPage()) {
        const size = uiMode === 'fullscreen' ? 'mode-focus mode-fullscreen' : 'mode-focus';
        return size + ' page-control cc-view-' + controlView;
    }
    if (uiMode === 'panel') return 'page-jarvis mode-panel';
    return uiMode === 'fullscreen' ? 'page-jarvis mode-fullscreen' : 'page-jarvis';
}

function updateModeButton() {
    if (!modeSwitch) return;
    modeSwitch.querySelectorAll('[data-window-mode]').forEach((btn) => {
        const active = btn.dataset.windowMode === uiMode;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
}

function updatePageButton() {
    if (!pageNav) return;
    pageNav.querySelectorAll('[data-app-page]').forEach((btn) => {
        const active = btn.dataset.appPage === appPage;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
}

function updateControlViewButton() {
    if (!ccSubnav) return;
    ccSubnav.querySelectorAll('[data-cc-view]').forEach((btn) => {
        const active = btn.dataset.ccView === controlView;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
}

// Sub-View im Kontrollzentrum wechseln: Übersicht (Dashboard) oder
// Einstellungen (inline). Auch von settings.js genutzt (Abbrechen/Speichern
// kehren zur Übersicht zurueck).
function applyControlView(view) {
    if (!CONTROL_VIEWS.includes(view)) view = 'overview';
    controlView = view;
    document.documentElement.className = rootClass();
    updateControlViewButton();
    if (!shouldLoadControlData()) return;
    if (view === 'settings') {
        // Frische Werte vom Server ins Formular laden (settings.js).
        if (window.openSettings) window.openSettings();
    } else if (view === 'music') {
        // MP3-Liste + Auswahl frisch laden (music.js).
        if (window.loadMusic) window.loadMusic();
    } else {
        loadDashboardState();
    }
}
window.applyControlView = applyControlView;

function applyUiMode(mode, callNative = true) {
    if (!UI_MODES.includes(mode)) mode = 'fullscreen';
    uiMode = mode;
    // Das kleine Panel ist immer die kompakte Jarvis-Ansicht.
    if (mode === 'panel' && isControlPage()) appPage = 'jarvis';
    document.documentElement.className = rootClass();
    updateModeButton();
    updatePageButton();
    // Natives Fenster nachziehen — im Browser (ohne pywebview) nur CSS-Layout.
    if (callNative && window.pywebview && window.pywebview.api && window.pywebview.api.set_window_mode) {
        window.pywebview.api.set_window_mode(mode);
    }
    // Kontrollzentrum mit frischen Daten fuellen, sobald es sichtbar wird.
    if (shouldLoadControlData()) loadDashboardState();
}

function applyAppPage(page) {
    if (!APP_PAGES.includes(page)) page = 'jarvis';
    appPage = page;
    // Das Kontrollzentrum braucht Platz: aus dem kleinen Panel wird automatisch
    // auf die mittlere Fenstergroesse gewechselt.
    if (isControlPage() && uiMode === 'panel') {
        applyUiMode('focus');
        return;
    }
    document.documentElement.className = rootClass();
    updatePageButton();
    if (shouldLoadControlData()) loadDashboardState();
}

// Drei-Wege-Auswahl: jeder Button setzt direkt seinen Modus.
if (modeSwitch) {
    modeSwitch.querySelectorAll('[data-window-mode]').forEach((btn) => {
        btn.addEventListener('click', () => applyUiMode(btn.dataset.windowMode));
    });
}
// Fokus nach Bereichswechsel auf die (sr-only) Bereichsueberschrift —
// Screenreader landen im Inhalt statt in der Titelleiste (docs/ux A11y §2).
function focusPageHeading() {
    const id = isControlPage() ? 'control-heading' : 'jarvis-heading';
    const h = document.getElementById(id);
    if (h) h.focus();
}

// Enter-only-Ansichtswechsel (Phase 5): Zielbereich blendet kurz ein,
// Exit ist sofort — nicht blockierend, per animationend selbstauf raeumend.
function playViewEnter() {
    const el = document.getElementById(isControlPage() ? 'cc-shell' : 'main-col');
    if (!el) return;
    el.classList.remove('view-enter');
    void el.offsetWidth; // Re-Trigger bei schnellem Wechsel
    el.classList.add('view-enter');
    el.addEventListener('animationend', () => el.classList.remove('view-enter'), { once: true });
}

// Hauptnavigation: Jarvis-Seite / Kontrollzentrum.
if (pageNav) {
    pageNav.querySelectorAll('[data-app-page]').forEach((btn) => {
        btn.addEventListener('click', () => {
            applyAppPage(btn.dataset.appPage);
            focusPageHeading();
            playViewEnter();
        });
    });
}
// Kontrollzentrum-Sub-Nav: Übersicht / Einstellungen.
if (ccSubnav) {
    ccSubnav.querySelectorAll('[data-cc-view]').forEach((btn) => {
        btn.addEventListener('click', () => {
            applyControlView(btn.dataset.ccView);
            focusPageHeading();
            playViewEnter();
        });
    });
}
// Sobald die pywebview-Bruecke bereit ist: immer fullscreen — Modus wird nicht
// wiederhergestellt, jeder Launcher-Start beginnt im Vollbild (Jarvis-Seite).
window.addEventListener('pywebviewready', () => applyUiMode('fullscreen'));

// Gemeinsamer Sendepfad fuer Sprache und Texteingabe.
function sendUtterance(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        reportError('Jarvis-Server nicht erreichbar — Nachricht nicht gesendet.');
        return false;
    }
    addTranscript('user', text);
    setOrbState('thinking');
    JarvisWire.sayText(ws, text);
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

// Delight: der Orb-Glow blüht beim ersten Verbinden einmal auf („Instrument
// erwacht"). Reduced-Motion unterdrückt die Animation (statischer Glow bleibt);
// CSS-Spezifität lässt den Bloom kurz vor dem Zustands-Glow führen.
function awakenInstrument() {
    const c = document.getElementById('orb-container');
    if (!c) return;
    c.classList.add('awakening');
    let cleared = false;
    const clear = () => {
        if (cleared) return;
        cleared = true;
        c.classList.remove('awakening');
        c.removeEventListener('animationend', onEnd);
    };
    function onEnd(e) { if (e.animationName === 'orb-awaken') clear(); }
    c.addEventListener('animationend', onEnd);
    // Fallback: bei reduzierter Bewegung feuert animationend nie (Animation aus).
    setTimeout(clear, 600);
}

function connect() {
    // Session-Token wird vom Server in die Seite injiziert (window.JARVIS_TOKEN).
    const token = encodeURIComponent(window.JARVIS_TOKEN || '');
    const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = JarvisWire.createSocket(`${wsProtocol}//${location.host}/ws?token=${token}`);
    ws.onopen = () => {
        // Ausgehandelte Protokollversion fuer Diagnose/E2E sichtbar machen.
        window.__jarvisProtocol = ws.protocol || '';
        console.log('[jarvis] WebSocket connected', ws.protocol || '(legacy)');
        uiState.connected = true;
        uiState.lastError = '';
        reconnectAttempts = 0;
        dismissErrorBanners('ws');
        renderStatusCenter();
        setStatusWord();
        if (!hasGreeted) {
            // Begruessung nur einmal — nicht bei jedem Reconnect wiederholen.
            hasGreeted = true;
            setOrbState('thinking');
            awakenInstrument(); // Delight: einmaliger Erwachen-Glow
            JarvisWire.sayText(ws, 'Jarvis activate');
        } else {
            status.textContent = 'Wieder verbunden.';
            if (!isPlaying) resumeListening(0);
        }
    };
    ws.onmessage = (event) => {
        // Wire-Adapter: V1-Envelope -> UI-Event der Legacy-Form; kaputt/unbekannt -> null.
        const data = JarvisWire.decodeFrame(event.data);
        if (!data) return;
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
        } else if (data.type === 'stop') {
            // Server bestaetigt Stopp (auch wenn er von anderswo ausgeloest wurde).
            stopPlaybackLocal();
        } else if (data.type === 'action') {
            addActionEntry(data);
            // Abgeschlossene Aktionen (z.B. INBOX_WRITE) koennen "Heute" veraendern.
            if (data.phase !== 'start') scheduleDashboardRefresh();
        } else if (data.type === 'app_event') {
            showAppMessage(data);
            scheduleDashboardRefresh();
        } else if (data.type === 'launcher_changed') {
            // Profil-/Autostart-/Placement-Aenderung (z.B. per Sprache):
            // Profil-Leiste, Module und Map nachziehen (focus-only Guard im Refresh).
            scheduleDashboardRefresh();
        } else if (data.type === 'music_changed') {
            // Musikauswahl geaendert: Liste + "Nächste Musik"-Status nachziehen.
            if (window.loadMusic) window.loadMusic();
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
        setStatusWord();
        resumeListening(500);
        return;
    }
    isPlaying = true;
    setOrbState('speaking');
    setStatusWord();
    if (isListening) {
        recognition.stop();
        isListening = false;
    }

    const b64 = audioQueue.shift();
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    currentAudioUrl = url;
    audio.onended = () => { URL.revokeObjectURL(url); currentAudio = null; playNext(); };
    audio.onerror = () => { URL.revokeObjectURL(url); currentAudio = null; playNext(); };
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
                setStatusWord();
            }).catch(() => playNext());
        });
    });
}

// ── Stopp: Wiedergabe sofort beenden + laufende Server-Aktion abbrechen ─────
function stopPlaybackLocal() {
    // Nur wenn wirklich etwas lief "Gestoppt." anzeigen — sonst wirkt ein Stopp
    // im Leerlauf (oder der zweite Aufruf via stop-Frame) verwirrend.
    const wasActive = isPlaying || audioQueue.length > 0;
    audioQueue = [];
    if (currentAudio) {
        currentAudio.onended = null;
        currentAudio.onerror = null;
        currentAudio.pause();
        if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
        currentAudio = null;
        currentAudioUrl = null;
    }
    isPlaying = false;
    setOrbState('idle');
    if (wasActive) status.textContent = 'Gestoppt.';
    resumeListening(300);
}

function requestStop() {
    stopPlaybackLocal();
    // Server bricht eine laufende Aktion (z.B. Recherche) ab und leert die Queue.
    if (ws && ws.readyState === WebSocket.OPEN) {
        JarvisWire.stop(ws);
    }
}

// Reine Stopp-Aeusserung per Sprache — Details entscheidet der Server nochmal.
const STOP_RE = /^\s*(jarvis[,!\s]+)?(bitte\s+)?(stopp?|halt|abbruch|abbrechen|aufhören|ruhe|sei still|sei ruhig|hör auf)[\s.!]*$/i;

document.getElementById('stop-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    requestStop();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') requestStop();
});

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
            // Stopp geht immer — auch stummgeschaltet, und ohne LLM-Umweg.
            if (STOP_RE.test(text)) { requestStop(); return; }
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
    if (!isMuted) setStatusWord();
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
    setStatusWord();
    status.classList.toggle('active', effective !== 'idle' && effective !== 'muted');
    // Stop ist waehrend Sprache/laufender Aktion die visuell primaere Aktion.
    const stopBtn = document.getElementById('stop-btn');
    if (stopBtn) {
        const actionRunning = !!document.getElementById('status-action')?.textContent;
        stopBtn.classList.toggle('primary-now', effective === 'speaking' || actionRunning);
    }
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
    btn.setAttribute('aria-pressed', isMuted ? 'true' : 'false');
    btn.setAttribute('aria-label', isMuted ? 'Mikrofon wieder aktivieren' : 'Mikrofon stummschalten');
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
        setStatusWord();
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

function transcriptAtEnd() {
    return transcript.scrollTop + transcript.clientHeight >= transcript.scrollHeight - 12;
}

function addTranscript(role, text) {
    const time = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    const wasAtEnd = transcriptAtEnd();
    transcriptLog.push({ role, text, time });
    if (transcriptLog.length > MAX_TRANSCRIPT) transcriptLog.shift();
    if (role === 'jarvis') {
        // Letzte Antwort fuer den Panel-Modus spiegeln.
        document.getElementById('panel-answer').textContent = text;
    }
    renderTranscript();
    // Nur der NEUE Eintrag blendet ein (Suche/Re-Render animiert nichts).
    const newest = transcript.lastElementChild;
    if (newest) {
        newest.classList.add('msg-new');
        newest.addEventListener('animationend',
            () => newest.classList.remove('msg-new'), { once: true });
    }
    // Auto-Scroll nur, wenn der Leser am Ende stand — sonst leise Pill anbieten.
    const pill = document.getElementById('new-msg-pill');
    if (wasAtEnd) {
        transcript.scrollTop = transcript.scrollHeight;
        if (pill) pill.hidden = true;
    } else if (pill) {
        pill.hidden = false;
    }
}

function renderTranscript() {
    const filter = (transcriptSearch.value || '').trim().toLowerCase();
    transcript.textContent = '';
    let shown = 0;
    for (const entry of transcriptLog) {
        if (filter && !entry.text.toLowerCase().includes(filter)) continue;
        shown++;
        const row = document.createElement('div');
        row.className = 'msg ' + entry.role;
        const t = document.createElement('span');
        t.className = 'msg-time';
        t.textContent = entry.time;
        const body = document.createElement('span');
        body.className = 'msg-text';
        const speaker = document.createElement('span');
        speaker.className = 'msg-speaker';
        speaker.textContent = entry.role === 'user' ? 'Du' : 'Jarvis';
        const txt = document.createElement('span');
        txt.className = 'msg-words';
        txt.textContent = entry.text;
        body.appendChild(speaker);
        body.appendChild(txt);
        const copy = document.createElement('button');
        copy.className = 'msg-copy';
        copy.title = 'Antwort kopieren';
        copy.setAttribute('aria-label',
            (entry.role === 'user' ? 'Eigene Nachricht' : 'Antwort') + ' von ' + entry.time + ' kopieren');
        copy.textContent = '⧉';
        copy.addEventListener('click', () => copyToClipboard(entry.text, copy));
        row.appendChild(t);
        row.appendChild(body);
        row.appendChild(copy);
        transcript.appendChild(row);
    }
    const count = document.getElementById('search-count');
    if (count) {
        count.textContent = filter ? `${shown} von ${transcriptLog.length} Einträgen` : '';
    }
    if (filter) transcript.scrollTop = 0;
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

// Neue-Nachricht-Pill: erscheint nur, wenn der Leser hochgescrollt hat.
const newMsgPill = document.getElementById('new-msg-pill');
if (newMsgPill) {
    newMsgPill.addEventListener('click', () => {
        transcript.scrollTop = transcript.scrollHeight;
        newMsgPill.hidden = true;
    });
    transcript.addEventListener('scroll', () => {
        if (transcriptAtEnd()) newMsgPill.hidden = true;
    });
}
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
    // Laufende Aktion als Klartext in der Statuszeile (Aktions-Dedupe:
    // die volle Historie lebt im Kontrollzentrum, s. docs/ux). Stop wird
    // waehrend einer laufenden Aktion zur visuell primaeren Kontrolle.
    const actionEl = document.getElementById('status-action');
    const escEl = document.getElementById('status-esc');
    // Laufende Taetigkeit am Instrument: umlaufender Skalen-Glanz (Phase 5).
    const orbBox = document.getElementById('orb-container');
    if (orbBox) orbBox.classList.toggle('action-running', data.phase === 'start');
    if (actionEl) {
        if (data.phase === 'start') {
            actionEl.textContent = '· ' + (data.label || data.action || 'Aktion')
                + (data.detail ? ': ' + data.detail : '');
            if (escEl) escEl.hidden = false;
        } else {
            actionEl.textContent = '';
            if (escEl) escEl.hidden = true;
        }
        const stopBtn = document.getElementById('stop-btn');
        if (stopBtn) stopBtn.classList.toggle('primary-now',
            data.phase === 'start' || uiState.jarvisState === 'speaking');
    }
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

// ── Command Center (Kontrollzentrum-Seite) ──────────────────────────────────
// Dashboard-State per HTTP laden und rendern. App-Klicks laufen ueber
// POST /commands/app/open — dieselbe Allowlist wie die Sprach-Aktion APP_OPEN.

let ccLoading = false;
let ccRefreshTimer = null;
// Delight: nur der eben zugewiesene Chip animiert beim naechsten Map-Render.
let justPlacedAppId = null;

// Monitor-Map-State: lastApps = letzter Server-Stand (Quelle fuer Map + Module),
// mapMonitors null = noch nicht geladen, [] = Erkennung fehlgeschlagen (Fallback).
let lastApps = [];
let mapMonitors = null;
let mapNote = '';
let selectedAppId = null;
let mapStatusTimer = null;
let mapResizeObserver = null;

// Session-Profile: {active_profile, profiles:[{id,name,apps}]} vom Server.
let profilesState = null;
let profileDeleteMode = false;

function ccAuthHeaders() {
    return {
        'X-Jarvis-Token': window.JARVIS_TOKEN || '',
        'Content-Type': 'application/json',
    };
}

function ccSetEmpty(el, text) {
    el.textContent = '';
    const span = document.createElement('span');
    span.className = 'cc-empty';
    span.textContent = text;
    el.appendChild(span);
}

function ccRenderList(id, items, emptyText, max) {
    const list = document.getElementById(id);
    list.textContent = '';
    if (!items || items.length === 0) {
        const li = document.createElement('li');
        li.className = 'cc-empty';
        li.textContent = emptyText;
        list.appendChild(li);
        return;
    }
    for (const item of items.slice(0, max)) {
        const li = document.createElement('li');
        li.textContent = item;
        li.title = item;
        list.appendChild(li);
    }
}

function renderToday(data) {
    ccRenderList('cc-task-list', data.tasks, 'Keine offenen Aufgaben.', 8);
    const inbox = document.getElementById('cc-inbox-text');
    if (data.today_inbox) {
        inbox.textContent = data.today_inbox.length > 600
            ? data.today_inbox.slice(0, 600) + ' …'
            : data.today_inbox;
    } else {
        ccSetEmpty(inbox, 'Noch keine Einträge heute.');
    }
    const recent = (data.vault && data.vault.recent) || [];
    ccRenderList('cc-note-list', recent, 'Kein Vault verbunden.', 5);
}

function renderApps(apps) {
    lastApps = apps || [];
    const grid = document.getElementById('cc-app-grid');
    grid.textContent = '';
    if (lastApps.length === 0) {
        const span = document.createElement('span');
        span.className = 'cc-empty';
        span.textContent = 'Keine Apps konfiguriert — siehe Einstellungen.';
        grid.appendChild(span);
    } else {
        for (const app of lastApps) {
            grid.appendChild(buildAppModule(app));
        }
    }
    renderMap();
    applySelectionClasses();
    resetMapStatus();
}

// Platzierungsoptionen fuer den Sessionstart — Werte muessen den Allowlists
// in config_loader/app_launcher entsprechen, Labels sind reine Anzeige.
const APP_MONITOR_OPTIONS = [
    ['primary', 'Primär'], ['left', 'Links'], ['right', 'Rechts'],
    ['leftmost', 'Ganz links'], ['rightmost', 'Ganz rechts'],
];
const APP_ZONE_OPTIONS = [
    ['fullscreen', 'Vollbild'], ['left_half', 'Linke Hälfte'], ['right_half', 'Rechte Hälfte'],
    ['top_half', 'Obere Hälfte'], ['bottom_half', 'Untere Hälfte'],
    ['top_left', 'Oben links'], ['top_right', 'Oben rechts'],
    ['bottom_left', 'Unten links'], ['bottom_right', 'Unten rechts'],
    ['center', 'Zentriert'],
];

function optionLabel(options, value) {
    for (const [v, l] of options) {
        if (v === value) return l;
    }
    return value;
}

// Ein App-Modul: Name + Typ-Tag, Öffnen-Button, Autostart-Toggle und das
// Placement-Label. Klick auf den Modul-Koerper selektiert die App fuer
// Click-to-Assign auf der Monitor-Map (Öffnen/Toggle sind ausgenommen).
function buildAppModule(app) {
    const module = document.createElement('div');
    module.className = 'app-module' + (app.autostart ? '' : ' off');
    module.dataset.app = app.id;
    module.setAttribute('role', 'button');
    module.tabIndex = 0;
    module.addEventListener('click', (e) => {
        if (e.target.closest('.app-btn, .app-toggle, .app-position')) return;
        selectApp(app.id);
    });
    module.addEventListener('keydown', (e) => {
        if ((e.key === 'Enter' || e.key === ' ') && e.target === module) {
            e.preventDefault();
            selectApp(app.id);
        }
    });
    // Drag-and-Drop als Progressive Enhancement — Click-to-Assign bleibt der Hauptweg.
    module.draggable = true;
    module.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', app.id);
        e.dataTransfer.effectAllowed = 'move';
        selectedAppId = app.id;
        applySelectionClasses();
        resetMapStatus();
    });

    const head = document.createElement('div');
    head.className = 'app-module-head';
    const name = document.createElement('span');
    name.className = 'app-module-name';
    name.textContent = app.name;
    name.title = app.name;
    const type = document.createElement('span');
    type.className = 'app-module-type';
    type.textContent = app.type === 'url' ? 'URL' : 'App';
    type.title = app.type === 'url' ? 'Link/Protokoll' : 'Programm';
    head.appendChild(name);
    head.appendChild(type);

    const actions = document.createElement('div');
    actions.className = 'app-module-actions';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'app-btn';
    btn.textContent = 'Öffnen';
    btn.title = app.name + ' öffnen';
    btn.addEventListener('click', () => openApp(app.id, btn));

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'app-toggle' + (app.autostart ? ' on' : '');
    toggle.setAttribute('role', 'switch');
    toggle.setAttribute('aria-checked', app.autostart ? 'true' : 'false');
    toggle.title = app.autostart
        ? 'Startet beim Sessionstart — klicken zum Deaktivieren'
        : 'Startet nicht automatisch — klicken zum Aktivieren';
    const track = document.createElement('span');
    track.className = 'app-toggle-track';
    const knob = document.createElement('span');
    knob.className = 'app-toggle-knob';
    track.appendChild(knob);
    const label = document.createElement('span');
    label.className = 'app-toggle-label';
    label.textContent = 'Autostart';
    toggle.appendChild(track);
    toggle.appendChild(label);
    toggle.addEventListener('click', () => toggleAutostart(app.id, !app.autostart, toggle, app.name));

    actions.appendChild(btn);
    actions.appendChild(toggle);
    module.appendChild(head);
    module.appendChild(actions);

    const p = app.placement || { monitor: 'primary', zone: 'fullscreen' };
    const place = document.createElement('div');
    place.className = 'app-module-place';
    place.textContent = optionLabel(APP_MONITOR_OPTIONS, p.monitor)
        + ' · ' + optionLabel(APP_ZONE_OPTIONS, p.zone);
    place.title = 'Platzierung beim Sessionstart — per Karte oder den Auswahlfeldern unten';
    module.appendChild(place);

    // Nicht-visuelle Zuweisung (Weg B, docs/ux): Selects + Speichern —
    // gleichwertig zur Karte, sichtbar bei Auswahl/Fokus (progressive disclosure).
    const pos = document.createElement('div');
    pos.className = 'app-position';
    const row = document.createElement('div');
    row.className = 'ap-row';
    const mkSelect = (labelText, options, current, idSuffix) => {
        const wrap = document.createElement('span');
        const lbl = document.createElement('label');
        const sel = document.createElement('select');
        sel.id = 'ap-' + idSuffix + '-' + app.id;
        lbl.htmlFor = sel.id;
        lbl.textContent = labelText;
        for (const [value, text] of options) {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = text;
            if (value === current) opt.selected = true;
            sel.appendChild(opt);
        }
        wrap.appendChild(lbl);
        wrap.appendChild(sel);
        row.appendChild(wrap);
        return sel;
    };
    const selMon = mkSelect('Monitor', APP_MONITOR_OPTIONS, p.monitor, 'mon');
    const selZone = mkSelect('Zone', APP_ZONE_OPTIONS, p.zone, 'zone');
    const save = document.createElement('button');
    save.type = 'button';
    save.className = 'ap-save';
    save.textContent = 'Position speichern';
    save.setAttribute('aria-label', 'Position für ' + app.name + ' speichern');
    save.addEventListener('click', async () => {
        save.disabled = true;
        try {
            await assignPlacement(app.id, selMon.value, selZone.value, null);
        } finally {
            save.disabled = false;
        }
    });
    row.appendChild(save);
    pos.appendChild(row);
    module.appendChild(pos);
    return module;
}

// ── Monitor-Map (Click-to-Assign) ───────────────────────────────────────────
// Zonen-Geometrie spiegelt Get-ZoneRect in launch-session.ps1 (fraktional).
const ZONE_RECTS = {
    fullscreen:   { x: 0,    y: 0,     w: 1,   h: 1 },
    left_half:    { x: 0,    y: 0,     w: 0.5, h: 1 },
    right_half:   { x: 0.5,  y: 0,     w: 0.5, h: 1 },
    top_half:     { x: 0,    y: 0,     w: 1,   h: 0.5 },
    bottom_half:  { x: 0,    y: 0.5,   w: 1,   h: 0.5 },
    top_left:     { x: 0,    y: 0,     w: 0.5, h: 0.5 },
    top_right:    { x: 0.5,  y: 0,     w: 0.5, h: 0.5 },
    bottom_left:  { x: 0,    y: 0.5,   w: 0.5, h: 0.5 },
    bottom_right: { x: 0.5,  y: 0.5,   w: 0.5, h: 0.5 },
    center:       { x: 0.15, y: 0.125, w: 0.7, h: 0.75 },
};
// 3×3-Raster: Ecken = Viertel, Kantenmitten = Haelften, Mitte = Zentriert.
// Vollbild haengt als eigener Micro-Chip in der Monitor-Beschriftung.
const ZONE_CELLS = [
    ['top_left', 'top_half', 'top_right'],
    ['left_half', 'center', 'right_half'],
    ['bottom_left', 'bottom_half', 'bottom_right'],
];

// Fallback, wenn die Erkennung nichts liefert: zwei virtuelle Monitore —
// derselbe Adressraum (left/right), nur ohne echte Aufloesungsangabe.
function effectiveMonitors() {
    if (mapMonitors && mapMonitors.length > 0) return mapMonitors;
    return [
        { id: 'left', label: 'Linker Monitor', x: 0, y: 0, width: 1920, height: 1080, primary: true, virtual: true },
        { id: 'right', label: 'Rechter Monitor', x: 1920, y: 0, width: 1920, height: 1080, primary: false, virtual: true },
    ];
}

// Spiegel der PS1-Aufloesung: left==leftmost, right==rightmost, sonst primary.
function resolveMonitorIndex(monitors, key) {
    if (key === 'left' || key === 'leftmost') return 0;
    if (key === 'right' || key === 'rightmost') return monitors.length - 1;
    const p = monitors.findIndex((m) => m.primary);
    return p >= 0 ? p : 0;
}

async function loadMonitors() {
    if (mapMonitors !== null) return;
    try {
        const resp = await fetch('/launcher/monitors', { headers: ccAuthHeaders() });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        mapMonitors = (data.ok && Array.isArray(data.monitors)) ? data.monitors : [];
    } catch (e) {
        mapMonitors = [];
    }
    mapNote = mapMonitors.length === 0
        ? 'Monitor-Erkennung nicht verfügbar — verwende Standardansicht.' : '';
    renderMap();
    applySelectionClasses();
    resetMapStatus();
}

function setMapStatus(text, isError, transientMs) {
    const el = document.getElementById('cc-map-status');
    if (!el) return;
    clearTimeout(mapStatusTimer);
    el.textContent = text;
    el.classList.toggle('err', !!isError);
    if (transientMs) mapStatusTimer = setTimeout(resetMapStatus, transientMs);
}

function resetMapStatus() {
    const el = document.getElementById('cc-map-status');
    if (!el) return;
    clearTimeout(mapStatusTimer);
    el.classList.remove('err');
    if (profileDeleteMode) {
        el.textContent = 'Zu löschendes Profil anklicken · Esc bricht ab';
    } else if (selectedAppId) {
        const app = lastApps.find((a) => a.id === selectedAppId);
        el.textContent = '„' + (app ? app.name : selectedAppId) + '" zuweisen — Zone anklicken · Esc bricht ab';
    } else if (lastApps.length === 0) {
        el.textContent = 'Keine Apps konfiguriert — siehe Einstellungen.';
    } else if (mapNote) {
        el.textContent = mapNote;
    } else {
        const active = profilesState
            && profilesState.profiles.find((p) => p.id === profilesState.active_profile);
        el.textContent = (active ? 'Profil „' + active.name + '" — ' : '')
            + 'App anklicken, dann Zone wählen.';
    }
}

// Canvas-Groesse in px (Aspekt der Monitor-Bounding-Box, in die Stage eingepasst);
// die Monitore selbst sitzen prozentual im Canvas.
function layoutMapCanvas(canvas, stage) {
    const ratio = parseFloat(canvas.dataset.ratio) || 1;
    const pad = 18;
    const availW = Math.max(stage.clientWidth - pad * 2, 0);
    const availH = Math.max(stage.clientHeight - pad * 2, 0);
    let w = availW;
    let h = w / ratio;
    if (h > availH) { h = availH; w = h * ratio; }
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
}

function ensureMapObserver(stage) {
    if (mapResizeObserver || typeof ResizeObserver === 'undefined') return;
    mapResizeObserver = new ResizeObserver(() => {
        const canvas = stage.querySelector('.map-canvas');
        if (canvas) layoutMapCanvas(canvas, stage);
    });
    mapResizeObserver.observe(stage);
}

function showGhost(ghost, zone) {
    const r = ZONE_RECTS[zone];
    if (!r) return;
    ghost.style.left = (r.x * 100) + '%';
    ghost.style.top = (r.y * 100) + '%';
    ghost.style.width = (r.w * 100) + '%';
    ghost.style.height = (r.h * 100) + '%';
    ghost.classList.add('on');
}

function hideGhost(ghost) {
    ghost.classList.remove('on');
}

// Zonen-Ziel verdrahten: Hover/Fokus zeigt den Ghost mit der ECHTEN
// Zonen-Geometrie, Klick/Enter weist zu, Drop nimmt gezogene App-Module an.
function wireZoneTarget(el, monitorId, zone, ghost) {
    const show = () => showGhost(ghost, zone);
    const hide = () => hideGhost(ghost);
    el.addEventListener('mouseenter', show);
    el.addEventListener('mouseleave', hide);
    el.addEventListener('focus', show);
    el.addEventListener('blur', hide);
    el.addEventListener('click', (e) => {
        e.stopPropagation();
        zoneClicked(monitorId, zone, el);
    });
    el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            zoneClicked(monitorId, zone, el);
        }
    });
    el.addEventListener('dragover', (e) => { e.preventDefault(); show(); });
    el.addEventListener('dragleave', hide);
    el.addEventListener('drop', (e) => {
        e.preventDefault();
        hide();
        const appId = e.dataTransfer.getData('text/plain');
        if (appId) assignPlacement(appId, monitorId, zone, el);
    });
}

function renderMap() {
    const stage = document.getElementById('cc-map-stage');
    if (!stage) return;
    ensureMapObserver(stage);
    stage.textContent = '';
    if (mapMonitors === null) {
        const span = document.createElement('span');
        span.className = 'cc-empty';
        span.textContent = 'Lade Monitore…';
        stage.appendChild(span);
        return;
    }

    const monitors = effectiveMonitors();
    const minX = Math.min(...monitors.map((m) => m.x));
    const minY = Math.min(...monitors.map((m) => m.y));
    const bboxW = Math.max(...monitors.map((m) => m.x + m.width)) - minX;
    const bboxH = Math.max(...monitors.map((m) => m.y + m.height)) - minY;
    if (bboxW <= 0 || bboxH <= 0) return;

    const canvas = document.createElement('div');
    canvas.className = 'map-canvas';
    canvas.dataset.ratio = String(bboxW / bboxH);

    monitors.forEach((mon, idx) => {
        const monEl = document.createElement('div');
        monEl.className = 'map-monitor' + (mon.id ? '' : ' unassignable');
        if (mon.id) monEl.dataset.monitor = mon.id;
        const gap = 3; // px Luft zwischen angrenzenden Monitoren
        monEl.style.left = 'calc(' + (((mon.x - minX) / bboxW) * 100) + '% + ' + gap + 'px)';
        monEl.style.top = 'calc(' + (((mon.y - minY) / bboxH) * 100) + '% + ' + gap + 'px)';
        monEl.style.width = 'calc(' + ((mon.width / bboxW) * 100) + '% - ' + (gap * 2) + 'px)';
        monEl.style.height = 'calc(' + ((mon.height / bboxH) * 100) + '% - ' + (gap * 2) + 'px)';

        const body = document.createElement('div');
        body.className = 'map-monitor-body';
        const ghost = document.createElement('div');
        ghost.className = 'map-ghost';

        const labelBar = document.createElement('div');
        labelBar.className = 'map-monitor-label';
        const lbl = document.createElement('span');
        lbl.textContent = (mon.label || 'Monitor')
            + (mon.virtual ? '' : ' · ' + mon.width + '×' + mon.height);
        labelBar.appendChild(lbl);
        if (mon.id) {
            const full = document.createElement('button');
            full.type = 'button';
            full.className = 'map-zone-full';
            full.dataset.zone = 'fullscreen';
            full.textContent = 'Vollbild';
            full.title = 'Vollbild auf ' + (mon.label || 'Monitor');
            wireZoneTarget(full, mon.id, 'fullscreen', ghost);
            labelBar.appendChild(full);
        }

        const grid = document.createElement('div');
        grid.className = 'map-grid';
        for (const row of ZONE_CELLS) {
            for (const zone of row) {
                const cell = document.createElement('div');
                cell.className = 'map-zone';
                cell.dataset.zone = zone;
                if (mon.id) {
                    cell.setAttribute('role', 'button');
                    cell.tabIndex = 0;
                    cell.setAttribute('aria-label',
                        (mon.label || 'Monitor') + ': ' + optionLabel(APP_ZONE_OPTIONS, zone));
                    cell.title = optionLabel(APP_ZONE_OPTIONS, zone);
                    wireZoneTarget(cell, mon.id, zone, ghost);
                }
                grid.appendChild(cell);
            }
        }

        // Chips: aktivierte Apps auf ihrer Zone (gestapelt, >3 wird gekappt).
        const chips = document.createElement('div');
        chips.className = 'map-chips';
        const groups = {};
        for (const app of lastApps) {
            if (!app.autostart) continue;
            const p = app.placement || { monitor: 'primary', zone: 'fullscreen' };
            if (resolveMonitorIndex(monitors, p.monitor) !== idx) continue;
            (groups[p.zone] = groups[p.zone] || []).push(app);
        }
        for (const [zone, apps] of Object.entries(groups)) {
            const rect = ZONE_RECTS[zone] || ZONE_RECTS.fullscreen;
            const group = document.createElement('div');
            group.className = 'map-chip-group';
            group.style.left = (rect.x * 100) + '%';
            group.style.top = (rect.y * 100) + '%';
            group.style.width = (rect.w * 100) + '%';
            group.style.height = (rect.h * 100) + '%';
            for (const app of apps.slice(0, 3)) {
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'map-chip';
                chip.dataset.app = app.id;
                chip.textContent = app.name;
                chip.title = app.name + ' — anklicken zum Zuweisen';
                chip.draggable = true;
                if (app.id === justPlacedAppId) {
                    chip.classList.add('chip-landed');
                    chip.addEventListener('animationend', function h() {
                        chip.classList.remove('chip-landed');
                        chip.removeEventListener('animationend', h);
                    });
                }
                chip.addEventListener('click', (e) => {
                    e.stopPropagation();
                    selectApp(app.id);
                });
                chip.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('text/plain', app.id);
                    e.dataTransfer.effectAllowed = 'move';
                    selectedAppId = app.id;
                    applySelectionClasses();
                    resetMapStatus();
                });
                group.appendChild(chip);
            }
            if (apps.length > 3) {
                const more = document.createElement('span');
                more.className = 'map-chip-more';
                more.textContent = '+' + (apps.length - 3);
                more.title = apps.slice(3).map((a) => a.name).join(', ');
                group.appendChild(more);
            }
            chips.appendChild(group);
        }

        body.appendChild(ghost);
        body.appendChild(grid);
        body.appendChild(chips);
        monEl.appendChild(labelBar);
        monEl.appendChild(body);
        canvas.appendChild(monEl);
    });

    stage.appendChild(canvas);
    layoutMapCanvas(canvas, stage);
}

// ── Click-to-Assign-Statemachine ────────────────────────────────────────────
function selectApp(appId) {
    selectedAppId = selectedAppId === appId ? null : appId;
    applySelectionClasses();
    resetMapStatus();
}

function clearSelection() {
    if (!selectedAppId) return;
    selectedAppId = null;
    applySelectionClasses();
    resetMapStatus();
}

function applySelectionClasses() {
    document.querySelectorAll('.app-module.selected, .map-chip.selected')
        .forEach((el) => el.classList.remove('selected'));
    const stage = document.getElementById('cc-map-stage');
    if (stage) stage.classList.toggle('assigning', !!selectedAppId);
    if (!selectedAppId) return;
    const sel = '[data-app="' + CSS.escape(selectedAppId) + '"]';
    document.querySelectorAll('.app-module' + sel + ', .map-chip' + sel)
        .forEach((el) => el.classList.add('selected'));
}

function zoneClicked(monitorId, zone, zoneEl) {
    if (!selectedAppId) {
        setMapStatus('Erst App anklicken — dann Zone wählen.', false, 2000);
        return;
    }
    assignPlacement(selectedAppId, monitorId, zone, zoneEl);
}

// Platzierung speichern (Click-to-Assign + Drop). Pessimistisch: der neue
// Zustand kommt aus der Server-Antwort; bei Fehler bleibt die Selektion
// bestehen, damit der Nutzer direkt eine andere Zone versuchen kann.
async function assignPlacement(appId, monitorId, zone, zoneEl) {
    const app = lastApps.find((a) => a.id === appId);
    const name = app ? app.name : appId;
    if (zoneEl) zoneEl.classList.add('saving');
    setMapStatus('Speichere…', false);
    try {
        const resp = await fetch('/launcher/apps/' + encodeURIComponent(appId) + '/placement', {
            method: 'POST',
            headers: ccAuthHeaders(),
            body: JSON.stringify({ monitor: monitorId, zone: zone }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
            setMapStatus((data.errors || ['Platzierung konnte nicht gespeichert werden.']).join(' '), true);
            return;
        }
        selectedAppId = null;
        justPlacedAppId = appId;      // Chip-Landung nur fuer diese Zuweisung
        renderApps(data.apps);        // rendert Module + Map neu (liest das Flag)
        justPlacedAppId = null;
        pulseZone(monitorId, zone);
        setMapStatus(name + ': Platzierung gespeichert.', false, 2500);
    } catch (e) {
        setMapStatus('Platzierung konnte nicht gespeichert werden — läuft der Server?', true);
    } finally {
        if (zoneEl) zoneEl.classList.remove('saving');
    }
}

// Kurzer Lichtimpuls auf der Ziel-Zone nach erfolgreichem Speichern.
function pulseZone(monitorId, zone) {
    const el = document.querySelector(
        '.map-monitor[data-monitor="' + CSS.escape(monitorId) + '"] [data-zone="' + CSS.escape(zone) + '"]'
    );
    if (!el) return;
    el.classList.add('pulse');
    setTimeout(() => el.classList.remove('pulse'), 700);
}

// ── Session-Profile: Tabs + Aktionen (Neu/Duplizieren/Umbenennen/Löschen) ──
function currentActiveProfile() {
    if (!profilesState) return null;
    return profilesState.profiles.find((p) => p.id === profilesState.active_profile) || null;
}

async function loadProfiles() {
    try {
        const resp = await fetch('/launcher/profiles', { headers: ccAuthHeaders() });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (data.ok) {
            profilesState = { active_profile: data.active_profile, profiles: data.profiles };
            renderProfiles();
            resetMapStatus();
        }
    } catch (e) {
        // Kein Banner-Spam: Status-Center meldet Verbindungsprobleme bereits.
    }
}

// Gemeinsamer Pfad aller Profil-Aktionen: Antwort traegt den kompletten
// frischen Zustand (Profile + effective Apps des aktiven Profils).
async function profileRequest(url, options, successMsg) {
    try {
        const resp = await fetch(url, Object.assign({ headers: ccAuthHeaders() }, options));
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
            setMapStatus((data.errors || ['Profil-Aktion fehlgeschlagen.']).join(' '), true);
            return null;
        }
        profilesState = { active_profile: data.active_profile, profiles: data.profiles };
        profileDeleteMode = false;
        clearSelection(); // Auswahl passt nach Profilwechsel evtl. nicht mehr
        renderProfiles();
        renderApps(data.apps); // aktualisiert Module, Map und Statuszeile
        if (successMsg) setMapStatus(successMsg, false, 2500);
        return data;
    } catch (e) {
        setMapStatus('Profil-Aktion fehlgeschlagen — läuft der Server?', true);
        return null;
    }
}

function activateProfile(profileId, name) {
    profileRequest('/launcher/profiles/' + encodeURIComponent(profileId) + '/activate',
        { method: 'POST' }, 'Profil „' + name + '" aktiviert.');
}

function deleteProfile(profileId, name) {
    profileRequest('/launcher/profiles/' + encodeURIComponent(profileId),
        { method: 'DELETE' }, 'Profil „' + name + '" gelöscht.');
}

function submitProfileInput(mode, value) {
    const name = (value || '').trim();
    if (!name) return;
    const active = currentActiveProfile();
    if (mode === 'new') {
        profileRequest('/launcher/profiles',
            { method: 'POST', body: JSON.stringify({ name: name }) },
            'Profil „' + name + '" angelegt.');
    } else if (mode === 'duplicate' && active) {
        profileRequest('/launcher/profiles/' + encodeURIComponent(active.id) + '/duplicate',
            { method: 'POST', body: JSON.stringify({ name: name }) },
            'Profil „' + name + '" angelegt.');
    } else if (mode === 'rename' && active) {
        profileRequest('/launcher/profiles/' + encodeURIComponent(active.id) + '/rename',
            { method: 'POST', body: JSON.stringify({ name: name }) },
            'Profil umbenannt.');
    }
}

function profileActionButton(label, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'profile-action';
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
}

// Inline-Input statt Modal: Name eingeben, Enter bestaetigt, Esc bricht ab.
function openProfileInput(mode) {
    profileDeleteMode = false;
    const actions = document.getElementById('cc-profile-actions');
    if (!actions) return;
    actions.textContent = '';
    const active = currentActiveProfile();
    const input = document.createElement('input');
    input.id = 'cc-profile-input';
    input.type = 'text';
    input.setAttribute('aria-label', 'Profilname');
    input.placeholder = mode === 'duplicate' && active
        ? 'Name der Kopie von „' + active.name + '"' : 'Profilname';
    if (mode === 'rename' && active) input.value = active.name;
    input.addEventListener('keydown', (e) => {
        // Nicht an globale Handler durchreichen (Esc-Stopp, Leertaste-PTT).
        e.stopPropagation();
        if (e.key === 'Enter') {
            e.preventDefault();
            submitProfileInput(mode, input.value);
        } else if (e.key === 'Escape') {
            renderProfiles();
        }
    });
    actions.appendChild(input);
    actions.appendChild(profileActionButton('OK', () => submitProfileInput(mode, input.value)));
    actions.appendChild(profileActionButton('Abbrechen', () => renderProfiles()));
    input.focus();
}

function cancelProfileDeleteMode() {
    if (!profileDeleteMode) return;
    profileDeleteMode = false;
    renderProfiles();
    resetMapStatus();
}

function renderProfiles() {
    const tabs = document.getElementById('cc-profile-tabs');
    const actions = document.getElementById('cc-profile-actions');
    if (!tabs || !actions) return;
    tabs.textContent = '';
    actions.textContent = '';
    if (!profilesState) return;

    for (const profile of profilesState.profiles) {
        const tab = document.createElement('button');
        tab.type = 'button';
        tab.setAttribute('role', 'tab');
        const isActive = profile.id === profilesState.active_profile;
        tab.className = 'profile-tab' + (isActive ? ' active' : '')
            + (profileDeleteMode ? ' deletable' : '');
        tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        tab.textContent = profile.name;
        tab.title = profileDeleteMode
            ? 'Profil „' + profile.name + '" löschen'
            : 'Profil „' + profile.name + '" aktivieren';
        tab.addEventListener('click', () => {
            if (profileDeleteMode) {
                deleteProfile(profile.id, profile.name);
            } else if (!isActive) {
                activateProfile(profile.id, profile.name);
            }
        });
        tabs.appendChild(tab);
    }

    actions.appendChild(profileActionButton('Neu', () => openProfileInput('new')));
    actions.appendChild(profileActionButton('Duplizieren', () => openProfileInput('duplicate')));
    actions.appendChild(profileActionButton('Umbenennen', () => openProfileInput('rename')));
    const del = profileActionButton('Löschen', () => {
        if (profileDeleteMode) {
            cancelProfileDeleteMode();
        } else if (profilesState.profiles.length <= 1) {
            setMapStatus('Das letzte Profil kann nicht gelöscht werden.', true);
        } else {
            profileDeleteMode = true;
            renderProfiles();
            resetMapStatus();
        }
    });
    if (profileDeleteMode) del.classList.add('confirm');
    actions.appendChild(del);
}

// Abbruch-Wege: Esc (Capture — darf nicht zusaetzlich die Stopp-Logik ausloesen)
// und Klick auf den Stage-Hintergrund.
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (selectedAppId || profileDeleteMode)) {
        e.preventDefault();
        e.stopImmediatePropagation();
        clearSelection();
        cancelProfileDeleteMode();
    }
}, true);
(() => {
    const stage = document.getElementById('cc-map-stage');
    if (!stage) return;
    stage.addEventListener('click', (e) => {
        if (e.target === stage || e.target.classList.contains('map-canvas')) clearSelection();
    });
})();

// Autostart pessimistisch schalten: Visuals erst nach Server-OK umlegen —
// die Antwort liefert die frische App-Liste, daraus wird neu gerendert.
async function toggleAutostart(appId, nextValue, toggle, appName) {
    toggle.disabled = true;
    toggle.classList.add('busy');
    try {
        const resp = await fetch('/launcher/apps/' + encodeURIComponent(appId) + '/toggle', {
            method: 'POST',
            headers: ccAuthHeaders(),
            body: JSON.stringify({ autostart: nextValue }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
            showAppMessage({
                ok: false,
                message: (data.errors || ['Autostart konnte nicht geändert werden.']).join(' '),
            });
            return;
        }
        renderApps(data.apps);
        showAppMessage({
            ok: true,
            message: appName + ': Autostart ' + (nextValue ? 'aktiviert.' : 'deaktiviert.'),
        });
    } catch (e) {
        showAppMessage({ ok: false, message: 'Autostart konnte nicht geändert werden — läuft der Server?' });
    } finally {
        // Harmlos, falls das Element durch den Re-Render bereits ersetzt wurde.
        toggle.disabled = false;
        toggle.classList.remove('busy');
    }
}

function renderSystem(data) {
    const list = document.getElementById('cc-sys-list');
    list.textContent = '';
    const services = (data.health && data.health.services) || {};
    const labels = { llm: 'KI', tts: 'Sprachausgabe', browser: 'Browser', vault: 'Vault' };
    for (const key of ['llm', 'tts', 'browser', 'vault']) {
        const svc = services[key];
        if (!svc) continue;
        const li = document.createElement('li');
        const dot = document.createElement('span');
        dot.className = 'cc-dot ' + (svc.ok ? 'ok' : 'err');
        li.appendChild(dot);
        li.appendChild(document.createTextNode(labels[key]));
        if (!svc.ok && svc.detail) li.title = svc.detail;
        list.appendChild(li);
    }
    const li = document.createElement('li');
    const dot = document.createElement('span');
    dot.className = 'cc-dot' + (data.data_loaded ? ' ok' : '');
    li.appendChild(dot);
    let refreshText = 'Daten laden…';
    if (data.data_loaded && data.last_refresh) {
        refreshText = 'Stand ' + new Date(data.last_refresh * 1000)
            .toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    }
    li.appendChild(document.createTextNode(refreshText));
    list.appendChild(li);
}

async function loadDashboardState() {
    if (ccLoading) return;
    ccLoading = true;
    loadMonitors(); // einmalig, asynchron — rendert die Map nach, sobald geladen
    loadProfiles(); // haelt die Profil-Leiste bei jedem Refresh synchron
    try {
        const resp = await fetch('/dashboard/state', { headers: ccAuthHeaders() });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        renderApps(data.apps);
        renderToday(data);
        renderSystem(data);
    } catch (e) {
        // Kein Banner-Spam: Status-Center meldet Verbindungsprobleme bereits.
        ccSetEmpty(document.getElementById('cc-inbox-text'), 'Keine Daten — Server prüfen.');
    } finally {
        ccLoading = false;
    }
}
// Fuer settings.js: nach einem Save die App-Buttons/Daten aktualisieren.
window.loadDashboardState = loadDashboardState;

function scheduleDashboardRefresh() {
    if (!shouldLoadControlData()) return;
    clearTimeout(ccRefreshTimer);
    ccRefreshTimer = setTimeout(loadDashboardState, 1000);
}

function showAppMessage(data) {
    const msgEl = document.getElementById('cc-app-msg');
    msgEl.textContent = data.message || '';
    msgEl.classList.toggle('err', data.ok === false);
}

async function openApp(appId, btn) {
    btn.classList.add('busy');
    btn.disabled = true;
    try {
        const resp = await fetch('/commands/app/open', {
            method: 'POST',
            headers: ccAuthHeaders(),
            body: JSON.stringify({ app: appId }),
        });
        const data = await resp.json().catch(() => ({}));
        showAppMessage(data);
        btn.classList.add(data.ok ? 'ok' : 'err');
    } catch (e) {
        showErrorBanner({
            component: 'action',
            text: 'App konnte nicht gestartet werden.',
            hint: 'Läuft der Server?',
        });
        btn.classList.add('err');
    } finally {
        btn.classList.remove('busy');
        btn.disabled = false;
        setTimeout(() => btn.classList.remove('ok', 'err'), 2500);
    }
}

// ── Start ────────────────────────────────────────────────────────────────────
if (micMode === 'off') isMuted = true;
updateMuteButton();
updateModeButton();
updatePageButton();
updateControlViewButton();
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
if (shouldLoadControlData()) loadDashboardState();
document.body.classList.add('jarvis-ready');
