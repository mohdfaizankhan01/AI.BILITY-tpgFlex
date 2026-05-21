# tpgFlex Voice Booking — Architecture

## Overview

tpgFlex Voice Booking is an AI-powered ride-booking assistant for tpgFlex, Geneva's on-demand shared minibus service. Users speak or type a destination; the system extracts intent, confirms details, and creates a booking. A separate driver panel handles real-time accessibility alerts. A blind navigation mode provides audio-guided pedestrian routing.

```
Browser (passenger / driver / blind user)
        │  HTTP REST + WebSocket
        ▼
FastAPI backend  ──► Groq API (LLaMA 3.3-70B)
        │
        ▼
SQLite (mock_data/tpgflex.db)
        │
        └──► OSRM public API (pedestrian routing, outbound only)
```

---

## Frontend — 5 Pages

All pages are static HTML/CSS/JS served by the backend at `/static/<page>.html`. They must be loaded through `http://localhost:8000/` (not as `file://` URLs) because navigation links use absolute paths like `/static/navigate_user.html`.

| File | Purpose | Who uses it |
|---|---|---|
| `index.html` | Main passenger UI: voice/text input, chat, map, booking flow | Passenger |
| `driver_panel.html` | Real-time accessibility alerts, ramp request queue | Driver |
| `navigate_user.html` | Audio-guided step-by-step navigation (blind mode, user side) | Blind passenger |
| `navigate_display.html` | Mirrored map display for a companion or mounted screen | Companion/display |
| `navigate_map.html` | Map-only component embedded by navigate pages | Internal |

The main page (`index.html`) talks to the backend over both REST (booking) and WebSocket (navigation relay). The driver panel connects to `/ws/driver` and listens for push messages. The navigate pages connect to `/ws/navigate/{role}` where role is `user` or `display`.

---

## Backend — FastAPI (`backend/main.py`)

Single-process FastAPI app running under uvicorn on port 8000.

### REST Endpoints

**Voice & booking**

| Method | Path | What it does |
|---|---|---|
| `POST` | `/voice/process` | Core endpoint. Takes user text + history, calls AI, runs booking logic |
| `POST` | `/quick-book` | Tap-to-book shortcut — no AI, no confirmation loop |

**Data queries**

| Method | Path | What it does |
|---|---|---|
| `GET` | `/stops` | List all active stops |
| `GET` | `/stops/nearest?lat&lon` | Nearest stop to a GPS coordinate |
| `GET` | `/api/stops/nearby?lat&lng` | Top 5 stops sorted by distance (for navigation) |
| `GET` | `/bookings/{user_id}` | Last 10 bookings for a user |
| `GET` | `/vehicles` | List all vehicles |
| `GET` | `/health` | Health check |

**Ramp / accessibility**

| Method | Path | What it does |
|---|---|---|
| `POST` | `/ramp-request` | Create a wheelchair ramp request; pushes to all driver panels |
| `GET` | `/ramp-request/{req_id}` | Get status of a specific ramp request |
| `POST` | `/ramp-request/{req_id}/acknowledge` | Driver confirms ramp is deployed |
| `GET` | `/ramp-requests/pending` | All unacknowledged ramp requests |

**Routing & static**

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/route` | Proxy to OSRM; enriches steps with blind-navigation hints |
| `GET` | `/` | Serves `frontend/index.html` |
| `GET` | `/static/*` | Serves all frontend files |

### WebSocket Endpoints

| Path | Purpose |
|---|---|
| `/ws/driver` | Persistent connection for each driver panel. Backend pushes `ramp_request` and `ramp_acknowledged` events in real time |
| `/ws/navigate/{role}` | Relay bridge between `user` and `display` sides of blind navigation. Any message received from one role is forwarded verbatim to the other |

### In-Memory State

| Variable | Type | Contents |
|---|---|---|
| `_booking_context` | `dict[user_id → dict]` | Per-user conversation context: cached origin, destination, time, passengers across multi-turn dialogue |
| `_ramp_requests` | `dict[req_id → dict]` | All ramp requests for the session (not persisted to DB) |
| `_driver_clients` | `list[WebSocket]` | All currently connected driver panel sockets |
| `nav_clients` | `dict` | `{"user": ws, "display": ws}` — the active navigation pair |

---

## AI Agent Layer (`backend/agent/`)

### Intent Detection (`intent.py`)

1. Builds a message list: system prompt + conversation history + current user message.
2. Sends to Groq API (`llama-3.3-70b-versatile`, temperature 0.1, max 400 tokens).
3. Parses the JSON response. Strips markdown fences if the model wraps them.
4. On any failure (timeout, bad JSON, empty response) falls back to a local keyword parser.

**Groq response schema:**
```json
{
  "intent": "book_ride | awaiting_confirmation | confirmed | find_stop | check_status | greeting | restart | unknown",
  "origin": "<stop name or null>",
  "destination": "<stop name or null>",
  "time": "<HH:MM or now or null>",
  "passengers": 1,
  "reply": "<short spoken reply>",
  "ready_to_book": false
}
```

**Keyword fallback** (`_keyword_intent`): scans the user message and history for known place keywords (e.g. "airport" → Palexpo, "hospital" → Hôpital Cantonal) and constructs a minimal intent dict. Used silently when Groq is unavailable.

### Booking Engine (`booking_engine.py`)

Called by `main.py` after the AI returns `confirmed` intent.

| Function | What it does |
|---|---|
| `find_stop_by_name(query)` | Fuzzy-matches a free-text name to a stop using `difflib.get_close_matches` (cutoff 0.3), with a substring fallback |
| `nearest_stop_to_coords(lat, lon)` | Returns the stop with the smallest haversine distance |
| `assign_vehicle(zone)` | Finds an `available` vehicle, optionally filtered by zone. If none found (all `in_service`), recycles them back to `available` |
| `create_booking(...)` | Inserts a booking row, marks the vehicle `in_service`, returns a summary dict |
| `get_user_history(user_id)` | Returns last N bookings for a user |

---

## Conversation Flow (Voice Booking)

```
User speaks/types
       │
       ▼
POST /voice/process
       │
       ├─► detect_intent(text, history)   ← Groq API or keyword fallback
       │         returns intent JSON
       │
       ├─► Cache origin/destination into _booking_context[user_id]
       │   (LLM can omit fields on short replies like "yes"; cache preserves them)
       │
       ├─► If user said "yes/ok/confirm" AND context has origin+dest → force intent="confirmed"
       │
       └─► intent == "confirmed"?
               │ YES
               ├─► find_stop_by_name(origin)
               ├─► find_stop_by_name(destination)
               ├─► assign_vehicle(zone)
               ├─► create_booking(...)  → SQLite INSERT
               └─► Return confirmation message + booking data
               │
               NO → Return AI reply as-is (clarification, greeting, etc.)
```

---

## Ramp Request Flow (Accessibility)

```
Passenger (wheelchair profile) requests ramp via UI
       │
       ▼
POST /ramp-request
       │
       ├─► Store in _ramp_requests dict (in-memory)
       └─► Push {"type": "ramp_request", "data": record}
           to every WebSocket in _driver_clients
                   │
                   ▼
           Driver panel receives push, displays alert
                   │
           Driver taps "Acknowledge"
                   │
                   ▼
POST /ramp-request/{id}/acknowledge
       │
       ├─► Update status to "acknowledged", set acknowledged_at
       └─► Push {"type": "ramp_acknowledged", "data": record}
           to all driver clients
```

---

## Blind Navigation Flow

```
navigate_user.html                    navigate_display.html
       │                                      │
       └──── WS /ws/navigate/user ──────────────┘
                      │
              backend relay (nav_clients dict)
              any message from "user" → forwarded to "display"
              any message from "display" → forwarded to "user"

Step-by-step routing:
  navigate_user.html
       │
       └─► GET /api/route?from_lat&from_lng&to_lat&to_lng
                   │
                   └─► OSRM public API (foot profile, steps+geometry)
                               │
                   _enrich_pedestrian_steps()
                   adds per-step fields:
                     - is_crossing (bool)
                     - crossing_hint (spoken warning at junctions)
                     - side_streets (count of intersections mid-segment)
                     - path_hint (reassurance for long straight segments)
                               │
                   Returns enriched JSON to frontend
                   Frontend reads steps aloud via Web Speech API (TTS)
```

---

## Database (`backend/mock_data/tpgflex.db`)

SQLite. Seeded once by `backend/mock_data/seed.py`.

| Table | Key columns | Records |
|---|---|---|
| `stops` | stop_id, name, latitude, longitude, zone, is_active | 15 |
| `vehicles` | vehicle_id, status, capacity, zone, current_lat/lng | 8 |
| `users` | user_id, name, email, phone, preferred_language | 5 |
| `bookings` | booking_id, status, passenger_status, user_id, pickup_id, dropoff_id, selected_pickup_time, vehicle_id, passengers | 118 (seeded) |
| `locations` | date, driver, latitude, longitude, bearing, accuracy | 80 (vehicle telemetry) |

Vehicle status lifecycle: `available` → `in_service` (on booking) → recycled back to `available` when the pool is exhausted.

### Sample Data

**stops**
```
stop_id   | name               | latitude | longitude | zone | is_active
----------|--------------------|----------|-----------|------|----------
STOP_001  | Cornavin           | 46.2100  | 6.1422    | A    | 1
STOP_002  | Carouge-Marché     | 46.1833  | 6.1400    | B    | 1
STOP_003  | Palexpo            | 46.2333  | 6.1167    | C    | 1
STOP_004  | Hôpital Cantonal   | 46.1938  | 6.1477    | A    | 1
STOP_005  | CERN               | 46.2330  | 6.0550    | C    | 1
```

**vehicles**
```
vehicle_id | status     | capacity | zone | current_lat | current_lng
-----------|------------|----------|------|-------------|------------
VEH_001    | in_service | 8        | A    | 46.2100     | 6.1422
VEH_002    | available  | 6        | B    | 46.1833     | 6.1400
VEH_003    | available  | 8        | C    | 46.2333     | 6.1167
VEH_004    | in_service | 8        | A    | 46.1938     | 6.1477
```

**users**
```
user_id | name           | email                    | phone          | preferred_language
--------|----------------|--------------------------|----------------|-------------------
USR_001 | Marie Dubois   | marie.dubois@email.ch    | +41791234567   | fr
USR_002 | John Smith     | john.smith@email.com     | +41791234568   | en
USR_003 | Ahmed Hassan   | ahmed.h@email.com        | +41791234569   | fr
```

**bookings**
```
booking_id | status    | passenger_status | user_id | pickup      | dropoff          | pickup_time          | vehicle_id
-----------|-----------|------------------|---------|-------------|------------------|----------------------|-----------
33c59378   | Validated | Trip completed   | USR_002 | Palexpo     | Cornavin         | 2026-04-06T08:48:00  | VEH_004
5d192941   | Validated | Trip completed   | USR_004 | Bachet-de-Pesay | Vernier-Village | 2026-03-30T03:41:00 | VEH_001
0abd7a6a   | Cancelled | Cancelled        | USR_001 | Onex-Cité   | Hôpital Cantonal | 2026-03-28T05:43:00  | VEH_005
8a03e037   | Cancelled | Cancelled        | USR_002 | Carouge-Marché | Aïre          | 2026-03-21T06:47:00  | VEH_004
```

**locations** (live vehicle telemetry)
```
location_id | datetime                  | driver          | latitude   | longitude  | bearing | accuracy | vehicle_id
------------|---------------------------|-----------------|------------|------------|---------|----------|----------
6e7d3c8c   | 2026-04-18T20:38:38       | Driver_VEH_001  | 46.20931   | 6.14494    | 8.55    | 86.06    | VEH_001
3c6de40f   | 2026-04-18T21:02:38       | Driver_VEH_001  | 46.20823   | 6.14648    | 8.60    | 259.68   | VEH_001
e5e6dc82   | 2026-04-18T20:05:38       | Driver_VEH_001  | 46.21329   | 6.14157    | 3.42    | 127.89   | VEH_001
```

---

## External Dependencies

| Service | Used for | Failure mode |
|---|---|---|
| Groq API (`api.groq.com`) | LLM intent extraction | Silent fallback to keyword parser |
| OSRM (`router.project-osrm.org`) | Pedestrian turn-by-turn routing | Returns `{"error": "routing failed"}` |

---

## Running the Project

```bash
# Install dependencies (one time)
pip install -r requirements.txt

# Start backend (keep running)
uvicorn backend.main:app --reload --port 8000

# Open app — must use the backend URL, not a file:// path
open http://localhost:8000/
```

API explorer: `http://localhost:8000/docs`
