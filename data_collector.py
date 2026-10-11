import csv
import json
import uuid
from datetime import datetime, timezone, timedelta
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import sqlite3
from database import get_db_connection

CYBER_TEAMS = [
    "Real Madrid Cyber", "Manchester City Cyber", "Bayern Munich Cyber", 
    "Paris SG Cyber", "Barcelona Cyber", "Liverpool Cyber", 
    "Arsenal Cyber", "Inter Milan Cyber", "Juventus Cyber", 
    "Chelsea Cyber", "Borussia Dortmund Cyber", "Atletico Madrid Cyber"
]

COMPETITIONS = [
    "FIFA 23 Cyber Champions League (4x4)",
    "FIFA 23 eSports Premier League (3x2 min)",
    "FIFA 23 Cyber World Cup (8 min)",
    "FIFA 23 eSports La Liga"
]

BOOKMAKERS = ["1xBet", "BetWinner", "MegaPari"]

def generate_match_hash(home_team: str, away_team: str, match_time: str, bookmaker: str) -> str:
    """Generates deterministic hash to prevent match duplicates."""
    raw = f"{home_team}_{away_team}_{match_time[:13]}_{bookmaker}".lower()
    return hashlib.md5(raw.encode()).hexdigest()

def validate_match_data(match_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validates logical integrity of match record.
    Checks score coherence, required fields and timestamps.
    """
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
    """Inserts or updates match record in database."""
    is_valid, err_msg = validate_match_data(match_dict)
    if not is_valid:
        return False, f"Erreur de validation : {err_msg}"

    conn = get_db_connection()
    cursor = conn.cursor()

    match_id = match_dict.get("id") or f"m_{generate_match_hash(match_dict['home_team'], match_dict['away_team'], match_dict['match_time'], match_dict['bookmaker'])}"
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor.execute("""
        INSERT INTO matches (
            id, bookmaker, game_format, competition, home_team, away_team,
            match_time, status, home_score, away_score, ht_home_score, ht_away_score,
            odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_btts_yes, odds_btts_no,
            source, validation_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            home_score = excluded.home_score,
            away_score = excluded.away_score,
            ht_home_score = excluded.ht_home_score,
            ht_away_score = excluded.ht_away_score,
            status = excluded.status,
            odds_1 = excluded.odds_1,
            odds_x = excluded.odds_x,
            odds_2 = excluded.odds_2,
            updated_at = excluded.updated_at
        """, (
            match_id,
            match_dict["bookmaker"],
            match_dict.get("game_format", "FIFA 23 Cyber 4x4"),
            match_dict.get("competition", "FIFA 23 Cyber Champions League (4x4)"),
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
    except Exception as e:
        conn.close()
        return False, str(e)

def import_csv_content(csv_text: str) -> Dict[str, Any]:
    """Parses and imports CSV dataset."""
    lines = csv_text.strip().split("\n")
    reader = csv.DictReader(lines)
    imported = 0
    errors = []

    for row in reader:
        try:
            m_dict = {
                "bookmaker": row.get("bookmaker", "1xBet").strip(),
                "game_format": row.get("game_format", "FIFA 23 Cyber 4x4").strip(),
                "competition": row.get("competition", "FIFA 23 Cyber Champions League").strip(),
                "home_team": row.get("home_team", "").strip(),
                "away_team": row.get("away_team", "").strip(),
                "match_time": row.get("match_time", datetime.now(timezone.utc).isoformat()).strip(),
                "status": row.get("status", "FINISHED").strip(),
                "home_score": int(row["home_score"]) if row.get("home_score") and row["home_score"].strip() != "" else None,
                "away_score": int(row["away_score"]) if row.get("away_score") and row["away_score"].strip() != "" else None,
                "ht_home_score": int(row["ht_home_score"]) if row.get("ht_home_score") and row["ht_home_score"].strip() != "" else None,
                "ht_away_score": int(row["ht_away_score"]) if row.get("ht_away_score") and row["ht_away_score"].strip() != "" else None,
                "odds_1": float(row["odds_1"]) if row.get("odds_1") and row["odds_1"].strip() != "" else None,
                "odds_x": float(row["odds_x"]) if row.get("odds_x") and row["odds_x"].strip() != "" else None,
                "odds_2": float(row["odds_2"]) if row.get("odds_2") and row["odds_2"].strip() != "" else None,
                "source": "CSV_IMPORT",
                "validation_status": "VALIDATED"
            }
            success, msg = insert_or_update_match(m_dict)
            if success:
                imported += 1
            else:
                errors.append(f"Ligne {row}: {msg}")
        except Exception as e:
            errors.append(f"Erreur parsing ligne: {str(e)}")

    return {
        "imported_count": imported,
        "error_count": len(errors),
        "errors": errors[:5]
    }
