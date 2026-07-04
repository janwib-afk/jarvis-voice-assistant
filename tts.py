"""
Jarvis V2 — ElevenLabs Text-to-Speech

Reine TTS-Funktion ohne Config-/Server-Abhaengigkeit: API-Key, Voice-ID und
HTTP-Client kommen als Parameter — dadurch isoliert testbar und Settings-
Aenderungen (Voice-ID) greifen automatisch pro Aufruf.
"""

import asyncio
import logging
import re

import httpx

logger = logging.getLogger("jarvis.tts")

# Laengere Texte werden an Satzgrenzen gestueckelt, um ElevenLabs-Cutoffs zu vermeiden.
MAX_CHUNK_CHARS = 250

# Eigener Timeout pro Request (statt Client-Default); 1 Retry pro Chunk,
# aber nur bei Netzwerkfehlern/5xx — 4xx (Key/Voice/Quota) ist nicht transient.
TTS_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Teilt Text an Satzgrenzen in Stuecke von maximal ``max_chars`` Zeichen."""
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current.strip())
            current = s
        else:
            current = (current + " " + s).strip()
    if current:
        chunks.append(current.strip())
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
            except Exception:
                logger.warning("TTS-Aufruf fehlgeschlagen (Versuch %d)", attempt + 1, exc_info=True)
                error = "Netzwerkfehler zu ElevenLabs."
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                break
            logger.debug("TTS chunk status: %s, size: %d", resp.status_code, len(resp.content))
            if resp.status_code == 200:
                audio_parts.append(resp.content)
                break
            logger.warning("TTS-Fehler (Status %s): %s", resp.status_code, resp.text[:200])
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

    audio = b"".join(audio_parts)
    if audio:
        error = None  # Teil-Erfolg reicht — kein Fehler melden
    return audio, error
