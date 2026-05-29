"""
Mock data seeder for tpgFlex hackathon demo.
Schema mirrors the real tpgFlex dataset (Bookings, Locations, Stops, Users, Vehicles).
On hackathon day: replace SQLite with MySQL and point to real data.
"""

import sqlite3
import random
from datetime import datetime, timedelta
import uuid

DB_PATH = "tpgflex.db"

# Real Geneva tpg stop names + coordinates
STOPS = [
    ("STOP_001", "Cornavin",              46.2100, 6.1422, "A"),
    ("STOP_002", "Carouge-Marché",        46.1833, 6.1400, "B"),
    ("STOP_003", "Palexpo",               46.2333, 6.1167, "C"),
    ("STOP_004", "Hôpital Cantonal",      46.1938, 6.1477, "A"),
    ("STOP_005", "CERN",                  46.2330, 6.0550, "C"),
    ("STOP_006", "Onex-Cité",             46.1833, 6.1050, "B"),
    ("STOP_007", "Lancy-Pont-Rouge",      46.1800, 6.1317, "B"),
    ("STOP_008", "Meyrin-Village",        46.2317, 6.0783, "C"),
    ("STOP_009", "Rive",                  46.2017, 6.1533, "A"),
    ("STOP_010", "Plainpalais",           46.1967, 6.1400, "A"),
    ("STOP_011", "Vernier-Village",       46.2133, 6.0883, "C"),
    ("STOP_012", "Bachet-de-Pesay",       46.1717, 6.1317, "B"),
    ("STOP_013", "Genève-Sécheron",       46.2217, 6.1383, "A"),
    ("STOP_014", "Nations",               46.2267, 6.1400, "A"),
    ("STOP_015", "Aïre",                  46.2050, 6.0933, "C"),
]

USERS = [
    ("USR_001", "Marie Dubois",    "marie.dubois@email.ch",    "+41791234567", "fr"),
    ("USR_002", "John Smith",      "john.smith@email.com",     "+41791234568", "en"),
    ("USR_003", "Ahmed Hassan",    "ahmed.h@email.com",        "+41791234569", "fr"),
    ("USR_004", "Lena Müller",     "lena.m@email.ch",          "+41791234570", "de"),
    ("USR_005", "Sophie Martin",   "sophie.m@email.fr",        "+41791234571", "fr"),
]

VEHICLES = [
    ("VEH_001", "available", 8,  46.2100, 6.1422, "A"),
    ("VEH_002", "available", 6,  46.1833, 6.1400, "B"),
    ("VEH_003", "in_service", 8, 46.2333, 6.1167, "C"),
    ("VEH_004", "available", 8,  46.1938, 6.1477, "A"),
    ("VEH_005", "available", 6,  46.2317, 6.0783, "C"),
    ("VEH_006", "in_service", 8, 46.2017, 6.1533, "A"),
    ("VEH_007", "available", 8,  46.1967, 6.1400, "A"),
    ("VEH_008", "maintenance", 8, 46.2133, 6.0883, "C"),
]


def create_tables(conn):
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS stops (
        stop_id         TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        latitude        REAL NOT NULL,
        longitude       REAL NOT NULL,
        zone            TEXT,
        territory_identifier TEXT DEFAULT 'geneva',
        is_active       INTEGER DEFAULT 1,
        created_at      TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id         TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        email           TEXT,
        phone           TEXT,
        preferred_language TEXT DEFAULT 'fr',
        referral_count  INTEGER DEFAULT 0,
        created_at      TEXT,
        last_booking_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        vehicle_id      TEXT PRIMARY KEY,
        status          TEXT,       -- available, in_service, maintenance
        capacity        INTEGER,
        current_latitude  REAL,
        current_longitude REAL,
        zone            TEXT,
        driver          TEXT,
        shift_start     TEXT,
        shift_end       TEXT
    )""")

    # Mirrors real Bookings table (54 fields → key subset for demo)
    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        booking_id          TEXT PRIMARY KEY,
        status              TEXT,           -- Validated, Cancelled by client, etc.
        passenger_status    TEXT,           -- Trip completed, Waiting, Cancelled
        created_at          TEXT,
        cancellation_time   TEXT,
        passengers          INTEGER,
        initial_price       REAL DEFAULT 0,
        price_vat_included  REAL DEFAULT 0,
        vat                 REAL DEFAULT 0,
        payment_mode        TEXT DEFAULT 'ZERO',
        discount_code       TEXT,
        referral            INTEGER DEFAULT 0,
        user_id             TEXT,
        origin_address      TEXT,
        destination_address TEXT,
        pickup_id           TEXT,
        pickup              TEXT,
        dropoff_id          TEXT,
        dropoff             TEXT,
        ride_id             TEXT,
        selected_pickup_time  TEXT,
        selected_dropoff_time TEXT,
        vehicle_id          TEXT,
        FOREIGN KEY (user_id)    REFERENCES users(user_id),
        FOREIGN KEY (pickup_id)  REFERENCES stops(stop_id),
        FOREIGN KEY (dropoff_id) REFERENCES stops(stop_id),
        FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
    )""")

    # Mirrors real Locations table (GPS pings)
    c.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        location_id         TEXT PRIMARY KEY,
        date                TEXT,
        driver              TEXT,
        latitude            REAL,
        longitude           REAL,
        accuracy            REAL,
        bearing             REAL,
        client              TEXT DEFAULT 'tpg',
        territory_identifier TEXT DEFAULT 'geneva',
        export_month        TEXT,
        vehicle_id          TEXT
    )""")

    conn.commit()


def seed_data(conn):
    c = conn.cursor()
    now = datetime.now()

    # Stops
    for s in STOPS:
        c.execute("""INSERT OR IGNORE INTO stops
            (stop_id, name, latitude, longitude, zone, created_at)
            VALUES (?,?,?,?,?,?)""",
            (*s, now.isoformat()))

    # Users
    for u in USERS:
        c.execute("""INSERT OR IGNORE INTO users
            (user_id, name, email, phone, preferred_language, created_at)
            VALUES (?,?,?,?,?,?)""",
            (*u, now.isoformat()))

    # Vehicles
    for v in VEHICLES:
        c.execute("""INSERT OR IGNORE INTO vehicles
            (vehicle_id, status, capacity, current_latitude, current_longitude, zone, driver)
            VALUES (?,?,?,?,?,?,?)""",
            (*v, f"Driver_{v[0]}"))

    # Historical bookings (last 30 days)
    statuses = ["Validated", "Cancelled by client", "Cancelled by driver"]
    pax_statuses = ["Trip completed", "Waiting", "Cancelled"]

    for i in range(60):
        booking_time = now - timedelta(days=random.randint(0, 30),
                                       hours=random.randint(6, 23))
        pickup_stop  = random.choice(STOPS)
        dropoff_stop = random.choice([s for s in STOPS if s[0] != pickup_stop[0]])
        user         = random.choice(USERS)
        vehicle      = random.choice([v for v in VEHICLES if v[1] == "available"])
        status       = random.choice(statuses)
        pax_status   = "Trip completed" if status == "Validated" else "Cancelled"
        pickup_time  = booking_time + timedelta(minutes=random.randint(5, 20))
        dropoff_time = pickup_time  + timedelta(minutes=random.randint(5, 30))

        c.execute("""INSERT OR IGNORE INTO bookings
            (booking_id, status, passenger_status, created_at, passengers,
             user_id, origin_address, destination_address,
             pickup_id, pickup, dropoff_id, dropoff,
             selected_pickup_time, selected_dropoff_time, vehicle_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            str(uuid.uuid4())[:8],
            status, pax_status, booking_time.isoformat(),
            random.randint(1, 4),
            user[0],
            f"Near {pickup_stop[1]}, Geneva",
            f"Near {dropoff_stop[1]}, Geneva",
            pickup_stop[0], pickup_stop[1],
            dropoff_stop[0], dropoff_stop[1],
            pickup_time.isoformat(),
            dropoff_time.isoformat(),
            vehicle[0]
        ))

    # GPS location pings for vehicles
    for v in VEHICLES:
        for _ in range(10):
            ping_time = now - timedelta(minutes=random.randint(1, 120))
            c.execute("""INSERT INTO locations
                (location_id, date, driver, latitude, longitude,
                 accuracy, bearing, export_month, vehicle_id)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                str(uuid.uuid4())[:8],
                ping_time.isoformat(),
                f"Driver_{v[0]}",
                v[3] + random.uniform(-0.005, 0.005),
                v[4] + random.uniform(-0.005, 0.005),
                random.uniform(3, 10),
                random.uniform(0, 360),
                now.strftime("%Y-%m"),
                v[0]
            ))

    conn.commit()
    print("✅ Mock data seeded successfully.")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    seed_data(conn)
    conn.close()
    return DB_PATH


if __name__ == "__main__":
    init_db()
