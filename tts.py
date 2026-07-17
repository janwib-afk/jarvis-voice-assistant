"""
Jarvis V2 — ElevenLabs Text-to-Speech

Reine TTS-Funktion ohne Config-/Server-Abhaengigkeit: API-Key, Voice-ID und
HTTP-Client kommen als Parameter — dadurch isoliert testbar und Settings-
Aenderungen (Voice-ID) greifen automatisch pro Aufruf.
"""

import asyncio
import re

import httpx

import obslog

# Laengere Texte werden an Satzgrenzen gestueckelt, um ElevenLabs-Cutoffs zu vermeiden.
# Bewusst grosszuegig (600), damit normale Antworten (System-Prompt: max. 3 Saetze,
# Tagesueberblick 6) in EINEM Chunk gesprochen werden — dann faellt die MP3-Verkettung
# ganz weg und es gibt keine hoerbaren Uebergaenge. Nur die laengsten Antworten
# splitten noch, weiterhin an Satzgrenzen. eleven_turbo_v2_5 vertraegt deutlich mehr,
# 600 bleibt konservativ (keine Cutoff-/Latenz-Probleme).
MAX_CHUNK_CHARS = 600

# Eigener Timeout pro Request (statt Client-Default); 1 Retry pro Chunk,
# aber nur bei Netzwerkfehlern/5xx — 4xx (Key/Voice/Quota) ist nicht transient.
TTS_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _split_long_segment(segment: str, max_chars: int) -> list[str]:
    """Zerlegt ein zu langes Segment an Wortgrenzen; ein einzelnes Wort, das laenger
    als ``max_chars`` ist, wird hart geschnitten. Kein Stueck ist laenger als
    ``max_chars``; Leerstrings entstehen nicht."""
    pieces: list[str] = []
    current = ""
    for word in segment.split():
        if len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            for i in range(0, len(word), max_chars):
                pieces.append(word[i:i + max_chars])
        elif current and len(current) + 1 + len(word) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        pieces.append(current)
    return pieces


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Teilt Text in Stuecke von hoechstens ``max_chars`` Zeichen.

    Zuerst an Satzgrenzen; ist ein Satz selbst zu lang, wird er an Wortgrenzen
    zerlegt; ein einzelnes Wort, das laenger als ``max_chars`` ist, wird hart
    geschnitten. Es entstehen keine Leerstrings, und fuer normale Texte bleibt
    ``" ".join(chunks)`` verlustfrei (ganze Saetze werden gruppiert).
    """
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list[str] = []
    current = ""
    for s in sentences:
        if not s:
            continue
        if len(s) > max_chars:
            # Satz allein schon zu lang: Puffer schliessen, dann feiner zerlegen.
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_segment(s, max_chars))
        elif current and len(current) + 1 + len(s) > max_chars:
            chunks.append(current)
            current = s
        else:
            current = f"{current} {s}" if current else s
    if current:
        chunks.append(current)
    return chunks


async def synthesize_speech(
    text: str, *, api_key: str, voice_id: str, client: httpx.AsyncClient
) -> tuple[bytes, str | None]:
    """Erzeugt TTS-Audio. Gibt (audio, fehlergrund) zurück — fehlergrund ist ein
    kurzer, nutzertauglicher Hinweis wenn KEIN Audio erzeugt werden konnte."""
    if not text.strip():
        return b"", None

    chunks = split_into_chunks(text)

    audio_parts = []
    error: str | None = None
    for chunk in chunks:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        for attempt in range(2):
            try:
                resp = await client.post(url, headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                }, json={
                    "text": chunk,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.85},
                }, timeout=TTS_TIMEOUT)
            except Exception as e:
                obslog.event("tts.request_failed", error_type=type(e).__name__)
                error = "Netzwerkfehler zu ElevenLabs."
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                break
            obslog.event("tts.chunk_received", status=resp.status_code, size=len(resp.content))
            if resp.status_code == 200:
                audio_parts.append(resp.content)
                break
            obslog.event("tts.request_failed", status=resp.status_code)
            if resp.status_code in (401, 403):
                error = f"ElevenLabs-Status {resp.status_code} — API-Key prüfen."
                break
            elif resp.status_code == 404:
                error = "ElevenLabs-Status 404 — Voice-ID prüfen."
                break
            elif resp.status_code == 429:
                error = "ElevenLabs-Kontingent oder Rate-Limit erreicht."
                break
            else:
                error = f"ElevenLabs-Status {resp.status_code}."
                if attempt == 0 and resp.status_code >= 500:
                    await asyncio.sleep(0.5)
                    continue
                break

    # MP3-Frames werden bewusst nur konkateniert, nicht neu codiert: eine saubere
    # Frame-Reparatur/Re-Codierung waere ein riskanter Umbau (zusaetzliche Audio-
    # Abhaengigkeit) ohne verlaesslichen Gewinn. Dank MAX_CHUNK_CHARS=600 hat der
    # Normalfall ohnehin nur EINEN Part (keine Verkettung); nur seltene Langantworten
    # haengen mehrere Parts an — der etablierte, getestete Pfad.
    audio = b"".join(audio_parts)
    if audio:
        error = None  # Teil-Erfolg reicht — kein Fehler melden
    return audio, error
