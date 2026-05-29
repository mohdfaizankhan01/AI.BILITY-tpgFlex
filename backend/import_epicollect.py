"""
Epicollect CSV importer for stop_observations.

Usage:
    python backend/import_epicollect.py path/to/survey.csv

Expected CSV columns (case-insensitive, flexible naming):
  - stop_id  OR  stop_name       (one required)
  - latitude, longitude          (optional, used for coord-based stop lookup)
  - accessibility / safety / experience observations (comma- or semicolon-separated)
"""

import csv
import sys
import os
from datetime import datetime
from difflib import get_close_matches

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_conn


# ── Column detection ───────────────────────────────────────────────────────────

_BLOCK_ALIASES = {
    "accessibility": ["accessibility", "accessibility_obs", "1_accessibility",
                      "accessibilite", "accessibilité"],
    "safety":        ["safety", "safety_obs", "2_safety", "securite", "sécurité",
                      "surete", "sûreté"],
    "experience":    ["experience", "experience_obs", "3_experience", "expérience",
                      "ride_experience"],
}


def _norm(s: str) -> str:
    import unicodedata
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def detect_columns(headers: list[str]) -> dict:
    """
    Identify which CSV columns hold stop key and each observation block.
    Returns: {"stop_key": colname, "blocks": {"accessibility": col, ...}}
    """
    normed = {h: _norm(h) for h in headers}

    # Stop key
    stop_key = None
    for h, n in normed.items():
        if n in ("stop_id", "stopid", "id"):
            stop_key = h
            break
    if not stop_key:
        for h, n in normed.items():
            if "stop" in n and "name" in n:
                stop_key = h
                break
    if not stop_key:
        for h, n in normed.items():
            if "stop" in n or "arret" in n or "arrêt" in n:
                stop_key = h
                break

    # Block columns
    block_cols: dict[str, str | None] = {b: None for b in _BLOCK_ALIASES}
    for block, aliases in _BLOCK_ALIASES.items():
        for h, n in normed.items():
            if any(a in n for a in aliases):
                block_cols[block] = h
                break
        if not block_cols[block]:
            # fuzzy fallback
            matches = get_close_matches(block, list(normed.values()), n=1, cutoff=0.6)
            if matches:
                for h, n in normed.items():
                    if n == matches[0]:
                        block_cols[block] = h
                        break

    return {"stop_key": stop_key, "blocks": block_cols}


# ── Cell parser ────────────────────────────────────────────────────────────────

def parse_cell(cell_value: str) -> list[str]:
    """Split a multi-value cell on comma or semicolon, strip blanks."""
    if not cell_value or not cell_value.strip():
        return []
    items: list[str] = []
    for raw in cell_value.replace(";", ",").split(","):
        item = raw.strip()
        if item:
            items.append(item)
    return items


# ── Stop lookup helpers ────────────────────────────────────────────────────────

def _load_stops() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT stop_id, name FROM stops").fetchall()
    conn.close()
    return {r["stop_id"]: r["name"] for r in rows}


def _stop_id_by_name(name: str, stops: dict) -> str | None:
    names = list(stops.values())
    matches = get_close_matches(name, names, n=1, cutoff=0.4)
    if matches:
        for sid, sname in stops.items():
            if sname == matches[0]:
                return sid
    # substring fallback
    q = name.lower()
    for sid, sname in stops.items():
        if q in sname.lower() or sname.lower() in q:
            return sid
    return None


# ── Main importer ──────────────────────────────────────────────────────────────

def import_csv(csv_path: str) -> dict:
    stops = _load_stops()
    stop_ids_set = set(stops.keys())

    rows_processed = 0
    items_imported = 0
    stops_matched: set[str] = set()
    stops_unmatched: list[str] = []

    now = datetime.now().isoformat()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = detect_columns(headers)
        stop_key = mapping["stop_key"]
        block_cols = mapping["blocks"]

        if not stop_key:
            return {
                "error": "Could not identify a stop_id or stop_name column.",
                "headers_found": headers,
            }

        conn = get_conn()
        try:
            for row in reader:
                rows_processed += 1
                raw_stop = row.get(stop_key, "").strip()
                if not raw_stop:
                    continue

                # Resolve stop_id
                if raw_stop in stop_ids_set:
                    stop_id = raw_stop
                else:
                    stop_id = _stop_id_by_name(raw_stop, stops)

                if not stop_id:
                    stops_unmatched.append(raw_stop)
                    continue

                stops_matched.add(stop_id)

                for block, col in block_cols.items():
                    if not col:
                        continue
                    cell = row.get(col, "")
                    for item in parse_cell(cell):
                        conn.execute(
                            """INSERT INTO stop_observations
                               (stop_id, block_type, checked_item, source, submitted_at)
                               VALUES (?, ?, ?, 'epicollect', ?)""",
                            (stop_id, block, item, now),
                        )
                        items_imported += 1

            conn.commit()
        finally:
            conn.close()

    return {
        "rows_processed":  rows_processed,
        "items_imported":  items_imported,
        "stops_matched":   len(stops_matched),
        "stops_unmatched": list(set(stops_unmatched)),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/import_epicollect.py path/to/file.csv")
        sys.exit(1)

    result = import_csv(sys.argv[1])
    if "error" in result:
        print(f"Error: {result['error']}")
        if "headers_found" in result:
            print(f"Headers found: {result['headers_found']}")
        sys.exit(1)

    print(f"Rows processed : {result['rows_processed']}")
    print(f"Items imported : {result['items_imported']}")
    print(f"Stops matched  : {result['stops_matched']}")
    if result["stops_unmatched"]:
        print(f"Stops unmatched: {result['stops_unmatched']}")
