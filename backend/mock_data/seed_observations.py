"""
Demo observation seeder for the Stop Evaluator.
Inserts realistic Epicollect survey data for 8 stops so the UI has meaningful
scores immediately without needing a real CSV upload.

Idempotent: only inserts if stop_observations is empty.
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import get_conn

# ── Demo observations per stop ─────────────────────────────────────────────────
# Each entry: (stop_name_fragment, block, [items])
# stop_name_fragment is matched case-insensitively against the stops table.

DEMO_DATA = [
    # ── Cornavin — flagship urban hub, best-equipped stop ─────────────────────
    ("Cornavin", "accessibility", [
        "Surface dure et stable",
        "Bordure abaissée présente",
        "Embarquement de plain-pied avec le véhicule",
        "Espace suffisant pour manœuvrer un fauteuil",
        "Bandes podotactiles de guidage",
        "Bandes podotactiles d'éveil au bord",
        "Affichage temps réel (PID)",
        "Nom de l'arrêt clairement visible et lisible",
        "Pictogrammes universels",
        "Plan du réseau",
        "Signalétique à fort contraste visuel",
    ]),
    ("Cornavin", "safety", [
        "Éclairage suffisant",
        "Commerce ou Hopital-pharmacie proche",
        "Passage piéton proche",
        "Zone scolaire proche",
    ]),
    ("Cornavin", "experience", [
        "Abri disponible",
        "Banc disponible",
        "Zone calme",
        "Stationnement vélo proche",
    ]),

    # ── Aïre — rural/isolated, minimal facilities ─────────────────────────────
    ("Aïre", "accessibility", [
        "Surface meuble ou irrégulière",
        "Forte pente",
        "Obstacles dans la zone d'attente",
    ]),
    ("Aïre", "safety", [
        "Zone sombre",
        "Zone isolée",
        "Couverture mobile faible",
        "Route à vitesse élevée (> 50 km/h)",
    ]),
    ("Aïre", "experience", []),

    # ── Bachet-de-Pesay — suburban, mid-tier ─────────────────────────────────
    ("Bachet", "accessibility", [
        "Surface dure et stable",
        "Nom de l'arrêt clairement visible et lisible",
        "Affichage temps réel (PID)",
    ]),
    ("Bachet", "safety", [
        "Éclairage suffisant",
        "Passage piéton proche",
    ]),
    ("Bachet", "experience", [
        "Abri disponible",
        "Banc disponible",
    ]),

    # ── Hôpital Cantonal — hospital, strong accessibility focus ───────────────
    ("Cantonal", "accessibility", [
        "Surface dure et stable",
        "Bordure abaissée présente",
        "Embarquement de plain-pied avec le véhicule",
        "Espace suffisant pour manœuvrer un fauteuil",
        "Bandes podotactiles de guidage",
        "Affichage temps réel (PID)",
        "Nom de l'arrêt clairement visible et lisible",
        "Information en braille",
        "Signalétique à fort contraste visuel",
        "Pictogrammes universels",
    ]),
    ("Cantonal", "safety", [
        "Éclairage suffisant",
        "Commerce ou Hopital-pharmacie proche",
        "Passage piéton proche",
    ]),
    ("Cantonal", "experience", [
        "Abri disponible",
        "Banc disponible",
        "Zone calme",
    ]),

    # ── Nations (UN area) — well-lit, busy, good overall ─────────────────────
    ("Nations", "accessibility", [
        "Surface dure et stable",
        "Bordure abaissée présente",
        "Affichage temps réel (PID)",
        "Nom de l'arrêt clairement visible et lisible",
        "Pictogrammes universels",
        "Plan du réseau",
        "Signalétique à fort contraste visuel",
    ]),
    ("Nations", "safety", [
        "Éclairage suffisant",
        "Passage piéton proche",
        "Commerce ou Hopital-pharmacie proche",
    ]),
    ("Nations", "experience", [
        "Abri disponible",
        "Banc disponible",
        "Stationnement vélo proche",
    ]),

    # ── CERN — tech campus, well-maintained but car-centric road ─────────────
    ("CERN", "accessibility", [
        "Surface dure et stable",
        "Embarquement de plain-pied avec le véhicule",
        "Affichage temps réel (PID)",
        "Nom de l'arrêt clairement visible et lisible",
        "Signalétique à fort contraste visuel",
    ]),
    ("CERN", "safety", [
        "Éclairage suffisant",
        "Route à vitesse élevée (> 50 km/h)",
    ]),
    ("CERN", "experience", [
        "Abri disponible",
        "Zone calme",
        "Stationnement vélo proche",
    ]),

    # ── Vernier-Village — village stop, partial facilities ────────────────────
    ("Vernier", "accessibility", [
        "Surface dure et stable",
        "Nom de l'arrêt clairement visible et lisible",
        "Pente du chemin",
    ]),
    ("Vernier", "safety", [
        "Éclairage suffisant",
        "Zone sombre",
    ]),
    ("Vernier", "experience", [
        "Abri disponible",
    ]),

    # ── Rive — lakeside, scenic but some negatives ────────────────────────────
    ("Rive", "accessibility", [
        "Surface dure et stable",
        "Bordure abaissée présente",
        "Affichage temps réel (PID)",
        "Nom de l'arrêt clairement visible et lisible",
        "Obstacles dans la zone d'attente",
    ]),
    ("Rive", "safety", [
        "Passage piéton proche",
        "Commerce ou Hopital-pharmacie proche",
        "Zone scolaire proche",
    ]),
    ("Rive", "experience", [
        "Abri disponible",
        "Banc disponible",
    ]),
]


def seed_observations():
    conn = get_conn()

    # Idempotency check
    count = conn.execute("SELECT COUNT(*) FROM stop_observations").fetchone()[0]
    if count > 0:
        conn.close()
        return

    # Build name → stop_id index
    rows = conn.execute("SELECT stop_id, name FROM stops").fetchall()
    stop_index = {r["name"].lower(): r["stop_id"] for r in rows}

    now = datetime.now().isoformat()
    total = 0

    for (name_frag, block, items) in DEMO_DATA:
        # Match by substring (case-insensitive)
        frag = name_frag.lower()
        stop_id = None
        for sname, sid in stop_index.items():
            if frag in sname:
                stop_id = sid
                break
        if not stop_id:
            print(f"[seed_observations] no stop matched '{name_frag}', skipping")
            continue

        for item in items:
            conn.execute(
                """INSERT INTO stop_observations
                   (stop_id, block_type, checked_item, source, submitted_at)
                   VALUES (?, ?, ?, 'demo', ?)""",
                (stop_id, block, item, now),
            )
            total += 1

    conn.commit()
    conn.close()
    print(f"[seed_observations] inserted {total} demo observations for 8 stops")


if __name__ == "__main__":
    seed_observations()
