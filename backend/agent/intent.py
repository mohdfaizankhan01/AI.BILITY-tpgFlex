"""
AI Agent using Groq API with fallback keyword parser.
If Groq returns empty or invalid JSON, keyword parser handles it.
"""

import json
import re
import httpx
import os
from dotenv import load_dotenv
load_dotenv()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

SYSTEM_PROMPT = """
You are a booking assistant for tpgFlex, Geneva's on-demand shared minibus service.
Collect origin, destination, time, and passengers then confirm before booking.

Once you have origin + destination, ask for time (default now if not given).
Then ask user to confirm. On confirm set intent to "confirmed".
On yes/ok/correct set intent to "confirmed".
On restart/no set intent to "restart".

Stop name mappings:
- airport, aeroport -> Palexpo
- hospital, hopital, HUG -> Hopital Cantonal
- train station, gare, cornavin -> Cornavin
- cern -> CERN
- carouge -> Carouge-Marche
- nations, UN -> Nations
- onex -> Onex-Cite
- lancy -> Lancy-Pont-Rouge
- meyrin -> Meyrin-Village
- rive -> Rive
- plainpalais -> Plainpalais

IMPORTANT: Respond ONLY with a single valid JSON object. No text before or after. No markdown.

{
  "intent": "book_ride" | "awaiting_confirmation" | "confirmed" | "find_stop" | "check_status" | "greeting" | "restart" | "unknown",
  "origin": "<stop name or null>",
  "destination": "<stop name or null>",
  "time": "<HH:MM or now or null>",
  "passengers": 1,
  "reply": "<short friendly reply to speak aloud>",
  "ready_to_book": false
}
"""

# ── Keyword fallback ──────────────────────────────────────────────────────────

DEST_MAP = {
    "airport": "Palexpo", "aeroport": "Palexpo", "palexpo": "Palexpo",
    "hospital": "Hopital Cantonal", "hopital": "Hopital Cantonal", "hug": "Hopital Cantonal",
    "cornavin": "Cornavin", "station": "Cornavin", "gare": "Cornavin", "train": "Cornavin",
    "cern": "CERN", "carouge": "Carouge-Marche", "nations": "Nations",
    "onex": "Onex-Cite", "lancy": "Lancy-Pont-Rouge", "meyrin": "Meyrin-Village",
    "rive": "Rive", "plainpalais": "Plainpalais",
}

def _keyword_intent(text: str, history: list) -> dict:
    """Simple fallback when Groq fails."""
    lower = text.lower()

    # Pull known stops from history
    origin = None
    destination = None
    for msg in history:
        c = msg.get("content", "").lower()
        for kw, stop in DEST_MAP.items():
            if kw in c:
                if "from" in c or "at" in c or "origin" in c or "location" in c:
                    origin = stop
                elif destination is None:
                    destination = stop

    # Check current message
    for kw, stop in DEST_MAP.items():
        if kw in lower:
            if origin is None:
                origin = stop
            elif destination is None and stop != origin:
                destination = stop

    if destination and origin:
        return {
            "intent": "awaiting_confirmation",
            "origin": origin, "destination": destination,
            "time": "now", "passengers": 1,
            "reply": f"Just to confirm — pick up at {origin}, drop off at {destination}. Shall I book this?",
            "ready_to_book": True
        }
    elif destination and not origin:
        return {
            "intent": "book_ride",
            "origin": None, "destination": destination,
            "time": "now", "passengers": 1,
            "reply": f"Got it, heading to {destination}. Where are you coming from?",
            "ready_to_book": False
        }
    elif any(w in lower for w in ["yes", "confirm", "ok", "correct", "sure", "book it"]):
        return {
            "intent": "confirmed", "origin": origin, "destination": destination,
            "time": "now", "passengers": 1,
            "reply": "Booking confirmed!", "ready_to_book": True
        }

    return {
        "intent": "unknown", "origin": None, "destination": None,
        "time": None, "passengers": 1,
        "reply": "Could you tell me where you are and where you'd like to go?",
        "ready_to_book": False
    }


# ── Main intent function ──────────────────────────────────────────────────────

async def detect_intent(user_text: str, history: list[dict]) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history
    messages.append({"role": "user", "content": user_text})

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GROQ_API_URL,
                json={
                    "model": "llama-3.3-70b-versatile",
                    "max_tokens": 400,
                    "temperature": 0.1,
                    "messages": messages
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {GROQ_API_KEY}"
                },
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    raw = part
                    break

        raw = raw.strip()

        if not raw:
            raise ValueError("Empty response from Groq")

        return json.loads(raw)

    except Exception as e:
        # Groq failed — use keyword fallback silently
        print(f"[intent fallback] {type(e).__name__}: {e}")
        return _keyword_intent(user_text, history)