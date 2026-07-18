/* Jarvis Voice-Reducer (RFC-0006 + Amendment 1 / Phase 4J, Slice 7).
 *
 * REINER Zustandskern des Browsers: kein DOM, kein WebSocket, kein Audio, keine
 * SpeechRecognition, kein localStorage, keine Timer. `reduce` ist deterministisch
 * und gibt nur BESCHRIEBENE Effekte zurueck — ausgefuehrt werden sie ausserhalb.
 *
 * Fuenf orthogonale Regionen plus die Client-Session-Ebene (Amendment 1):
 *   Connection : disconnected | connecting | connected | reconnecting
 *   Capture    : unavailable | idle | listening | muted
 *   Playback   : locked | idle | playing        (locked = Audio noch nicht freigeschaltet)
 *   Interaction: idle | awaiting-response | action-running | stopping
 *   Overlays   : Menge aus degraded | recoverable-error | fatal-error
 *   ClientSession: { greeted, epoch }           ueberlebt Reconnects, nicht Page Load
 *
 * Presentation wird IMMER abgeleitet (§13) und nie gesetzt. Das DOM ist Ausgabe,
 * nie Zustandsquelle.
 */
(function (global) {
  'use strict';

  var MAX_AUDIO_QUEUE = 32;

  function initialVoiceState() {
    return Object.freeze({
      connection: 'disconnected',
      capture: 'unavailable',
      playback: 'locked',
      interaction: 'idle',
      overlays: Object.freeze([]),
      greeted: false,
      epoch: 0,
      audioQueue: Object.freeze([]),
      micMode: 'auto'
    });
  }

  function _next(state, patch, bumpEpoch) {
    var out = {};
    for (var k in state) { if (Object.prototype.hasOwnProperty.call(state, k)) out[k] = state[k]; }
    for (var p in patch) { if (Object.prototype.hasOwnProperty.call(patch, p)) out[p] = patch[p]; }
    if (bumpEpoch) out.epoch = state.epoch + 1;
    if (out.overlays) out.overlays = Object.freeze(out.overlays.slice());
    if (out.audioQueue) out.audioQueue = Object.freeze(out.audioQueue.slice());
    return Object.freeze(out);
  }

  function _withOverlay(list, name) {
    return list.indexOf(name) === -1 ? list.concat([name]) : list.slice();
  }
  function _withoutOverlay(list, name) {
    return list.filter(function (o) { return o !== name; });
  }

  function _result(state, effects) {
    return { state: state, effects: effects || [] };
  }

  /* Stale-Guard (Amendment 1 / M3): jede asynchrone Operation merkt sich die Epoch
   * beim PLANEN; bei Zustellung mit veralteter Epoch wird sie verworfen. */
  function isStale(state, epoch) {
    return typeof epoch !== 'number' || epoch !== state.epoch;
  }

  /* Abgeleiteter Presentation State (§13) — erste zutreffende Regel gewinnt.
   * degraded/recoverable-error sind ADDITIVE Overlays und aendern ihn nicht. */
  function presentation(state) {
    if (state.connection !== 'connected') return 'disconnected';
    if (state.overlays.indexOf('fatal-error') !== -1) return 'error';
    if (state.playback === 'playing') return 'speaking';
    if (state.interaction === 'stopping') return 'stopping';
    if (state.interaction === 'action-running') return 'action-running';
    if (state.interaction === 'awaiting-response') return 'thinking';
    if (state.capture === 'listening') return 'listening';
    if (state.capture === 'muted') return 'muted';
    return 'idle';
  }

  function reduce(state, event) {
    if (!event || typeof event.type !== 'string') return _result(state, []);

    // Stale-Ereignisse veraendern NICHTS: kein State, keine Effects, kein Render.
    if (typeof event.epoch === 'number' && isStale(state, event.epoch)) {
      return _result(state, []);
    }

    switch (event.type) {
      // ── Connection ─────────────────────────────────────────────────────
      case 'WsConnecting':
        return _result(_next(state, { connection: 'connecting' }), ['Render']);

      case 'WsOpen': {
        var eff = ['ResetBackoff', 'Render'];
        var patch = { connection: 'connected' };
        // Greeting-Latch (Amendment 1 / M2): GENAU EINMAL pro Client Session —
        // ueberlebt jeden Reconnect. Verhindert echte LLM-/TTS-Kosten.
        if (!state.greeted) {
          patch.greeted = true;
          patch.interaction = 'awaiting-response';
          eff = ['SendGreeting'].concat(eff);
        }
        if (state.capture === 'unavailable' && state.micMode === 'auto') {
          patch.capture = 'idle';
        }
        return _result(_next(state, patch, true), eff);
      }

      case 'WsClosed':
        return _result(_next(state, {
          connection: 'reconnecting',
          interaction: 'idle'
        }, true), ['ScheduleReconnect', 'Render']);

      case 'WsError':
        return _result(_next(state, {
          overlays: _withOverlay(state.overlays, 'recoverable-error')
        }), ['ShowBanner', 'Render']);

      // ── Capture ────────────────────────────────────────────────────────
      case 'MicAvailable':
        return _result(_next(state, {
          capture: state.capture === 'unavailable' ? 'idle' : state.capture,
          micMode: event.micMode || state.micMode
        }), ['Render']);

      case 'MicModeChanged':
        return _result(_next(state, { micMode: event.micMode || 'auto' }), ['Render']);

      case 'MuteToggled': {
        var muted = state.capture !== 'muted';
        // Mute ist ein Capture-Modifikator: Playback laeuft ggf. WEITER.
        return _result(_next(state, { capture: muted ? 'muted' : 'idle' }, true),
                       muted ? ['StopRecognition', 'Render'] : ['MaybeResumeListening', 'Render']);
      }

      case 'StartListening':
        if (state.capture === 'muted' || state.capture === 'unavailable') {
          return _result(state, []);           // unter Mute kein normales Zuhoeren
        }
        if (state.playback === 'playing') return _result(state, []);
        return _result(_next(state, { capture: 'listening' }), ['StartRecognition', 'Render']);

      case 'RecognitionResult': {
        // Unter Mute werden NUR Kontrolláusserungen (Stop/Entstummen) erkannt;
        // normale Sprache wird verworfen (Praezisierung 1).
        if (state.capture === 'muted' && !event.control) return _result(state, []);
        if (event.control === 'stop') return reduce(state, { type: 'StopRequested' });
        if (event.control === 'unmute') return reduce(state, { type: 'MuteToggled' });
        return _result(_next(state, {
          capture: 'idle', interaction: 'awaiting-response'
        }), ['SendText', 'Render']);
      }

      case 'RecognitionEnd':
      case 'RecognitionError':
        if (state.capture !== 'listening') return _result(state, []);
        return _result(_next(state, { capture: 'idle' }), ['MaybeResumeListening', 'Render']);

      // ── Playback (inkl. locked, Amendment 1 / M1) ──────────────────────
      case 'AudioReceived': {
        var queued = state.audioQueue.concat([event.audio]).slice(-MAX_AUDIO_QUEUE);
        if (state.playback === 'locked') {
          // Gesperrt: puffern statt abspielen, Nutzergeste anfordern.
          return _result(_next(state, {
            audioQueue: queued,
            overlays: _withOverlay(state.overlays, 'recoverable-error')
          }), ['AwaitUserGesture', 'ShowBanner', 'Render']);
        }
        if (state.playback === 'playing') {
          return _result(_next(state, { audioQueue: queued }), []);
        }
        return _result(_next(state, {
          playback: 'playing', audioQueue: queued, capture: 'idle'
        }), ['StopRecognition', 'PlayAudio', 'Render']);
      }

      case 'UserGesture': {
        if (state.playback !== 'locked') return _result(state, []);
        var unlocked = { playback: 'idle',
                         overlays: _withoutOverlay(state.overlays, 'recoverable-error') };
        if (state.audioQueue.length) {
          unlocked.playback = 'playing';
          return _result(_next(state, unlocked),
                         ['UnlockAudio', 'PlayAudio', 'DismissBanner', 'Render']);
        }
        return _result(_next(state, unlocked), ['UnlockAudio', 'DismissBanner', 'Render']);
      }

      case 'AutoplayBlocked':
        // Zurueck nach locked + recoverable Overlay (kein Fehlerzustand).
        return _result(_next(state, {
          playback: 'locked',
          overlays: _withOverlay(state.overlays, 'recoverable-error')
        }), ['AwaitUserGesture', 'ShowBanner', 'Render']);

      case 'AudioEnded':
      case 'AudioError': {
        if (state.playback !== 'playing') return _result(state, []);
        var rest = state.audioQueue.slice(1);
        if (rest.length) {
          return _result(_next(state, { audioQueue: rest }), ['PlayAudio', 'Render']);
        }
        return _result(_next(state, { playback: 'idle', audioQueue: [] }),
                       ['MaybeResumeListening', 'Render']);
      }

      // ── Interaction ────────────────────────────────────────────────────
      case 'SayTextSent':
        return _result(_next(state, { interaction: 'awaiting-response' }), ['Render']);

      case 'ActionStart':
        return _result(_next(state, { interaction: 'action-running' }), ['Render']);

      case 'ActionDone':
      case 'ActionError':
        return _result(_next(state, { interaction: 'idle' }), ['Render']);

      case 'SpokenResponse':
        return _result(_next(state, {
          interaction: state.interaction === 'action-running' ? 'action-running' : 'idle'
        }), ['Render']);

      case 'StopRequested':
        return _result(_next(state, {
          interaction: 'stopping',
          playback: state.playback === 'playing' ? 'idle' : state.playback,
          audioQueue: []
        }, true), ['AbortAudio', 'ClearAudioQueue', 'SendStopCommand', 'Render']);

      case 'StopAck':
        return _result(_next(state, {
          interaction: 'idle',
          overlays: _withoutOverlay(state.overlays, 'recoverable-error')
        }), ['MaybeResumeListening', 'DismissBanner', 'Render']);

      // ── Overlays ───────────────────────────────────────────────────────
      case 'ErrorEvent':
        return _result(_next(state, {
          overlays: _withOverlay(state.overlays,
                                 event.fatal ? 'fatal-error' : 'recoverable-error')
        }), ['ShowBanner', 'Render']);

      case 'Degraded':
        return _result(_next(state, {
          overlays: _withOverlay(state.overlays, 'degraded')
        }), ['Render']);

      case 'ErrorDismissed':
        return _result(_next(state, {
          overlays: _withoutOverlay(state.overlays, event.overlay || 'recoverable-error')
        }), ['DismissBanner', 'Render']);

      default:
        // §19: unbekanntes Ereignis = totaler No-Op.
        return _result(state, []);
    }
  }

  /* Reconnect-Backoff (Slice 9f).
   *
   * Der Versuchszaehler ist eine PRIVATE ADAPTER-RESSOURCE des Reconnects, kein
   * Zustand einer der fuenf Regionen und keine Presentation-Wahrheit: die
   * Connection-Region kennt nur `reconnecting`, nicht wie oft es schon scheiterte.
   * Er liegt deshalb hinter dieser Schnittstelle statt als freie Variable herum,
   * damit es genau einen Besitzer gibt.
   *
   * Kein Reducer, aber ebenso ohne I/O: `fail()` BESCHREIBT nur die Verzoegerung
   * und die Warnschwelle — Timer und Banner fuehrt der Adapter aus.
   */
  function createBackoff() {
    var attempts = 0;
    return {
      fail: function () {
        attempts += 1;
        return Object.freeze({
          attempt: attempts,
          delayMs: Math.min(3000 * Math.pow(2, attempts - 1), 30000),
          // Genau EINMAL warnen, nicht bei jedem Versuch: ein Serverneustart
          // darf kein Bannergewitter ausloesen.
          warn: attempts === 3
        });
      },
      reset: function () { attempts = 0; }
    };
  }

  var api = {
    initialVoiceState: initialVoiceState,
    reduce: reduce,
    presentation: presentation,
    isStale: isStale,
    createBackoff: createBackoff
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  global.JarvisVoice = api;
})(typeof window !== 'undefined' ? window : globalThis);
