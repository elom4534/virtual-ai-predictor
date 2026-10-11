import urllib.request
import json
import sqlite3
import time
from datetime import datetime, timezone
import os
from logo_service import get_team_logo

DB_PATH = os.path.join(os.path.dirname(__file__), "real_fifa_collection.db")
MAIN_DB_PATH = os.path.join(os.path.dirname(__file__), "virtual_fifa.db")

MONITORED_SPORTS = [
    {"id": 85, "name": "FIFA / EA FC", "type": "CYBER_FIFA"},
    {"id": 144, "name": "PES / eFootball", "type": "PES_EFOOTBALL"},
    {"id": 276, "name": "SEGA Football", "type": "SEGA_FOOTBALL"},
    {"id": 40, "name": "Jeux Virtuels (RNG)", "type": "VIRTUAL_SPORTS"},
]

def init_collection_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS real_fifa_matches (
        id TEXT PRIMARY KEY,
        bookmaker TEXT NOT NULL,
        sport_id INTEGER NOT NULL DEFAULT 85,
        sport_category TEXT NOT NULL DEFAULT 'CYBER_FIFA',
        competition_id INTEGER,
        competition_name TEXT NOT NULL,
        game_format_tag TEXT NOT NULL DEFAULT 'SIMULATION_11V11',
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        home_logo_url TEXT,
        away_logo_url TEXT,
        scheduled_start_time TEXT NOT NULL,
        status TEXT NOT NULL,
        home_score INTEGER,
        away_score INTEGER,
        ht_home_score INTEGER,
        ht_away_score INTEGER,
        odds_1 REAL,
        odds_x REAL,
        odds_2 REAL,
        odds_dc_1x REAL,
        odds_dc_12 REAL,
        odds_dc_x2 REAL,
        odds_over_total REAL,
        odds_under_total REAL,
        odds_param_total REAL,
        source_url TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        completed_at TEXT,
        validation_status TEXT NOT NULL DEFAULT 'PENDING',
        raw_json TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS collection_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        endpoint_queried TEXT NOT NULL,
        http_status INTEGER NOT NULL,
        matches_found INTEGER NOT NULL,
        new_matches_added INTEGER NOT NULL,
        matches_updated INTEGER NOT NULL,
        matches_completed INTEGER NOT NULL,
        error_message TEXT
    );
    """)

    conn.commit()
    conn.close()

def parse_odds_from_feed(e_list):
    odds = {
        "1": None, "x": None, "2": None,
        "1x": None, "12": None, "x2": None,
        "over": None, "under": None, "param_total": None
    }
    for item in e_list or []:
        t = item.get("T")
        c = item.get("C")
        p = item.get("P")
        if t == 1: odds["1"] = c
        elif t == 2: odds["x"] = c
        elif t == 3: odds["2"] = c
        elif t == 4: odds["1x"] = c
        elif t == 5: odds["12"] = c
        elif t == 6: odds["x2"] = c
        elif t == 9:
            odds["over"] = c
            odds["param_total"] = p
        elif t == 10:
            odds["under"] = c
            odds["param_total"] = p
    return odds

def fetch_feed_for_sports(sport_ids_str: str = "85,144,276", timeout=6):
    url = f"https://betwinner.com/service-api/LiveFeed/Get1x2_VZip?sports={sport_ids_str}&count=200&lng=fr&mode=4"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return 200, data.get("Value", []), url, None
    except Exception as e:
        return 0, [], url, str(e)

LAST_SYNC_TIME = 0

def sync_real_live_feed_into_app(force=False, ensemble_model=None):
    """
    Fetches real live matches from 1xBet/BetWinner feed and updates main database.
    Throttled to run at most once every 15 seconds unless force=True.
    """
    global LAST_SYNC_TIME
    now_ts = time.time()
    if not force and (now_ts - LAST_SYNC_TIME) < 15:
        return {"status": "SKIPPED_THROTTLED", "message": "Recently synced"}

    LAST_SYNC_TIME = now_ts
    status_code, feed_matches, url, err = fetch_feed_for_sports(sport_ids_str="85,144,276")

    if status_code != 200 or not feed_matches:
        return {"status": "FEED_ERROR", "error": err, "matches_found": 0}

    now_utc = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(MAIN_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM matches WHERE status = 'FINISHED' LIMIT 150")
    hist_rows = [dict(sqlite3.Row(cursor, r)) for r in cursor.fetchall()] if cursor.description else []

    synced_count = 0
    matches_to_upsert = []
    preds_to_upsert = []

    for m in feed_matches:
        raw_id = str(m.get("I"))
        match_id = f"real_{raw_id}"
        comp_name = m.get("L", "FIFA Virtuel")
        home_team = m.get("O1", "Équipe 1")
        away_team = m.get("O2", "Équipe 2")
        start_ts = m.get("S", 0)
        start_iso = datetime.fromtimestamp(start_ts, timezone.utc).isoformat() if start_ts else now_utc

        sc = m.get("SC", {})
        fs = sc.get("FS", {})
        info_str = sc.get("I", "")
        
        if "Match terminé" in info_str:
            status = "FINISHED"
            h_score = int(fs.get("S1", 0)) if fs else 0
            a_score = int(fs.get("S2", 0)) if fs else 0
        elif "Paris avant le début" in info_str or not fs:
            status = "SCHEDULED"
            h_score, a_score = None, None
        else:
            status = "LIVE"
            h_score = int(fs.get("S1", 0))
            a_score = int(fs.get("S2", 0))

        odds = parse_odds_from_feed(m.get("E", []))
        odd_1 = odds.get("1")
        odd_x = odds.get("x")
        odd_2 = odds.get("2")
        odd_over = odds.get("over")
        odd_under = odds.get("under")

        matches_to_upsert.append((
            match_id, "1xBet", "Simulation 11v11 (8 min)", comp_name,
            home_team, away_team, start_iso, status,
            h_score, a_score, h_score, a_score,
            odd_1, odd_x, odd_2, odd_over, odd_under, 1.70, 2.05,
            "1XBET_LIVE_FEED", "VALIDATED", now_utc, now_utc
        ))

        # Generate Real-Time AI Prediction
        if ensemble_model:
            try:
                odds_dict = {"1": odd_1 or 2.0, "x": odd_x or 3.2, "2": odd_2 or 2.8}
                pred = ensemble_model.generate_prediction(
                    matches_history=hist_rows,
                    home_team=home_team,
                    away_team=away_team,
                    bookmaker="1xBet",
                    competition=comp_name,
                    odds=odds_dict
                )
                preds_to_upsert.append((
                    f"pred_{match_id}", match_id, pred["model_version"], now_utc,
                    pred["markets"]["1x2"]["home_win"], pred["markets"]["1x2"]["draw"], pred["markets"]["1x2"]["away_win"],
                    pred["markets"]["over_under"]["over_1.5"], pred["markets"]["over_under"]["under_1.5"],
                    pred["markets"]["over_under"]["over_2.5"], pred["markets"]["over_under"]["under_2.5"],
                    pred["markets"]["over_under"]["over_3.5"], pred["markets"]["over_under"]["under_3.5"],
                    pred["markets"]["btts"]["yes"], pred["markets"]["btts"]["no"],
                    pred["markets"]["double_chance"]["1x"], pred["markets"]["double_chance"]["12"], pred["markets"]["double_chance"]["x2"],
                    json.dumps(pred["markets"]["exact_scores"]), pred["expected_goals"]["home"], pred["expected_goals"]["away"],
                    pred["main_pick"]["market"], pred["main_pick"]["selection"], pred["confidence_score"], pred["confidence_tier"],
                    pred["sample_size_h2h"], pred["sample_size_team"],
                    json.dumps(pred["reasoning"]["positive_factors"]), json.dumps(pred["reasoning"]["negative_factors"]),
                    json.dumps(pred["sub_models"]["poisson"]), json.dumps(pred["sub_models"]["trend"]), json.dumps(pred["sub_models"]["ml"]),
                    "PENDING"
                ))
            except Exception:
                pass

        synced_count += 1

    cursor.executemany("""
    INSERT INTO matches (
        id, bookmaker, game_format, competition, home_team, away_team,
        match_time, status, home_score, away_score, ht_home_score, ht_away_score,
        odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_btts_yes, odds_btts_no,
        source, validation_status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        status = excluded.status,
        home_score = excluded.home_score,
        away_score = excluded.away_score,
        odds_1 = excluded.odds_1,
        odds_x = excluded.odds_x,
        odds_2 = excluded.odds_2,
        updated_at = excluded.updated_at
    """, matches_to_upsert)

    if preds_to_upsert:
        cursor.executemany("""
        INSERT INTO predictions (
            id, match_id, model_version, created_at,
            prob_home_win, prob_draw, prob_away_win,
            prob_over15, prob_under15, prob_over25, prob_under25, prob_over35, prob_under35,
            prob_btts_yes, prob_btts_no, prob_dc_1x, prob_dc_12, prob_dc_x2,
            top_exact_scores, expected_home_goals, expected_away_goals,
            main_pick_market, main_pick_selection, confidence_score, confidence_tier,
            sample_size_h2h, sample_size_team, reasoning_positive, reasoning_negative,
            model_poisson_probs, model_trend_probs, model_ml_probs,
            evaluation_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            prob_home_win = excluded.prob_home_win,
            prob_draw = excluded.prob_draw,
            prob_away_win = excluded.prob_away_win,
            confidence_score = excluded.confidence_score
        """, preds_to_upsert)

    conn.commit()
    conn.close()

    return {"status": "SUCCESS", "matches_synced": synced_count}

def sync_fifa_matches_cycle():
    """Alias for backward compatibility."""
    return sync_real_live_feed_into_app(force=True)
