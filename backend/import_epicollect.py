"""
Epicollect CSV importer for stop_observations.

Mirrors the live API sync (epicollect_sync.py) for offline CSV exports: it reads
the flat "Observations du lieu" multi-select, strips the bilingual
'French / English' labels down to the French side, and routes each item to its
scoring block via stop_evaluator.block_for_item (the single source of truth).
Legacy three-column exports (accessibility/safety/experience) still import — the
items are routed by dictionary membership regardless of which column holds them.

Usage:
    python backend/import_epicollect.py path/to/survey.csv

Expected CSV columns (case-insensitive, flexible naming):
  - stop_id  OR  stop_name                     (one required)
  - latitude, longitude                        (optional)
  - one or more observation columns            ("Observations du lieu", or the
    legacy accessibility/safety/experience columns). Multi-select values may be
    comma/semicolon-separated or a Python-list-literal string.
"""

import ast
import csv
import sys
import os
from datetime import datetime
from difflib import get_close_matches

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import get_conn
from backend import stop_evaluator as _se


# ── Column detection ───────────────────────────────────────────────────────────
# The current form is flat: one "Observations du lieu" multi-select (plus the
# retired "Retour d'expérience" field). We collect every observation column and
# route each item by weight-dict membership, so column naming no longer dictates
# the block. Legacy accessibility/safety/experience columns are picked up too.

_VALUE_NEEDLES = ("observation", "observ", "accessib", "safety", "securit",
                  "surete", "experience", "exprience", "retour", "feedback")
_META_NEEDLES  = ("uuid", "created", "uploaded", "title", "latitude", "longitude",
                  "lat", "lon", "photo")


def _norm(s: str) -> str:
    import unicodedata
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def detect_columns(headers: list[str]) -> dict:
    """
    Identify the stop-key column and every observation column.
    Returns: {"stop_key": colname, "value_cols": [colname, ...]}
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
            if any(x in n for x in ("stop", "arret", "arrt", "nom_de")):
                stop_key = h
                break

    # Observation columns — any field that looks like a survey answer.
    value_cols = [h for h, n in normed.items()
                  if h != stop_key and any(x in n for x in _VALUE_NEEDLES)]
    # Fallback: treat every non-meta column as an observation column.
    if not value_cols:
        value_cols = [h for h, n in normed.items()
                      if h != stop_key and not any(x in n for x in _META_NEEDLES)]

    return {"stop_key": stop_key, "value_cols": value_cols}


# ── Cell parser ────────────────────────────────────────────────────────────────

def parse_cell(cell_value) -> list[str]:
    """Split a multi-value survey cell into canonical French item labels.

    Handles the Epicollect bilingual multi-select format
    ("Surface dure et stable / Hard stable surface, Pente du chemin / Path slope"),
    Python-list-literal strings, and plain comma/semicolon lists. The English half
    (after ' / ') is dropped — the weight dicts key on the French side.
    """
    if cell_value is None:
        return []
    if isinstance(cell_value, list):
        seq = cell_value
    else:
        s = str(cell_value).strip()
        if not s:
            return []
        try:
            parsed = ast.literal_eval(s)            # "['a / A', ...]" → list
            seq = parsed if isinstance(parsed, list) else [s]
        except (ValueError, SyntaxError):
            seq = s.replace(";", ",").split(",")    # plain CSV fallback

    items: list[str] = []
    for raw in seq:
        item = str(raw).strip()
        if not item:
            continue
        item = item.split(" / ")[0].strip()         # drop the English half
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
    unmatched_vocab: set[str] = set()

    now = datetime.now().isoformat()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = detect_columns(headers)
        stop_key = mapping["stop_key"]
        value_cols = mapping["value_cols"]

        if not stop_key:
            return {
                "error": "Could not identify a stop_id or stop_name column.",
                "headers_found": headers,
            }

        conn = get_conn()
        try:
            for row in reader:
                rows_processed += 1
                raw_stop = (row.get(stop_key) or "").strip()
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

                for col in value_cols:
                    for item in parse_cell(row.get(col, "")):
                        block = _se.block_for_item(item)   # route by dict membership
                        if not block:
                            unmatched_vocab.add(item)       # not in any weight dict
                            continue
                        # Ride experience is network-wide (not tied to a stop).
                        target = _se.SERVICE_STOP_ID if block == "experience" else stop_id
                        conn.execute(
                            """INSERT INTO stop_observations
                               (stop_id, block_type, checked_item, source, submitted_at)
                               VALUES (?, ?, ?, 'epicollect', ?)""",
                            (target, block, item, now),
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
        "value_columns":   value_cols,
        "unmatched_vocabulary": sorted(unmatched_vocab),
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
    print(f"Value columns  : {result['value_columns']}")
    if result["stops_unmatched"]:
        print(f"Stops unmatched: {result['stops_unmatched']}")
    if result["unmatched_vocabulary"]:
        print(f"Unmatched vocab: {result['unmatched_vocabulary']}")
