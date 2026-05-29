"""
tpgFlex Voice Booking API
Run: uvicorn backend.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timedelta
import os, sys, math, httpx, json, uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.agent.intent import detect_intent
from backend.agent.booking_engine import (
    find_stop_by_name, assign_vehicle,
    create_booking, get_all_stops, get_user_history,
    nearest_stop_to_coords
)
from backend.database import get_conn
from backend import user_profile as _up

app = FastAPI(title="tpgFlex Voice Booking API", version="1.0.0")

# In-memory context: persists origin/destination across turns so a confirmed
# intent never silently fails because the LLM omitted them from its JSON.
_booking_context: dict[str, dict] = {}

# Ramp requests store + connected driver WebSocket clients
_ramp_requests: dict[str, dict] = {}
_driver_clients: list[WebSocket] = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str      # "user" or "assistant"
    content: str

class VoiceRequest(BaseModel):
    text: str
    user_id: str = "USR_001"
    user_lat: float | None = None
    user_lon: float | None = None
    history: list[Message] = []   # full conversation history


# ── Core voice endpoint ────────────────────────────────────────────────────────

@app.post("/voice/process")
async def process_voice(req: VoiceRequest):
    # Convert history to plain dicts for the AI
    history = [{"role": m.role, "content": m.content} for m in req.history]

    # Call AI with full history
    intent_data = await detect_intent(req.text, history)

    intent      = intent_data.get("intent", "unknown")
    reply       = intent_data.get("reply", "Sorry, I didn't understand that.")
    origin      = intent_data.get("origin")
    destination = intent_data.get("destination")
    time_str    = intent_data.get("time", "now")
    passengers  = intent_data.get("passengers", 1)
    ready       = intent_data.get("ready_to_book", False)

    ctx = _booking_context.setdefault(req.user_id, {})

    _CONFIRM_WORDS = {"yes","ok","sure","correct","yep","yeah","confirm","book","go ahead","do it","book it"}
    _user_confirmed = req.text.strip().lower() in _CONFIRM_WORDS

    if intent == "restart":
        _booking_context.pop(req.user_id, None)
    else:
        # Cache stops whenever LLM extracts them (any non-restart turn)
        if origin:
            ctx["origin"]     = origin
            ctx["time_str"]   = time_str
            ctx["passengers"] = passengers
        if destination:
            ctx["destination"] = destination

        # Force confirmed when user said yes + context is complete,
        # regardless of what the LLM returned (Groq often loops on confirmation).
        if _user_confirmed and ctx.get("origin") and ctx.get("destination"):
            intent = "confirmed"

        if intent == "confirmed":
            # Always prefer cached values — LLM hallucinates on single-word replies
            origin      = ctx.get("origin",      origin)
            destination = ctx.get("destination", destination)
            time_str    = ctx.get("time_str",    time_str)
            passengers  = ctx.get("passengers",  passengers)

    # ── Confirmed: user said yes to confirmation ──────────────────────────────
    if intent == "confirmed" and origin and destination:
        pickup_stop  = find_stop_by_name(origin)
        dropoff_stop = find_stop_by_name(destination)

        if not pickup_stop or not dropoff_stop:
            missing = origin if not pickup_stop else destination
            err = f"I couldn't find the stop '{missing}'. Could you rephrase?"
            return {
                "intent": "unknown",
                "tts_response": err,
                "reply": err,
                "data": {},
                "assistant_message": err
            }

        # Resolve pickup time
        if not time_str or time_str == "now":
            pickup_dt = datetime.now() + timedelta(minutes=7)
        else:
            try:
                t = datetime.strptime(time_str, "%H:%M")
                pickup_dt = datetime.now().replace(
                    hour=t.hour, minute=t.minute, second=0, microsecond=0)
            except ValueError:
                pickup_dt = datetime.now() + timedelta(minutes=7)

        vehicle = assign_vehicle(zone=pickup_stop.get("zone")) or assign_vehicle()

        if not vehicle:
            return {
                "intent": intent,
                "tts_response": "No vehicles available right now. Please try again shortly.",
                "reply": "No vehicles available right now. Please try again shortly.",
                "data": {},
                "assistant_message": "No vehicles available right now."
            }

        booking = create_booking(
            user_id=req.user_id,
            pickup_stop=pickup_stop,
            dropoff_stop=dropoff_stop,
            passengers=passengers,
            pickup_time=pickup_dt.isoformat(),
            vehicle=vehicle
        )

        _booking_context.pop(req.user_id, None)  # clear context after booking

        confirm_msg = (
            f"Your ride is booked! Picking you up at {pickup_stop['name']} "
            f"at {pickup_dt.strftime('%H:%M')}, dropping off at {dropoff_stop['name']}. "
            f"Booking ID is {booking['booking_id']}. Your vehicle is on its way!"
        )

        return {
            "intent": "booked",
            "tts_response": confirm_msg,
            "reply": confirm_msg,
            "data": booking,
            "assistant_message": confirm_msg
        }

    # ── All other intents: just relay the AI reply ─────────────────────────────
    return {
        "intent": intent,
        "tts_response": reply,
        "reply": reply,
        "data": intent_data,
        "assistant_message": reply
    }


# ── Helper endpoints ───────────────────────────────────────────────────────────

@app.get("/stops")
def list_stops():
    return get_all_stops()

@app.get("/stops/nearest")
def nearest_stop(lat: float, lon: float):
    stop = nearest_stop_to_coords(lat, lon)
    if not stop:
        raise HTTPException(404, "No stops found")
    return stop

@app.get("/bookings/{user_id}")
def user_bookings(user_id: str):
    return get_user_history(user_id, limit=10)

@app.get("/vehicles")
def list_vehicles():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM vehicles").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ── Quick (tap-to-book) ───────────────────────────────────────────────────────
# One-shot booking for the touch panel: no LLM, no confirmation loop. Designed
# for low-literacy users who pick stops + time by tapping rather than speaking.

class QuickBookBody(BaseModel):
    pickup: str
    dropoff: str
    time: str = "now"            # "now" or "HH:MM"
    passengers: int = 1
    user_id: str = "USR_001"


@app.post("/quick-book")
def quick_book(req: QuickBookBody):
    pickup_stop  = find_stop_by_name(req.pickup)
    dropoff_stop = find_stop_by_name(req.dropoff)

    if not pickup_stop or not dropoff_stop:
        missing = req.pickup if not pickup_stop else req.dropoff
        raise HTTPException(404, f"Stop '{missing}' not found")

    if not req.time or req.time == "now":
        pickup_dt = datetime.now() + timedelta(minutes=7)
    else:
        try:
            t = datetime.strptime(req.time, "%H:%M")
            pickup_dt = datetime.now().replace(
                hour=t.hour, minute=t.minute, second=0, microsecond=0)
        except ValueError:
            pickup_dt = datetime.now() + timedelta(minutes=7)

    vehicle = assign_vehicle(zone=pickup_stop.get("zone")) or assign_vehicle()
    if not vehicle:
        raise HTTPException(503, "No vehicles available right now")

    booking = create_booking(
        user_id=req.user_id,
        pickup_stop=pickup_stop,
        dropoff_stop=dropoff_stop,
        passengers=req.passengers,
        pickup_time=pickup_dt.isoformat(),
        vehicle=vehicle,
    )

    confirm_msg = (
        f"Your ride is booked! Picking you up at {pickup_stop['name']} "
        f"at {pickup_dt.strftime('%H:%M')}, dropping off at {dropoff_stop['name']}. "
        f"Booking ID is {booking['booking_id']}. Your vehicle is on its way!"
    )
    return {"reply": confirm_msg, "data": booking}


# ── Ramp requests ─────────────────────────────────────────────────────────────

class RampRequestBody(BaseModel):
    booking_id: str
    stop_name: str
    vehicle_id: str
    user_id: str = "USR_001"
    profile: str = "motor-wheelchair"   # motor-wheelchair | manual-wheelchair


@app.post("/ramp-request")
async def create_ramp_request(req: RampRequestBody):
    req_id = "RAMP_" + str(uuid.uuid4())[:8].upper()
    record = {
        "id": req_id,
        "booking_id": req.booking_id,
        "stop_name": req.stop_name,
        "vehicle_id": req.vehicle_id,
        "user_id": req.user_id,
        "profile": req.profile,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "acknowledged_at": None,
    }
    _ramp_requests[req_id] = record

    # Push to every connected driver panel
    dead = []
    for ws in _driver_clients:
        try:
            await ws.send_text(json.dumps({"type": "ramp_request", "data": record}))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _driver_clients.remove(ws)

    return record


@app.get("/ramp-request/{req_id}")
def get_ramp_request(req_id: str):
    rec = _ramp_requests.get(req_id)
    if not rec:
        raise HTTPException(404, "Ramp request not found")
    return rec


@app.post("/ramp-request/{req_id}/acknowledge")
async def acknowledge_ramp(req_id: str):
    rec = _ramp_requests.get(req_id)
    if not rec:
        raise HTTPException(404, "Ramp request not found")
    rec["status"] = "acknowledged"
    rec["acknowledged_at"] = datetime.now().isoformat()

    # Notify driver clients of the updated state
    dead = []
    for ws in _driver_clients:
        try:
            await ws.send_text(json.dumps({"type": "ramp_acknowledged", "data": rec}))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _driver_clients.remove(ws)

    return rec


@app.get("/ramp-requests/pending")
def list_pending_ramp_requests():
    return [r for r in _ramp_requests.values() if r["status"] == "pending"]


@app.websocket("/ws/driver")
async def driver_ws(websocket: WebSocket):
    await websocket.accept()
    _driver_clients.append(websocket)
    # Send any pending requests that arrived before this driver connected
    pending = [r for r in _ramp_requests.values() if r["status"] == "pending"]
    for r in pending:
        try:
            await websocket.send_text(json.dumps({"type": "ramp_request", "data": r}))
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()   # keep-alive, ignore messages
    except WebSocketDisconnect:
        if websocket in _driver_clients:
            _driver_clients.remove(websocket)


# ── Serve frontend ─────────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ── Blind navigation additions ─────────────────────────────────────────────────

nav_clients: dict[str, WebSocket | None] = {"user": None, "display": None}


@app.websocket("/ws/navigate/{role}")
async def ws_navigate(websocket: WebSocket, role: str):
    if role not in nav_clients:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    nav_clients[role] = websocket
    other = "display" if role == "user" else "user"
    try:
        while True:
            data = await websocket.receive_text()
            peer = nav_clients.get(other)
            if peer:
                try:
                    await peer.send_text(data)
                except Exception:
                    nav_clients[other] = None
    except WebSocketDisconnect:
        nav_clients[role] = None


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _enrich_pedestrian_steps(osrm: dict) -> dict:
    """
    The public OSRM foot profile routes on the named road network and does not
    expose footway/crossing tags. For a blind walker the two things that matter
    most are (1) when they must cross a road at a junction and (2) reassurance
    that they should stay on the sidewalk between turns. We derive both from the
    maneuver type and intersection geometry that OSRM *does* return.
    """
    _TURN_MODS = {"left", "right", "slight left", "slight right",
                  "sharp left", "sharp right"}
    try:
        routes = osrm.get("routes") or []
        for route in routes:
            for leg in route.get("legs", []):
                steps = leg.get("steps", [])
                for idx, step in enumerate(steps):
                    man   = step.get("maneuver", {}) or {}
                    mtype = man.get("type", "")
                    mod   = man.get("modifier", "")
                    name  = step.get("name") or "the path"
                    ints  = step.get("intersections", []) or []

                    # Turning onto a different street at a junction means the
                    # pedestrian has to cross traffic to get there.
                    is_crossing = (
                        mtype in ("turn", "end of road", "fork")
                        and mod in _TURN_MODS
                        and idx != 0
                    )
                    step["is_crossing"] = is_crossing
                    step["crossing_hint"] = (
                        "Road crossing ahead. Stop, listen for traffic, "
                        "and use the pedestrian crossing if there is one."
                        if is_crossing else ""
                    )

                    # Side streets passed mid-segment (each is a small crossing).
                    side = max(0, len(ints) - 1)
                    step["side_streets"] = side

                    # Reassurance for longer straight stretches.
                    dist = step.get("distance", 0)
                    if dist >= 40 and mtype in ("depart", "continue",
                                                "new name", "turn"):
                        hint = f"Stay on the sidewalk along {name}."
                        if side >= 1:
                            hint += (f" You will pass {side} side "
                                     f"street{'s' if side > 1 else ''} — "
                                     f"listen for traffic at each.")
                        step["path_hint"] = hint
                    else:
                        step["path_hint"] = ""
    except Exception:
        pass
    return osrm


@app.get("/api/route")
async def get_route(from_lat: float, from_lng: float, to_lat: float, to_lng: float,
                    user_id: str | None = None):
    url = (
        f"http://router.project-osrm.org/route/v1/foot/"
        f"{from_lng},{from_lat};{to_lng},{to_lat}"
        f"?steps=true&geometries=geojson&overview=full&annotations=false"
    )
    max_walking = None
    if user_id:
        try:
            prefs = _up.get_ui_preferences(user_id)
            max_walking = prefs.get("max_walking_distance")
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            result = _enrich_pedestrian_steps(r.json())
            if max_walking is not None:
                result["max_walking_distance_metres"] = max_walking
            return result
    except Exception:
        return {"error": "routing failed"}


from backend import stop_evaluator as _se


# ── Stop Evaluator routes ──────────────────────────────────────────────────────

@app.get("/api/stop-evaluator/stops")
def evaluator_all_stops(profile: str = "all"):
    """Return every active stop with its scores (for the map/list view)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT stop_id FROM stops WHERE is_active = 1"
    ).fetchall()
    conn.close()
    return [_se.evaluate_stop(r["stop_id"], profile) for r in rows]


@app.get("/api/stop-evaluator/{stop_id}")
def evaluator_one_stop(stop_id: str, profile: str = "all"):
    """Evaluate a single stop. profile: wheelchair|blind|deaf|low_digital|elderly|all"""
    result = _se.evaluate_stop(stop_id, profile)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


class ObservationRow(BaseModel):
    stop_id: str
    block_type: str   # accessibility | safety | experience
    checked_item: str
    source: str = "manual"


@app.post("/api/stop-evaluator/observations")
def add_observations(rows: list[ObservationRow]):
    """Bulk-insert observation rows (for testing without a CSV file)."""
    conn = get_conn()
    now = datetime.now().isoformat()
    for row in rows:
        conn.execute(
            """INSERT INTO stop_observations
               (stop_id, block_type, checked_item, source, submitted_at)
               VALUES (?, ?, ?, ?, ?)""",
            (row.stop_id, row.block_type, row.checked_item, row.source, now),
        )
    conn.commit()
    conn.close()
    return {"inserted": len(rows)}


@app.get("/api/stops/search")
def search_stops(q: str = ""):
    """Fuzzy stop-name search used by the Stop Evaluator autocomplete."""
    from difflib import get_close_matches
    stops = get_all_stops()
    if not q:
        return stops[:10]
    q_lower = q.lower()
    # Substring match first (fast)
    results = [s for s in stops if q_lower in s["name"].lower()]
    if not results:
        names = [s["name"] for s in stops]
        matches = get_close_matches(q, names, n=5, cutoff=0.3)
        results = [s for s in stops if s["name"] in matches]
    return results[:8]


def _resolve_scoring_profile(profile: str, user_id: str | None) -> str:
    """Return the scoring profile to use, preferring explicit param over user's saved profile."""
    if profile != "all":
        return profile           # caller explicitly chose a profile → honour it
    if user_id:
        try:
            return _up.get_scoring_profile(user_id)
        except Exception:
            pass
    return "all"


@app.get("/api/stops/evaluate-all")
def evaluate_all_stops(profile: str = "all", user_id: str | None = None):
    """All active stops with their 5-score evaluation. Used by the map view."""
    effective = _resolve_scoring_profile(profile, user_id)
    conn = get_conn()
    rows = conn.execute("SELECT stop_id FROM stops WHERE is_active = 1").fetchall()
    conn.close()
    return [_se.evaluate_stop(r["stop_id"], effective) for r in rows]


@app.get("/api/stops/evaluate/{stop_id}")
def evaluate_one_stop(stop_id: str, profile: str = "all", user_id: str | None = None):
    """5-score evaluation for a single stop. profile: wheelchair|blind|deaf|low_digital|elderly|all"""
    effective = _resolve_scoring_profile(profile, user_id)
    result = _se.evaluate_stop(stop_id, effective)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/api/stops/nearby")
def stops_nearby(lat: float, lng: float):
    conn = get_conn()
    rows = conn.execute(
        "SELECT stop_id, name, latitude, longitude FROM stops WHERE is_active=1"
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        d = _haversine(lat, lng, row["latitude"], row["longitude"])
        results.append({
            "stop_id": row["stop_id"],
            "name": row["name"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "distance_metres": round(d)
        })
    results.sort(key=lambda x: x["distance_metres"])
    return results[:5]


# ── User Profile routes ────────────────────────────────────────────────────────

class ProfileCreateBody(BaseModel):
    accessibility_profile: str = "standard"
    display_name: str | None = None
    secondary_needs: list[str] = []
    preferred_language: str = "fr"
    voice_speed: float = 1.0
    high_contrast: bool = False
    large_text: bool = False
    haptic_feedback: bool = True
    audio_feedback: bool = True
    visual_feedback: bool = True
    auto_announce_stops: bool = False
    step_length_metres: float = 0.75
    max_walking_distance: int = 500
    emergency_contact: str | None = None


class ProfilePatchBody(BaseModel):
    accessibility_profile: str | None = None
    display_name: str | None = None
    secondary_needs: list[str] | None = None
    preferred_language: str | None = None
    voice_speed: float | None = None
    high_contrast: bool | None = None
    large_text: bool | None = None
    haptic_feedback: bool | None = None
    audio_feedback: bool | None = None
    visual_feedback: bool | None = None
    auto_announce_stops: bool | None = None
    step_length_metres: float | None = None
    max_walking_distance: int | None = None
    emergency_contact: str | None = None


@app.get("/api/profiles/available")
def profiles_available():
    """List all selectable profile types with their metadata."""
    return [
        {"key": k, "label": v["label"], "icon": v["icon"], "ui_mode": v["ui_mode"]}
        for k, v in _up.PROFILES.items()
    ]


@app.get("/api/profile/{user_id}")
def get_user_profile(user_id: str):
    return _up.get_profile(user_id)


@app.post("/api/profile/{user_id}")
def save_user_profile(user_id: str, body: ProfileCreateBody):
    """Create or replace a user profile (used by profile_setup.html)."""
    return _up.create_profile(
        user_id,
        body.accessibility_profile,
        display_name=body.display_name,
        secondary_needs=body.secondary_needs,
        preferred_language=body.preferred_language,
        voice_speed=body.voice_speed,
        high_contrast=int(body.high_contrast),
        large_text=int(body.large_text),
        haptic_feedback=int(body.haptic_feedback),
        audio_feedback=int(body.audio_feedback),
        visual_feedback=int(body.visual_feedback),
        auto_announce_stops=int(body.auto_announce_stops),
        step_length_metres=body.step_length_metres,
        max_walking_distance=body.max_walking_distance,
        emergency_contact=body.emergency_contact,
    )


@app.patch("/api/profile/{user_id}")
def patch_user_profile(user_id: str, body: ProfilePatchBody):
    """Partial update (used by profile_settings.html)."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return _up.get_profile(user_id)
    return _up.update_profile(user_id, updates)


@app.delete("/api/profile/{user_id}")
def delete_user_profile(user_id: str):
    ok = _up.delete_profile(user_id)
    if not ok:
        raise HTTPException(404, f"Profile '{user_id}' not found")
    return {"deleted": user_id}


@app.get("/api/profile/{user_id}/ui-preferences")
def get_ui_prefs(user_id: str):
    """All UI-relevant preferences consumed by profile_manager.js."""
    return _up.get_ui_preferences(user_id)
