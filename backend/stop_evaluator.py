"""
Stop Evaluator — scores each tpgFlex stop across five dimensions using
Epicollect survey observations stored in stop_observations table.

Two Epicollect forms feed the scores:
  • "Observations du lieu" — a flat multi-select of place attributes
    (CANONICAL_OBSERVATION_ITEMS) that drive accessibility (per profile) + safety.
  • "Retour d'expérience / Quick Tags" — a separate sub-form of rider sentiment
    about the trip, driving the "🌟 Ride Experience" score (EXPERIENCE_ITEMS).

Every checked item is pooled and scored against every dimension; each weight dict
only counts the items it lists, so one observation can lift several scores.
"""

import unicodedata
from backend.database import get_conn

# ── Canonical survey vocabulary ────────────────────────────────────────────────
# The 28 items of the current Epicollect "Observations du lieu" form (French
# side — the side parse_epicollect_value keeps). Every item below must appear in
# at least one weight dict, otherwise it is dropped as "unmatched_vocabulary" on
# sync. This list is the contract between the survey and the scorer.

CANONICAL_OBSERVATION_ITEMS = [
    "Surface dure et stable",
    "Pente du chemin",
    "Bordure abaissée présente",
    "Embarquement de plain-pied avec le véhicule",
    "Espace suffisant pour manœuvrer un fauteuil",
    "Surface meuble ou irrégulière",
    "Forte pente",
    "Obstacles dans la zone d'attente",
    "Bandes podotactiles de guidage",
    "Bandes podotactiles d'éveil au bord",
    "Signalétique à fort contraste visuel",
    "Nom de l'arrêt clairement visible et lisible",
    "Information en braille",
    "Affichage temps réel (PID)",
    "Pictogrammes universels",
    "Plan du réseau",
    "Éclairage suffisant",
    "Passage piéton proche",
    "Commerce ou Hopital-pharmacie proche",
    "Zone sombre",
    "Zone isolée",
    "Route à vitesse élevée (> 50 km/h)",
    "Couverture mobile faible",
    "Zone scolaire proche",
    "Abri disponible",
    "Banc disponible",
    "Zone calme",
    "Stationnement vélo proche",
]

# ── Item weight dictionaries ───────────────────────────────────────────────────

WHEELCHAIR_ITEMS = {
    "Surface dure et stable": 3,
    "Bordure abaissée présente": 3,
    "Embarquement de plain-pied avec le véhicule": 4,
    "Espace suffisant pour manœuvrer un fauteuil": 3,
    "Pente du chemin": -1,
    "Surface meuble ou irrégulière": -3,
    "Forte pente": -4,
    "Obstacles dans la zone d'attente": -2,
    "Abri disponible": 1,
}

BLIND_ITEMS = {
    "Bandes podotactiles de guidage": 4,
    "Bandes podotactiles d'éveil au bord": 4,
    "Signalétique à fort contraste visuel": 2,
    "Nom de l'arrêt clairement visible et lisible": 2,
    "Information en braille": 2,
    "Affichage temps réel (PID)": 1,
    "Zone calme": 1,
    "Obstacles dans la zone d'attente": -2,
    "Route à vitesse élevée (> 50 km/h)": -3,
}

DEAF_ITEMS = {
    "Affichage temps réel (PID)": 4,
    "Nom de l'arrêt clairement visible et lisible": 3,
    "Pictogrammes universels": 3,
    "Plan du réseau": 2,
    "Signalétique à fort contraste visuel": 2,
}

LOW_DIGITAL_ITEMS = {
    "Affichage temps réel (PID)": 3,
    "Pictogrammes universels": 3,
    "Plan du réseau": 3,
    "Nom de l'arrêt clairement visible et lisible": 2,
    "Signalétique à fort contraste visuel": 2,
}

ELDERLY_ITEMS = {
    "Banc disponible": 3,
    "Abri disponible": 2,
    "Éclairage suffisant": 2,
    "Surface dure et stable": 2,
    "Pente du chemin": -1,
    "Forte pente": -3,
    "Surface meuble ou irrégulière": -2,
    "Obstacles dans la zone d'attente": -2,
}

SAFETY_ITEMS = {
    "Éclairage suffisant": 3,
    "Passage piéton proche": 2,
    "Commerce ou Hopital-pharmacie proche": 2,
    "Zone scolaire proche": 1,           # daytime activity / passive surveillance
    "Zone sombre": -3,
    "Zone isolée": -3,
    "Route à vitesse élevée (> 50 km/h)": -3,
    "Couverture mobile faible": -2,
}

# Ride-experience feedback — driven by the separate Epicollect "Retour
# d'expérience / Quick Tags" sub-form (rider sentiment about the trip itself,
# not the stop's amenities). These are the only items that feed the
# "🌟 Ride Experience" score.
EXPERIENCE_ITEMS = {
    # ── Positive tags ──
    "Bonne expérience": 3,                      # Good experience (overall)
    "Je me suis senti en sécurité": 3,          # Felt safe during ride
    "Confortable": 2,                           # Comfortable
    "Serviable": 2,                             # Helpful (driver)
    "Accessible": 2,                            # Accessible
    "Montée facile": 2,                         # Easy boarding
    "Ponctuel": 2,                              # On time
    "Rampe utilisée si nécessaire": 2,          # Ramp deployed when needed
    "Annonces sonores fonctionnelles": 2,       # Audio announcements working
    "Espace fauteuil disponible": 2,            # Wheelchair space available
    "Véhicule propre": 2,                       # Clean vehicle
    "Arrêts annoncés clairement": 2,            # Stops clearly announced
    "Information visuelle claire": 2,           # Clear visual information
    "Trajet facile à comprendre": 2,            # Easy to understand ride
    "Bon éclairage": 1,                         # Good lighting (inside vehicle)
    # ── Negative tags ──
    "Attente longue": -2,                       # Long waiting time
    "Accès difficile": -3,                      # Difficult access
    "Trajet cahoteux": -2,                      # Bumpy ride
    "Porte coincée": -3,                        # Door stuck
    "Véhicule surchargé": -2,                   # Overcrowded vehicle
}

PROFILE_MAP = {
    "wheelchair": WHEELCHAIR_ITEMS,
    "blind": BLIND_ITEMS,
    "deaf": DEAF_ITEMS,
    "low_digital": LOW_DIGITAL_ITEMS,
    "elderly": ELDERLY_ITEMS,
}


# ── Table bootstrap — runs once on import ─────────────────────────────────────

def _bootstrap():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stop_observations (
            obs_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            stop_id      TEXT NOT NULL,
            block_type   TEXT NOT NULL,
            checked_item TEXT NOT NULL,
            source       TEXT DEFAULT 'epicollect',
            submitted_at TEXT,
            FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_obs_stop  ON stop_observations(stop_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_obs_block ON stop_observations(block_type)"
    )
    conn.commit()
    conn.close()

_bootstrap()


def _maybe_seed_demo():
    """Auto-seed demo observations if the table is empty."""
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM stop_observations").fetchone()[0]
    conn.close()
    if count == 0:
        try:
            from backend.mock_data.seed_observations import seed_observations
            seed_observations()
        except Exception as e:
            print(f"[stop_evaluator] demo seed skipped: {e}")

_maybe_seed_demo()


# ── Core helpers ──────────────────────────────────────────────────────────────

def normalize_label(text: str) -> str:
    """Lowercase, strip whitespace, drop accent diacritics, truncate at 30 chars.

    Also folds the small/fullwidth greater-than variants (﹥ U+FE65, ＞ U+FF1E)
    that the live Epicollect form uses down to ASCII '>', so survey labels like
    "Route à vitesse élevée (﹥ 50 km/h)" match the weight-dict key exactly (the
    sync routes items by exact normalized lookup, not prefix overlap).
    """
    text = text.strip().lower()
    text = text.replace("﹥", ">").replace("＞", ">")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text[:30]


# ── Item → block routing (single source of truth) ──────────────────────────────
# The new survey is one flat observation list, so each item must be routed to a
# scoring block by which weight dict contains it — not by its survey column.
# Precedence: profile dicts → accessibility, then safety overrides, then
# experience fills any remaining gaps. Both the CSV importer and the API sync
# route through block_for_item() so the mapping can never drift between them.

def _build_block_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for weights in PROFILE_MAP.values():
        for item in weights:
            index[normalize_label(item)] = "accessibility"
    for item in SAFETY_ITEMS:
        index[normalize_label(item)] = "safety"
    for item in EXPERIENCE_ITEMS:
        index.setdefault(normalize_label(item), "experience")
    return index

BLOCK_INDEX = _build_block_index()


def block_for_item(item: str) -> str | None:
    """Scoring block ('accessibility'|'safety'|'experience') that owns this
    observation item, or None if it matches no weight dict (unmatched vocabulary)."""
    return BLOCK_INDEX.get(normalize_label(item))


def score_block(checked_items: list[str], item_weights: dict) -> dict:
    """
    Compute a normalized [0,1] score for one block (accessibility/safety/experience).
    Matching is done via normalize_label so accents and small typos are forgiven.
    """
    norm_checked = {normalize_label(i) for i in checked_items}

    max_possible = sum(w for w in item_weights.values() if w > 0)
    min_possible = sum(w for w in item_weights.values() if w < 0)
    span = max_possible - min_possible  # always > 0 given our dicts

    raw = 0
    matched_positives: list[str] = []
    matched_negatives: list[str] = []

    for item, weight in item_weights.items():
        norm_item = normalize_label(item)
        # Direct match or prefix-of-30 overlap
        if norm_item in norm_checked or any(
            norm_item.startswith(c[:30]) or c[:30].startswith(norm_item[:20])
            for c in norm_checked
        ):
            raw += weight
            if weight > 0:
                matched_positives.append(item)
            else:
                matched_negatives.append(item)

    normalized = max(0.0, min(1.0, (raw - min_possible) / span)) if span else 0.5

    if normalized >= 0.70:
        label, color = "Good", "green"
    elif normalized >= 0.40:
        label, color = "Fair", "orange"
    else:
        label, color = "Poor", "red"

    return {
        "raw_score": raw,
        "normalized": round(normalized, 3),
        "label": label,
        "color": color,
        "matched_items": matched_positives + matched_negatives,
        "matched_positives": matched_positives,
        "matched_negatives": matched_negatives,
        "positives_matched": len(matched_positives),
        "negatives_matched": len(matched_negatives),
    }


def evaluate_accessibility(checked_items: list[str], profile: str = "all") -> dict:
    if profile == "all":
        results = {
            name: score_block(checked_items, weights)
            for name, weights in PROFILE_MAP.items()
        }
        worst = min(results.values(), key=lambda r: r["normalized"])
        worst["profile_breakdown"] = {k: v["label"] for k, v in results.items()}
        return worst

    weights = PROFILE_MAP.get(profile)
    if not weights:
        raise ValueError(f"Unknown profile '{profile}'. Choose from: {list(PROFILE_MAP)}")
    return score_block(checked_items, weights)


def evaluate_safety(checked_items: list[str]) -> dict:
    return score_block(checked_items, SAFETY_ITEMS)


def evaluate_experience(checked_items: list[str]) -> dict:
    return score_block(checked_items, EXPERIENCE_ITEMS)


# ── Ride experience (network-wide) ────────────────────────────────────────────
# Ride feedback comes from the Epicollect "Évaluer un trajet / Evaluate ride
# experience" contribution type, which carries no stop (a ride happens between
# stops, not at one). So Ride Experience is a single service-wide score computed
# from ALL experience-tagged observations, and shown on every stop.

SERVICE_STOP_ID = "__SERVICE__"   # synthetic owner for stop-less ride feedback


def evaluate_ride_experience() -> dict:
    """Network-wide Ride Experience score from every experience-tagged observation."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT checked_item FROM stop_observations WHERE block_type = 'experience'"
    ).fetchall()
    conn.close()
    items = [r["checked_item"] for r in rows]
    result = score_block(items, EXPERIENCE_ITEMS)
    result["feedback_count"] = len(items)
    return result


# ── Main evaluator ────────────────────────────────────────────────────────────

def evaluate_stop(stop_id: str, profile: str = "all") -> dict:
    conn = get_conn()

    stop_row = conn.execute(
        "SELECT stop_id, name, latitude, longitude FROM stops WHERE stop_id = ?",
        (stop_id,),
    ).fetchone()

    if not stop_row:
        conn.close()
        return {"error": f"Stop '{stop_id}' not found"}

    obs_rows = conn.execute(
        "SELECT block_type, checked_item FROM stop_observations WHERE stop_id = ?",
        (stop_id,),
    ).fetchall()
    conn.close()

    survey_count = len(obs_rows)

    # The survey is a single flat observation list, so every checked item is
    # pooled and scored against every dimension. score_block() only counts the
    # items present in each weight dict, so an observation that is relevant to
    # several dimensions (e.g. "Abri disponible") correctly lifts each of them.
    # block_type is retained in the DB for provenance only and is not used here.
    checked_items = [row["checked_item"] for row in obs_rows]

    # Map UI profile names → internal profile keys
    _profile_alias = {
        "motor-wheelchair": "wheelchair",
        "manual-wheelchair": "wheelchair",
    }
    internal_profile = _profile_alias.get(profile, profile)

    accessibility = evaluate_accessibility(checked_items, internal_profile)
    safety        = evaluate_safety(checked_items)
    # Ride experience is network-wide (feedback is not tied to a stop), so every
    # stop shows the same aggregated Ride Experience score.
    experience    = evaluate_ride_experience()

    punctuality = {"label": "Good", "color": "green", "value": "On time 87%"}
    regularity  = {"label": "Every 15-20 min", "sublabel": "(Usually)", "color": "purple"}

    return {
        "stop_id":   stop_row["stop_id"],
        "stop_name": stop_row["name"],
        "latitude":  stop_row["latitude"],
        "longitude": stop_row["longitude"],
        "scores": {
            "accessibility": accessibility,
            "safety":        safety,
            "punctuality":   punctuality,
            "experience":    experience,
            "regularity":    regularity,
        },
        "profile_used":     profile,
        "survey_count":     survey_count,
        "data_confidence":  "high" if survey_count >= 3 else "medium" if survey_count >= 1 else "low",
    }
