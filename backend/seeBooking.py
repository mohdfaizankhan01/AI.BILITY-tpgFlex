import sqlite3
import os

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "mock_data", "tpgflex.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

rows = cursor.execute("SELECT * FROM bookings").fetchall()

for row in rows:
    print(row)

conn.close()