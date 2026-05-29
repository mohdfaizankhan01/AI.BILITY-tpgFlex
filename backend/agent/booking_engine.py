"""
Booking engine: handles the business logic after intent is known.
- Find nearest stop to a place name (fuzzy match on stop names)
- Assign an available vehicle
- Create booking in DB
"""

import math
import uuid
from datetime import datetime, timedelta
from difflib import get_close_matches
from backend.database import get_conn


def haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in km between two GPS points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_all_stops() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM stops WHERE is_active = 1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_stop_by_name(query: str) -> dict | None:
    """Fuzzy match a place name to a stop."""
    stops = get_all_stops()
    names = [s["name"] for s in stops]
    matches = get_close_matches(query, names, n=1, cutoff=0.3)
    if matches:
        return next(s for s in stops if s["name"] == matches[0])
    # Substring fallback
    q = query.lower()
    for s in stops:
        if q in s["name"].lower() or s["name"].lower() in q:
            return s
    return None


def nearest_stop_to_coords(lat: float, lon: float) -> dict | None:
    stops = get_all_stops()
    if not stops:
        return None
    return min(stops, key=lambda s: haversine(lat, lon, s["latitude"], s["longitude"]))


def assign_vehicle(zone: str | None = None) -> dict | None:
    conn = get_conn()
    query = "SELECT * FROM vehicles WHERE status = 'available'"
    params = []
    if zone:
        query += " AND zone = ?"
        params.append(zone)
    query += " LIMIT 1"
    row = conn.execute(query, params).fetchone()

    if not row and not zone:
        # All vehicles are busy — recycle in_service vehicles back to available
        conn.execute("UPDATE vehicles SET status = 'available' WHERE status = 'in_service'")
        conn.commit()
        row = conn.execute(query, params).fetchone()

    conn.close()
    return dict(row) if row else None


def create_booking(user_id: str, pickup_stop: dict, dropoff_stop: dict,
                   passengers: int, pickup_time: str, vehicle: dict) -> dict:
    conn = get_conn()
    booking_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now().isoformat()
    dropoff_time = (datetime.fromisoformat(pickup_time) +
                    timedelta(minutes=15)).isoformat()

    conn.execute("""
        INSERT INTO bookings
        (booking_id, status, passenger_status, created_at, passengers,
         user_id, origin_address, destination_address,
         pickup_id, pickup, dropoff_id, dropoff,
         selected_pickup_time, selected_dropoff_time, vehicle_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        booking_id, "Validated", "Waiting", now, passengers,
        user_id,
        f"Near {pickup_stop['name']}, Geneva",
        f"Near {dropoff_stop['name']}, Geneva",
        pickup_stop["stop_id"], pickup_stop["name"],
        dropoff_stop["stop_id"], dropoff_stop["name"],
        pickup_time, dropoff_time,
        vehicle["vehicle_id"]
    ))

    # Mark vehicle as in_service
    conn.execute("UPDATE vehicles SET status = 'in_service' WHERE vehicle_id = ?",
                 (vehicle["vehicle_id"],))
    conn.commit()
    conn.close()

    return {
        "booking_id": booking_id,
        "pickup":     pickup_stop["name"],
        "dropoff":    dropoff_stop["name"],
        "pickup_time": pickup_time,
        "dropoff_time": dropoff_time,
        "vehicle_id": vehicle["vehicle_id"],
        "passengers": passengers,
        "status":     "Validated"
    }


def get_user_history(user_id: str, limit: int = 3) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM bookings WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
