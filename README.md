# tpgFlex AI Voice Booking Assistant

AI-powered voice booking system for tpgFlex Geneva on-demand service.

## Setup (2 minutes)

```bash
bash setup.sh
```

Then in two terminals:

```bash
# Terminal 1 – backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 – frontend (just open the file)
open frontend/index.html
```

## Try it

Say or type:
- *"Book a ride to Cornavin"*
- *"I need to get to the hospital at 9am"*
- *"Take me to CERN for 2 passengers"*
- *"What's the nearest stop to Plainpalais?"*

## Project structure

```
tpgflex-voice/
├── backend/
│   ├── main.py              ← FastAPI – all routes
│   ├── database.py          ← SQLite connection
│   ├── agent/
│   │   ├── intent.py        ← Claude API intent detection
│   │   └── booking_engine.py← Stop matching + booking logic
│   └── mock_data/
│       ├── seed.py          ← Creates + seeds tpgflex.db
│       └── tpgflex.db       ← Generated on first run
├── frontend/
│   └── index.html           ← Full UI (voice + map + TTS)
├── requirements.txt
└── setup.sh
```

## On hackathon day – switching to real data

1. Replace `backend/database.py` with MySQL connector:
   ```python
   import mysql.connector
   def get_conn():
       return mysql.connector.connect(host=..., user=..., password=..., database=...)
   ```
2. Update table/field names in `booking_engine.py` if they differ from mock schema.
3. Done — all business logic stays the same.

## Data schema (mirrors real tpgFlex)

| Table    | Key fields |
|----------|-----------|
| bookings | booking_id, status, passenger_status, user_id, pickup_id, dropoff_id, selected_pickup_time |
| stops    | stop_id, name, latitude, longitude, zone |
| users    | user_id, name, email, phone, preferred_language |
| vehicles | vehicle_id, status, capacity, current_latitude, current_longitude |
| locations| date, driver, latitude, longitude, bearing, accuracy |
