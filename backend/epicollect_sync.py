"""
Epicollect5 → stop_observations sync.

Pulls survey entries straight from the Epicollect5 REST API and refreshes the
`stop_observations` rows that came from Epicollect, so stop scores update
automatically (evaluate_stop() reads the table live — there is no model to retrain).

Design notes
------------
- **Idempotent full-refresh of source='epicollect'.** Each sync deletes the
  previous Epicollect-sourced rows and re-inserts from the current export. This
  correctly reflects edited *and* deleted survey entries, and never duplicates.
- **Demo / manual rows are preserved** — only rows with source='epicollect' are
  touched, so the seeded demo data and any /observations inserts survive.
- **Public or private projects.** Public projects need no auth. Private projects
  use OAuth2 client-credentials (set EPICOLLECT_CLIENT_ID / _CLIENT_SECRET).

Config (environment variables)
------------------------------
  EPICOLLECT_PROJECT_SLUG     project slug (default "crowdsense")
  EPICOLLECT_BASE             API base    (default "https://five.epicollect.net")
  EPICOLLECT_CLIENT_ID        OAuth2 client id      (private projects only)
  EPICOLLECT_CLIENT_SECRET    OAuth2 client secret  (private projects only)
  EPICOLLECT_FORM_REF         specific form ref     (optional, multi-form projects)
  EPICOLLECT_AUTO_SYNC        "1" to enable the background poller (default off)
  EPICOLLECT_SYNC_INTERVAL_MIN  poll interval in minutes (default 60)

CLI
---
  python -m backend.epicollect_sync            # sync from the live API
  python -m backend.epicollect_sync --dry-run  # fetch + map, print summary, no DB write
"""

import os
import sys
import uuid
import asyncio
from datetime import datetime

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ast
from difflib import get_close_matches

from backend.database import get_conn
from backend.import_epicollect import _norm, _load_stops
from backend import stop_evaluator as _se

# ── Config ──────────────────────────────────────────────────────────────────────

BASE          = os.getenv("EPICOLLECT_BASE", "https://five.epicollect.net").rstrip("/")
PROJECT_SLUG  = os.getenv("EPICOLLECT_PROJECT_SLUG", "crowdsense")
CLIENT_ID     = os.getenv("EPICOLLECT_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("EPICOLLECT_CLIENT_SECRET", "")
FORM_REF      = os.getenv("EPICOLLECT_FORM_REF", "")
AUTO_SYNC     = os.getenv("EPICOLLECT_AUTO_SYNC", "0") == "1"
INTERVAL_MIN  = int(os.getenv("EPICOLLECT_SYNC_INTERVAL_MIN", "60"))
AUTO_CREATE_STOPS = os.getenv("EPICOLLECT_AUTO_CREATE_STOPS", "1") == "1"
GEOCODE_REGION    = os.getenv("EPICOLLECT_GEOCODE_REGION", "Geneva, Switzerland")
GENEVA_FALLBACK   = (46.2044, 6.1432)   # used when geocoding finds nothing


# ── Schema: add entry_uuid for traceability (safe, idempotent) ──────────────────

def _ensure_uuid_column():
    conn = get_conn()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(stop_observations)").fetchall()]
    if "entry_uuid" not in cols:
        try:
            conn.execute("ALTER TABLE stop_observations ADD COLUMN entry_uuid TEXT")
            conn.commit()
        except Exception:
            pass
    conn.close()


# ── API: auth + fetch ───────────────────────────────────────────────────────────

async def _get_access_token(client: httpx.AsyncClient) -> str | None:
    """OAuth2 client-credentials token, or None for public projects."""
    if not (CLIENT_ID and CLIENT_SECRET):
        return None
    r = await client.post(
        f"{BASE}/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20.0,
    )
    r.raise_for_status()
    return r.json().get("access_token")


async def fetch_entries() -> list[dict]:
    """Fetch all entries (handles pagination + optional OAuth2)."""
    entries: list[dict] = []
    async with httpx.AsyncClient() as client:
        token = await _get_access_token(client)
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        page = 1
        while True:
            params = {"per_page": 100, "page": page}
            if FORM_REF:
                params["form_ref"] = FORM_REF
            r = await client.get(
                f"{BASE}/api/export/entries/{PROJECT_SLUG}",
                params=params, headers=headers, timeout=30.0,
            )
            r.raise_for_status()
            payload = r.json()

            batch = (payload.get("data") or {}).get("entries") or []
            entries.extend(batch)

            meta = payload.get("meta") or {}
            last = meta.get("last_page") or 1
            if page >= last or not batch:
                break
            page += 1
    return entries


# ── Value parsing (real Epicollect format) ──────────────────────────────────────

def parse_epicollect_value(raw) -> list[str]:
    """
    The crowdsense form stores multi-select answers as a JSON array of bilingual
    strings: ['Surface dure et stable / Hard stable surface', '', ...].
    Return the French side of each non-empty item (the side the weight dicts use).
    """
    items: list[str] = []
    if raw is None:
        return items
    if isinstance(raw, list):
        seq = raw
    else:
        s = str(raw).strip()
        if not s:
            return items
        try:
            parsed = ast.literal_eval(s)          # "['a / A', ...]" → list
            seq = parsed if isinstance(parsed, list) else [s]
        except (ValueError, SyntaxError):
            seq = s.replace(";", ",").split(",")  # plain CSV fallback
    for raw_item in seq:
        item = str(raw_item).strip()
        if not item:
            continue
        item = item.split(" / ")[0].strip()       # drop the English half
        if item:
            items.append(item)
    return items


# ── Block routing via the model's own weight dictionaries ───────────────────────
# stop_evaluator.block_for_item is the single source of truth — it routes each
# observed item to the block whose weight dict contains it (shared with the CSV
# importer so the mapping can never drift between the two ingest paths).

def _route_item(item: str) -> str | None:
    return _se.block_for_item(item)


def _find_field(keys: list[str], *needles: str) -> str | None:
    for k in keys:
        n = _norm(k)
        if any(needle in n for needle in needles):
            return k
    return None


def _detect_fields(keys: list[str]) -> tuple[str | None, list[str]]:
    """Return (stop_field, [value_fields]) for a crowdsense entry's keys."""
    stop_key = _find_field(keys, "stop", "arret", "arrt", "nom_de")
    value_keys = [k for k in (
        _find_field(keys, "observation", "observ"),
        _find_field(keys, "experience", "exprience", "retour", "feedback"),
    ) if k]
    if not value_keys:
        meta = {"ec5_uuid", "uuid", "created_at", "uploaded_at", "title"}
        value_keys = [k for k in keys if _norm(k) not in meta and "photo" not in _norm(k)]
    return stop_key, value_keys


def _strict_stop_match(name: str, stops: dict) -> str | None:
    """High-confidence stop match only — refuses loose token coincidences that
    would attach a survey to the wrong stop (e.g. '… Village' → '… -Village')."""
    target = _norm(name)
    norm_to_id = {_norm(v): k for k, v in stops.items()}
    if target in norm_to_id:                       # exact (accent/case-insensitive)
        return norm_to_id[target]
    m = get_close_matches(target, list(norm_to_id), n=1, cutoff=0.85)
    return norm_to_id[m[0]] if m else None


# ── Mapping: entry dict → (stop_id, block, items) ───────────────────────────────

def _is_feedback_field(key: str) -> bool:
    """True for the 'Retour d'expérience' ride-feedback field (network-wide)."""
    n = _norm(key)
    return any(x in n for x in ("retour", "feedback", "exprience", "experience"))


def map_entries(entries: list[dict]) -> tuple[list[tuple], dict]:
    """
    Map raw Epicollect entries to observation rows
    (stop_id, block_type, checked_item, entry_uuid).
    Place observations are attached to their stop; ride-experience feedback (the
    "Évaluer un trajet" contribution type, which carries no stop) is attached to
    the network-wide SERVICE bucket. Values matching no block are reported under
    'unmatched_vocabulary'.
    """
    rows: list[tuple] = []
    matched_stops: set[str] = set()
    unmatched_stops: set[str] = set()
    unmatched_vocab: set[str] = set()
    service_feedback = 0

    if not entries:
        return rows, {"entries": 0, "stops_matched": 0, "stops_unmatched": []}

    stops = _load_stops()
    stop_ids = set(stops.keys())
    keys = list(entries[0].keys())

    stop_key, value_keys = _detect_fields(keys)

    if not stop_key:
        return rows, {"error": "Could not find a stop-name field in the Epicollect form",
                      "fields_seen": keys}

    for e in entries:
        raw_stop = str(e.get(stop_key, "")).strip()
        stop_id = (raw_stop if raw_stop in stop_ids
                   else _strict_stop_match(raw_stop, stops)) if raw_stop else None

        uuid = e.get("ec5_uuid") or e.get("uuid")
        for vk in value_keys:
            is_feedback = _is_feedback_field(vk)
            for item in parse_epicollect_value(e.get(vk)):
                block = _route_item(item)
                if not block:
                    unmatched_vocab.add(item)
                    continue
                if is_feedback:
                    # Ride experience is network-wide — no stop required.
                    rows.append((_se.SERVICE_STOP_ID, block, item, uuid))
                    service_feedback += 1
                elif stop_id:
                    rows.append((stop_id, block, item, uuid))
                    matched_stops.add(stop_id)
                elif raw_stop:
                    unmatched_stops.add(raw_stop)

    return rows, {
        "entries": len(entries),
        "stop_field": stop_key,
        "value_fields": value_keys,
        "stops_matched": len(matched_stops),
        "stops_unmatched": sorted(unmatched_stops),
        "observations_mapped": len(rows),
        "ride_feedback_items": service_feedback,
        "unmatched_vocabulary": sorted(unmatched_vocab),
    }


# ── Auto-create stops (geocoded via OpenStreetMap) ──────────────────────────────

async def _geocode(client: httpx.AsyncClient, name: str) -> tuple[float, float]:
    """Resolve a stop name to (lat, lon) via OSM Nominatim; Geneva centre on miss."""
    try:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{name}, {GEOCODE_REGION}", "format": "json", "limit": 1},
            headers={"User-Agent": "tpgFlex-StopEvaluator/1.0 (accessibility survey sync)"},
            timeout=20.0,
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return GENEVA_FALLBACK


async def ensure_survey_stops(entries: list[dict]) -> dict:
    """Insert any unknown survey stop into the stops table (geocoded). Idempotent."""
    if not entries:
        return {"created": 0, "names": []}
    stop_key, _ = _detect_fields(list(entries[0].keys()))
    if not stop_key:
        return {"created": 0, "names": []}

    stops = _load_stops()
    # Unique, not-yet-known names (preserve first-seen order)
    pending: list[str] = []
    seen: set[str] = set()
    for e in entries:
        nm = str(e.get(stop_key, "")).strip()
        if not nm or _norm(nm) in seen:
            continue
        seen.add(_norm(nm))
        if nm in stops or _strict_stop_match(nm, stops):
            continue
        pending.append(nm)

    if not pending:
        return {"created": 0, "names": []}

    created: list[str] = []
    now = datetime.now().isoformat()
    async with httpx.AsyncClient() as client:
        conn = get_conn()
        try:
            for nm in pending:
                lat, lon = await _geocode(client, nm)
                stop_id = "STOP_EC5_" + uuid.uuid4().hex[:6].upper()
                conn.execute(
                    """INSERT INTO stops
                       (stop_id, name, latitude, longitude, zone,
                        territory_identifier, is_active, created_at)
                       VALUES (?,?,?,?, 'survey', 'geneva', 1, ?)""",
                    (stop_id, nm, lat, lon, now),
                )
                created.append(nm)
                await asyncio.sleep(1.0)   # respect Nominatim's 1 req/sec policy
            conn.commit()
        finally:
            conn.close()
    return {"created": len(created), "names": created}


# ── Apply: refresh source='epicollect' rows ─────────────────────────────────────

def apply_rows(rows: list[tuple]) -> int:
    """Replace all source='epicollect' observations with the given rows."""
    _ensure_uuid_column()
    now = datetime.now().isoformat()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM stop_observations WHERE source = 'epicollect'")
        conn.executemany(
            """INSERT INTO stop_observations
               (stop_id, block_type, checked_item, source, submitted_at, entry_uuid)
               VALUES (?, ?, ?, 'epicollect', ?, ?)""",
            [(sid, blk, item, now, uuid) for (sid, blk, item, uuid) in rows],
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


# ── Orchestration ───────────────────────────────────────────────────────────────

async def sync(dry_run: bool = False) -> dict:
    """Fetch from the API, map, and (unless dry_run) refresh the table."""
    try:
        entries = await fetch_entries()
    except httpx.HTTPStatusError as ex:
        return {"ok": False, "error": f"Epicollect API returned {ex.response.status_code}",
                "hint": "Check EPICOLLECT_PROJECT_SLUG, and set client id/secret if the project is private."}
    except Exception as ex:
        return {"ok": False, "error": f"{type(ex).__name__}: {ex}"}

    # Auto-create any unknown survey stops (geocoded) before mapping.
    if AUTO_CREATE_STOPS and not dry_run:
        try:
            created = await ensure_survey_stops(entries)
            summary_created = created
        except Exception as ex:
            summary_created = {"created": 0, "error": f"{type(ex).__name__}: {ex}"}
    else:
        summary_created = {"created": 0, "skipped": dry_run or not AUTO_CREATE_STOPS}

    rows, summary = map_entries(entries)
    if "error" in summary:
        return {"ok": False, **summary}

    summary["stops_created"] = summary_created

    if not dry_run:
        written = apply_rows(rows)
        summary["observations_written"] = written
    summary["ok"] = True
    summary["dry_run"] = dry_run
    summary["synced_at"] = datetime.now().isoformat()
    summary["project_slug"] = PROJECT_SLUG
    return summary


# ── Background poller (opt-in via EPICOLLECT_AUTO_SYNC=1) ────────────────────────

async def _poller():
    while True:
        try:
            result = await sync()
            print(f"[epicollect_sync] {result}")
        except Exception as ex:
            print(f"[epicollect_sync] poll failed: {ex}")
        await asyncio.sleep(INTERVAL_MIN * 60)


def start_background_sync():
    """Call from a FastAPI startup handler. No-op unless EPICOLLECT_AUTO_SYNC=1."""
    if not AUTO_SYNC:
        return
    asyncio.create_task(_poller())
    print(f"[epicollect_sync] auto-sync ON — every {INTERVAL_MIN} min, project '{PROJECT_SLUG}'")


# ── CLI ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    out = asyncio.run(sync(dry_run=dry))
    print(out)
    sys.exit(0 if out.get("ok") else 1)
