/* Jarvis Wire-Adapter (RFC-0005 / Phase 4H, Slice 6).
 *
 * Zentrale Frontend-Schnittstelle zum Wire-Protokoll. Bietet beim WebSocket-Handshake
 * `jarvis.v1` an; encodiert V1-Client-Commands; decodiert eingehende V1-Envelopes zu
 * UI-Events der bisherigen (Legacy-)Form, sodass main.js/settings.js/music.js ihre
 * Handler NICHT ändern müssen. Wire-Interna (Envelope, protocol_version, correlation_id)
 * bleiben hier gekapselt und verstreuen sich nicht über das Frontend.
 *
 * Fehlt Server-seitige V1-Unterstützung, bestätigt der Handshake kein Subprotokoll und
 * der Adapter arbeitet transparent im Legacy-Modus weiter.
 */
(function (global) {
  'use strict';

  var V1_SUBPROTOCOL = 'jarvis.v1';

  function createSocket(url) {
    return new WebSocket(url, [V1_SUBPROTOCOL]);
  }

  function isV1(ws) {
    return !!ws && ws.protocol === V1_SUBPROTOCOL;
  }

  function newCorrelationId() {
    try {
      if (global.crypto && typeof global.crypto.randomUUID === 'function') {
        return global.crypto.randomUUID();
      }
    } catch (e) { /* ignore */ }
    return null;
  }

  function _sendCommand(ws, type, payload) {
    if (isV1(ws)) {
      var cmd = { protocol_version: 1, type: type, payload: payload || {} };
      var cid = newCorrelationId();
      if (cid) cmd.correlation_id = cid;
      ws.send(JSON.stringify(cmd));
    } else if (type === 'say_text') {
      ws.send(JSON.stringify({ text: payload.text }));
    } else if (type === 'stop') {
      ws.send(JSON.stringify({ type: 'stop' }));
    }
  }

  function sayText(ws, text) { _sendCommand(ws, 'say_text', { text: text }); }
  function stop(ws) { _sendCommand(ws, 'stop', {}); }

  /* Rohen Frame -> UI-Event {type, ...} in Legacy-Form. V1-Envelope: payload flach;
   * error.message -> text. Unbekannter/kaputter Frame -> null (UI ignoriert ihn). */
  function decodeFrame(raw) {
    var frame;
    try { frame = JSON.parse(raw); } catch (e) { return null; }
    if (!frame || typeof frame !== 'object') return null;
    if (frame.protocol_version === 1) {
      var p = (frame.payload && typeof frame.payload === 'object') ? frame.payload : {};
      if (frame.type === 'error') {
        return { type: 'error', component: p.component, text: p.message, hint: p.hint };
      }
      var out = { type: frame.type };
      for (var k in p) { if (Object.prototype.hasOwnProperty.call(p, k)) out[k] = p[k]; }
      return out;
    }
    return frame; // Legacy unverändert
  }

  var V1_MEDIA_TYPE = 'application/vnd.jarvis.v1+json';

  /* REST-V1: setzt den Vendor-Accept + Correlation-Header und entpackt die V1-Envelope
   * zu ihrem payload (= Legacy-Body), sodass bestehende Handler (.ok/.status/.json())
   * unveraendert weiterlaufen. Legacy-Antworten (kein Vendor-Content-Type) bleiben die
   * echte fetch-Response. X-Jarvis-Token/If-Match aus options.headers bleiben erhalten. */
  async function fetchV1(url, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    headers['Accept'] = V1_MEDIA_TYPE;
    var cid = newCorrelationId();
    if (cid) headers['X-Jarvis-Correlation-ID'] = cid;
    var resp = await fetch(url, Object.assign({}, options, { headers: headers }));
    var ct = resp.headers.get('content-type') || '';
    if (ct.indexOf(V1_MEDIA_TYPE) === -1) return resp; // Legacy/kein Envelope
    var env = null;
    try { env = await resp.json(); } catch (e) { env = null; }
    var payload = (env && env.payload && typeof env.payload === 'object') ? env.payload : {};
    return {
      ok: resp.ok,
      status: resp.status,
      headers: resp.headers,
      json: function () { return Promise.resolve(payload); }
    };
  }

  global.JarvisWire = {
    createSocket: createSocket,
    isV1: isV1,
    sayText: sayText,
    stop: stop,
    decodeFrame: decodeFrame,
    fetchV1: fetchV1,
    V1_SUBPROTOCOL: V1_SUBPROTOCOL,
    V1_MEDIA_TYPE: V1_MEDIA_TYPE
  };
})(window);
