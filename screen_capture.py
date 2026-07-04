"""
Jarvis V2 — Screen Capture
Takes screenshots and describes them via Claude Vision.
"""

import base64
import io
from PIL import ImageGrab


def capture_screen() -> bytes:
    """Capture the entire screen, return PNG bytes."""
    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def describe_screen(anthropic_client, question: str = "") -> str:
    """Capture screen and describe it using Claude Vision.

    Mit ``question`` (z.B. "Was ist das Problem?", "Fasse diese Seite zusammen")
    wird die Frage anhand des Bildschirms beantwortet statt nur beschrieben.
    """
    png_bytes = capture_screen()
    b64 = base64.b64encode(png_bytes).decode("utf-8")

    question = (question or "").strip()
    if question:
        prompt = (
            f"Sieh dir den Bildschirm an und beantworte diese Frage auf Deutsch: {question} "
            "Antworte praezise und konkret, maximal 4-5 Saetze."
        )
    else:
        prompt = (
            "Beschreibe kurz auf Deutsch was auf diesem Bildschirm zu sehen ist. "
            "Maximal 2-3 Saetze. Nenne die wichtigsten offenen Programme und Inhalte."
        )

    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        }],
    )
    return response.content[0].text
