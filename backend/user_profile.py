"""
User profile module — stores accessibility preferences in user_profiles table.
Single source of truth for all personalization across the app.
"""

import json
from datetime import datetime
from backend.database import get_conn

# ── Profile definitions ────────────────────────────────────────────────────────

PROFILES = {
    "standard": {
        "label": "Standard user",
        "icon": "👤",
        "scoring_profile": "all",
        "ui_mode": "default",
        "defaults": {}
    },
    "wheelchair": {
        "label": "Wheelchair / mobility",
        "icon": "♿",
        "scoring_profile": "wheelchair",
        "ui_mode": "default",
        "defaults": {
            "max_walking_distance": 200,
            "auto_announce_stops": 1
        }
    },
    "blind": {
        "label": "Blind / low vision",
        "icon": "🦯",
        "scoring_profile": "blind",
        "ui_mode": "voice_first",
        "defaults": {
            "audio_feedback": 1,
            "haptic_feedback": 1,
            "visual_feedback": 0,
            "large_text": 1,
            "auto_announce_stops": 1,
            "voice_speed": 1.1
        }
    },
    "deaf": {
        "label": "Deaf / hard of hearing",
        "icon": "🧏",
        "scoring_profile": "deaf",
        "ui_mode": "visual_first",
        "defaults": {
            "audio_feedback": 0,
            "haptic_feedback": 1,
            "visual_feedback": 1,
            "large_text": 1
        }
    },
    "low_digital": {
        "label": "Low digital literacy",
        "icon": "📖",
        "scoring_profile": "low_digital",
        "ui_mode": "simplified",
        "defaults": {
            "large_text": 1,
            "auto_announce_stops": 1,
            "voice_speed": 0.9
        }
    },
    "elderly": {
        "label": "Elderly",
        "icon": "🧓",
        "scoring_profile": "elderly",
        "ui_mode": "simplified",
        "defaults": {
            "large_text": 1,
            "voice_speed": 0.85,
            "max_walking_distance": 300,
            "haptic_feedback": 1
        }
    }
}

# ── Table bootstrap ────────────────────────────────────────────────────────────

def _bootstrap():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id              TEXT PRIMARY KEY,
            display_name         TEXT,
            accessibility_profile TEXT DEFAULT 'standard',
            secondary_needs      TEXT,
            preferred_language   TEXT DEFAULT 'fr',
            voice_speed          REAL DEFAULT 1.0,
            high_contrast        INTEGER DEFAULT 0,
            large_text           INTEGER DEFAULT 0,
            haptic_feedback      INTEGER DEFAULT 1,
            audio_feedback       INTEGER DEFAULT 1,
            visual_feedback      INTEGER DEFAULT 1,
            auto_announce_stops  INTEGER DEFAULT 0,
            step_length_metres   REAL DEFAULT 0.75,
            max_walking_distance INTEGER DEFAULT 500,
            emergency_contact    TEXT,
            created_at           TEXT,
            updated_at           TEXT
        )
    """)
    conn.commit()
    conn.close()

_bootstrap()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    d["secondary_needs"] = json.loads(d.get("secondary_needs") or "[]")
    return d


# ── CRUD ───────────────────────────────────────────────────────────────────────

def get_profile(user_id: str) -> dict:
    """Return the user's profile, creating a default one if it doesn't exist yet."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return create_profile(user_id, "standard")
    return _row_to_dict(row)


def create_profile(user_id: str, profile_type: str = "standard", **kwargs) -> dict:
    """Insert a new profile, applying profile-type defaults (overridable via kwargs)."""
    if profile_type not in PROFILES:
        profile_type = "standard"
    pdef = PROFILES[profile_type]
    data = {
        "preferred_language": "fr",
        "voice_speed": 1.0,
        "high_contrast": 0,
        "large_text": 0,
        "haptic_feedback": 1,
        "audio_feedback": 1,
        "visual_feedback": 1,
        "auto_announce_stops": 0,
        "step_length_metres": 0.75,
        "max_walking_distance": 500,
    }
    data.update(pdef["defaults"])          # apply profile defaults
    data.update({k: v for k, v in kwargs.items() if v is not None})

    now = datetime.now().isoformat()
    secondary_needs = json.dumps(data.pop("secondary_needs", []))

    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO user_profiles
            (user_id, accessibility_profile, display_name, secondary_needs,
             preferred_language, voice_speed, high_contrast, large_text,
             haptic_feedback, audio_feedback, visual_feedback, auto_announce_stops,
             step_length_metres, max_walking_distance, emergency_contact,
             created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, profile_type,
        data.get("display_name"),
        secondary_needs,
        data.get("preferred_language", "fr"),
        data.get("voice_speed", 1.0),
        int(data.get("high_contrast", 0)),
        int(data.get("large_text", 0)),
        int(data.get("haptic_feedback", 1)),
        int(data.get("audio_feedback", 1)),
        int(data.get("visual_feedback", 1)),
        int(data.get("auto_announce_stops", 0)),
        float(data.get("step_length_metres", 0.75)),
        int(data.get("max_walking_distance", 500)),
        data.get("emergency_contact"),
        now, now,
    ))
    conn.commit()
    conn.close()
    return get_profile(user_id)


def update_profile(user_id: str, updates: dict) -> dict:
    """Partial update. If accessibility_profile changes, apply that profile's defaults first."""
    if not updates:
        return get_profile(user_id)

    # Changing profile type → apply its defaults, but explicit updates win
    if "accessibility_profile" in updates:
        new_type = updates["accessibility_profile"]
        if new_type in PROFILES:
            for k, v in PROFILES[new_type]["defaults"].items():
                if k not in updates:
                    updates[k] = v

    # Serialize secondary_needs list → JSON string
    if "secondary_needs" in updates and isinstance(updates["secondary_needs"], list):
        updates["secondary_needs"] = json.dumps(updates["secondary_needs"])

    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]

    conn = get_conn()
    # Ensure row exists before updating
    exists = conn.execute(
        "SELECT 1 FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not exists:
        conn.close()
        profile_type = updates.get("accessibility_profile", "standard")
        return create_profile(user_id, profile_type, **{
            k: v for k, v in updates.items() if k not in ("accessibility_profile", "updated_at")
        })

    conn.execute(f"UPDATE user_profiles SET {set_clause} WHERE user_id = ?", values)
    conn.commit()
    conn.close()
    return get_profile(user_id)


def get_scoring_profile(user_id: str) -> str:
    """Return the stop_evaluator profile key for this user."""
    prof = get_profile(user_id)
    ap = prof.get("accessibility_profile", "standard")
    return PROFILES.get(ap, PROFILES["standard"])["scoring_profile"]


def get_ui_preferences(user_id: str) -> dict:
    """All UI-relevant fields consumed by profile_manager.js."""
    prof = get_profile(user_id)
    ap = prof.get("accessibility_profile", "standard")
    pdef = PROFILES.get(ap, PROFILES["standard"])
    return {
        "ui_mode":              pdef["ui_mode"],
        "audio_feedback":       bool(prof.get("audio_feedback", 1)),
        "haptic_feedback":      bool(prof.get("haptic_feedback", 1)),
        "visual_feedback":      bool(prof.get("visual_feedback", 1)),
        "high_contrast":        bool(prof.get("high_contrast", 0)),
        "large_text":           bool(prof.get("large_text", 0)),
        "voice_speed":          float(prof.get("voice_speed", 1.0)),
        "auto_announce_stops":  bool(prof.get("auto_announce_stops", 0)),
        "preferred_language":   prof.get("preferred_language", "fr"),
        "icon":                 pdef["icon"],
        "label":                pdef["label"],
        "max_walking_distance": int(prof.get("max_walking_distance", 500)),
        "step_length_metres":   float(prof.get("step_length_metres", 0.75)),
        "scoring_profile":      pdef["scoring_profile"],
        "accessibility_profile": ap,
    }


def delete_profile(user_id: str) -> bool:
    conn = get_conn()
    conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
    affected = conn.total_changes
    conn.commit()
    conn.close()
    return affected > 0
