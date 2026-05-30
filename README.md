# tpgFlex AI Voice Booking Assistant

AI-powered voice booking + accessibility platform for **tpgFlex**, Geneva's on-demand shared minibus service. Passengers speak or type a destination, the system extracts intent via LLM, confirms details, and creates a booking. Includes a driver panel for accessibility alerts and an audio-guided navigation mode for visually-impaired users.

---

## Setup

### 1. Install + seed

```bash
bash setup.sh
```

### 2. Set your Groq API key

Create a `.env` file in the project root:

```bash
GROQ_API_KEY=gsk_your_key_here
```

Get a key at https://console.groq.com/keys. The key is read from the environment — there is no hardcoded fallback.

### 3. Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Then open http://localhost:8000/ in your browser. **Do not open the HTML files via `file://`** — the navigation pages use absolute paths that only work when served by the backend.

API docs: http://localhost:8000/docs

---

## Try it

Say or type:
- *"Book a ride to Cornavin"*
- *"I need to get to the hospital at 9am"*
- *"Take me to CERN for 2 passengers"*
- *"What's the nearest stop to Plainpalais?"*

---

## Frontend pages

All served from the backend at `/` (which loads `index.html`) and `/static/<page>.html`.

| Page | Purpose | Who uses it |
|---|---|---|
| `index.html` | Main passenger UI: voice/text input, chat, map, booking flow | Passenger |
| `driver_panel.html` | Real-time accessibility alerts, ramp request queue (WebSocket) | Driver |
| `navigate_user.html` | Audio-guided step-by-step pedestrian navigation (blind mode) | Visually-impaired passenger |
| `navigate_display.html` | Mirrored map display for a companion or mounted screen | Companion |
| `navigate_map.html` | Map-only component embedded by navigate pages | Internal |
| `camtest.html` | Camera permission / device diagnostic | Debug |

---

## Project structure

```
tpgflex-voice/
├── backend/
│   ├── main.py                    ← FastAPI app — REST + WebSocket routes
│   ├── database.py                ← SQLite connection
│   ├── seeBooking.py              ← Booking inspection utility
│   ├── agent/
│   │   ├── intent.py              ← Groq (LLaMA 3.3-70B) intent detection + keyword fallback
│   │   └── booking_engine.py      ← Stop matching, vehicle assignment, booking creation
│   └── mock_data/
│       ├── seed.py                ← Creates + seeds tpgflex.db
│       └── tpgflex.db             ← Generated on first run (gitignored)
├── frontend/                      ← Static HTML/CSS/JS pages (see table above)
├── requirements.txt
└── setup.sh
```

---

## Key API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /voice/process` | Main conversational endpoint — accepts text + history, returns intent + reply |
| `POST /quick-book` | Single-shot booking without conversation |
| `GET /stops`, `GET /stops/nearest` | Stop lookups |
| `GET /bookings/{user_id}` | User booking history |
| `POST /ramp-request` | Passenger requests ramp deployment — pushed to driver panel |
| `GET /api/route` | Pedestrian routing via OSRM public API |
| `WS /ws/driver` | Driver panel real-time alerts |
| `WS /ws/navigate/{role}` | Navigation relay between user and display |

---

## Automated Epicollect survey sync

Stop scores are computed live from the `stop_observations` table — there is **no
model to retrain**. New community survey responses just need to land in that table,
and `backend/epicollect_sync.py` pulls them straight from the
[Epicollect5 API](https://five.epicollect.net/project/crowdsense):

```bash
python -m backend.epicollect_sync            # fetch + refresh scores
python -m backend.epicollect_sync --dry-run  # preview, no DB write
```

Or trigger over HTTP (handy for a cron job):

```bash
curl -X POST http://localhost:8000/api/stop-evaluator/sync
```

What it does each run (idempotent):
1. Fetches all entries (public project; OAuth2 for private — see env below).
2. Auto-creates any unknown survey stop, geocoding its name via OpenStreetMap.
3. Parses the bilingual `['Surface dure et stable / Hard stable surface', …]` answers.
4. Routes each item to its scoring block using the weight dicts in `stop_evaluator.py`
   (the single source of truth).
5. Replaces all `source='epicollect'` rows — demo/manual observations are preserved,
   edits & deletions are reflected, nothing is duplicated.

**Hands-off polling** — set `EPICOLLECT_AUTO_SYNC=1` and the backend re-syncs on a
timer (default 60 min). Or schedule the `curl` above with cron.

| Env var | Default | Purpose |
|---|---|---|
| `EPICOLLECT_PROJECT_SLUG` | `crowdsense` | Epicollect project slug |
| `EPICOLLECT_CLIENT_ID` / `_CLIENT_SECRET` | – | OAuth2 creds (private projects only) |
| `EPICOLLECT_AUTO_SYNC` | `0` | `1` enables the background poller |
| `EPICOLLECT_SYNC_INTERVAL_MIN` | `60` | Poll interval (minutes) |
| `EPICOLLECT_AUTO_CREATE_STOPS` | `1` | Geocode + insert unknown survey stops |

---

## Switching to real tpgFlex data

1. Replace `backend/database.py` with the real connector:
   ```python
   import mysql.connector
   def get_conn():
       return mysql.connector.connect(host=..., user=..., password=..., database=...)
   ```
2. Update table/field names in `booking_engine.py` if they differ from the mock schema.
3. All business logic, intent detection, and frontend stays the same.

---

## Data schema (mirrors real tpgFlex)

| Table    | Key fields |
|----------|-----------|
| bookings | booking_id, status, passenger_status, user_id, pickup_id, dropoff_id, selected_pickup_time |
| stops    | stop_id, name, latitude, longitude, zone |
| users    | user_id, name, email, phone, preferred_language |
| vehicles | vehicle_id, status, capacity, current_latitude, current_longitude |
| locations | date, driver, latitude, longitude, bearing, accuracy |

---

## Tech stack

- **Backend:** FastAPI, Uvicorn, SQLite, httpx, faster-whisper
- **LLM:** Groq API (LLaMA 3.3-70B) with keyword-parser fallback
- **Frontend:** Vanilla HTML/CSS/JS, Leaflet (maps), Web Speech API (STT/TTS), TensorFlow.js + COCO-SSD (object detection for navigation)
- **Routing:** OSRM public API (pedestrian)
