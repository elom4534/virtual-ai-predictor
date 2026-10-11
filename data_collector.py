import csv
import json
import uuid
import io
from datetime import datetime, timezone, timedelta
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import sqlite3
from database import get_db_connection

COMPETITIONS = [
    "FC 26. 5x5 Rush. Superligue",
    "FC 24. 4x4. Championnat d'Angleterre",
    "FC 25. 3x3. Ligue de conférence",
    "FC 26. England Championship",
    "FC 26. Champions League",
    "FC 26. Championnat du monde",
    "England. Premier League. Simulation",
    "FC 25. Ligue européenne",
    "FC 26. Germany Championship",
    "FC 26. Italy Championship",
    "FC 26. Spain Championship"
]

BOOKMAKERS = ["1xBet", "BetWinner", "MegaPari"]

CYBER_TEAMS = [
    "Real Madrid Cyber", "Manchester City Cyber", "Bayern Munich Cyber", 
    "Paris SG Cyber", "Barcelona Cyber", "Liverpool Cyber", 
    "Arsenal Cyber", "Inter Milan Cyber", "Juventus Cyber", 
    "Chelsea Cyber", "Manchester United Cyber", "Borussia Dortmund Cyber", 
    "Atletico Madrid Cyber", "Tottenham Cyber", "Bayer Leverkusen Cyber",
    "AC Milan Cyber", "Napoli Cyber", "AS Roma Cyber", "Lazio Cyber", "Atalanta Cyber",
    "Sevilla Cyber", "Real Sociedad Cyber", "Real Betis Cyber", "Newcastle Cyber", "Aston Villa Cyber",
    "Leeds Cyber", "Leicester Cyber", "Southampton Cyber", "Ipswich Cyber", "West Brom Cyber", "Norwich Cyber",
    "Fiorentina Cyber", "Porto Cyber", "Ajax Cyber", "Lyon Cyber",
    "France Cyber", "Brazil Cyber", "Argentina Cyber", 
    "England Cyber", "Germany Cyber", "Spain Cyber", 
    "Portugal Cyber", "Italy Cyber", "Netherlands Cyber", "Belgium Cyber"
]

def generate_match_hash(home_team: str, away_team: str, match_time: str, bookmaker: str) -> str:
    """Generates deterministic hash to prevent match duplicates."""
    raw = f"{home_team}_{away_team}_{match_time[:13]}_{bookmaker}".lower()
    return hashlib.md5(raw.encode()).hexdigest()

def validate_match_data(match_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    required = ["bookmaker", "home_team", "away_team", "match_time"]
    for r in required:
        if not match_dict.get(r):
            return False, f"Champ obligatoire manquant : {r}"

    if match_dict["home_team"] == match_dict["away_team"]:
        return False, "Les équipes à domicile et à l'extérieur doivent être différentes."

    hs = match_dict.get("home_score")
    as_ = match_dict.get("away_score")
    ht_hs = match_dict.get("ht_home_score")
    ht_as = match_dict.get("ht_away_score")

    if hs is not None and as_ is not None:
        if hs < 0 or as_ < 0:
            return False, "Les scores ne peuvent pas être négatifs."
        if ht_hs is not None and ht_hs > hs:
            return False, f"Incohérence : Score mi-temps domicile ({ht_hs}) > Score final ({hs})."
        if ht_as is not None and ht_as > as_:
            return False, f"Incohérence : Score mi-temps extérieur ({ht_as}) > Score final ({as_})."

    return True, None

def insert_or_update_match(match_dict: Dict[str, Any]) -> Tuple[bool, str]:
    is_valid, err = validate_match_data(match_dict)
    if not is_valid:
        return False, f"Validation échouée : {err}"

    conn = get_db_connection()
    cursor = conn.cursor()

    match_id = match_dict.get("id") or f"match_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
    INSERT INTO matches (
        id, bookmaker, game_format, competition,
        home_team, away_team, match_time, status,
        home_score, away_score, ht_home_score, ht_away_score,
        odds_1, odds_x, odds_2, odds_over25, odds_under25,
        odds_btts_yes, odds_btts_no, source, validation_status,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        status = excluded.status,
        home_score = excluded.home_score,
        away_score = excluded.away_score,
        ht_home_score = excluded.ht_home_score,
        ht_away_score = excluded.ht_away_score,
        odds_1 = excluded.odds_1,
        odds_x = excluded.odds_x,
        odds_2 = excluded.odds_2,
        odds_over25 = excluded.odds_over25,
        odds_under25 = excluded.odds_under25,
        odds_btts_yes = excluded.odds_btts_yes,
        odds_btts_no = excluded.odds_btts_no,
        updated_at = excluded.updated_at
    """, (
        match_id,
        match_dict["bookmaker"],
        match_dict.get("game_format", "Simulation 11v11 (8 min)"),
        match_dict.get("competition", "FC 26. Champions League"),
        match_dict["home_team"],
        match_dict["away_team"],
        match_dict["match_time"],
        match_dict.get("status", "FINISHED"),
        match_dict.get("home_score"),
        match_dict.get("away_score"),
        match_dict.get("ht_home_score"),
        match_dict.get("ht_away_score"),
        match_dict.get("odds_1"),
        match_dict.get("odds_x"),
        match_dict.get("odds_2"),
        match_dict.get("odds_over25"),
        match_dict.get("odds_under25"),
        match_dict.get("odds_btts_yes"),
        match_dict.get("odds_btts_no"),
        match_dict.get("source", "MANUAL"),
        match_dict.get("validation_status", "VALIDATED"),
        match_dict.get("created_at", now_iso),
        now_iso
    ))

    conn.commit()
    conn.close()
    return True, match_id

def import_csv_content(csv_text: str) -> Dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    inserted = 0
    rejected = 0
    errors = []

    for row in reader:
        try:
            m_dict = {
                "id": row.get("id"),
                "bookmaker": row.get("bookmaker", "1xBet"),
                "game_format": row.get("game_format", "Simulation 11v11 (8 min)"),
                "competition": row.get("competition", "FC 26. Champions League"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "match_time": row.get("match_time", datetime.now(timezone.utc).isoformat()),
                "status": row.get("status", "FINISHED"),
                "home_score": int(row["home_score"]) if row.get("home_score") not in (None, "") else None,
                "away_score": int(row["away_score"]) if row.get("away_score") not in (None, "") else None,
                "ht_home_score": int(row["ht_home_score"]) if row.get("ht_home_score") not in (None, "") else None,
                "ht_away_score": int(row["ht_away_score"]) if row.get("ht_away_score") not in (None, "") else None,
                "odds_1": float(row["odds_1"]) if row.get("odds_1") not in (None, "") else None,
                "odds_x": float(row["odds_x"]) if row.get("odds_x") not in (None, "") else None,
                "odds_2": float(row["odds_2"]) if row.get("odds_2") not in (None, "") else None,
                "source": row.get("source", "CSV_IMPORT"),
                "validation_status": "VALIDATED"
            }
            success, res = insert_or_update_match(m_dict)
            if success:
                inserted += 1
            else:
                rejected += 1
                errors.append(res)
        except Exception as e:
            rejected += 1
            errors.append(str(e))

    return {
        "inserted": inserted,
        "rejected": rejected,
        "errors": errors[:5]
    }
