import urllib.request
import json
import sqlite3
import time
from datetime import datetime, timezone
import os
from logo_service import get_team_logo

DB_PATH = os.path.join(os.path.dirname(__file__), "real_fifa_collection.db")

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
        game_format_tag TEXT NOT NULL DEFAULT 'SIMULATION_11V11', -- 'SIMULATION_11V11', 'RUSH_5X5', 'RUSH_4X4', 'PENALTY', 'PES', 'SEGA'
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        home_logo_url TEXT,
        away_logo_url TEXT,
        scheduled_start_time TEXT NOT NULL,
        status TEXT NOT NULL, -- 'SCHEDULED', 'IN_PLAY', 'FINISHED'
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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_real_status ON real_fifa_matches(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_real_start ON real_fifa_matches(scheduled_start_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_real_comp ON real_fifa_matches(competition_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_real_sport ON real_fifa_matches(sport_id);")

    conn.commit()
    conn.close()

def categorize_game_format(comp_name: str, sport_id: int) -> str:
    """Classifies the virtual game into specific algorithmic format."""
    c_lower = comp_name.lower()
    if sport_id == 144 or "pes" in c_lower:
        return "PES_EFOOTBALL"
    elif sport_id == 276 or "sega" in c_lower:
        return "SEGA_FOOTBALL"
    elif "penalty" in c_lower:
        return "PENALTY_SHOOTOUT"
    elif "5x5" in c_lower or "rush" in c_lower:
        return "RUSH_5X5"
    elif "4x4" in c_lower:
        return "RUSH_4X4"
    elif "3x3" in c_lower:
        return "RUSH_3X3"
    elif "esports" in c_lower or "battle" in c_lower or "gt league" in c_lower:
        return "ESPORTS_GAMERS"
    return "SIMULATION_11V11"

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

def fetch_feed_for_sports(sport_ids_str: str = "85,144,276", timeout=8):
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

def sync_fifa_matches_cycle():
    init_collection_db()
    now_utc = datetime.now(timezone.utc).isoformat()

    status_code, feed_matches, url, err = fetch_feed_for_sports(sport_ids_str="85,144,276")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if status_code != 200:
        cursor.execute("""
        INSERT INTO collection_logs (timestamp, endpoint_queried, http_status, matches_found, new_matches_added, matches_updated, matches_completed, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_utc, url, status_code, 0, 0, 0, 0, err))
        conn.commit()
        conn.close()
        return {"success": False, "error": err}

    current_feed_ids = set()
    new_added = 0
    updated_cnt = 0
    completed_cnt = 0

    for m in feed_matches:
        match_id = str(m.get("I"))
        current_feed_ids.add(match_id)

        sport_id = m.get("SI", 85)
        comp_id = m.get("LI")
        comp_name = m.get("L", "FIFA Virtuel")
        home_team = m.get("O1", "Équipe 1")
        away_team = m.get("O2", "Équipe 2")
        start_ts = m.get("S", 0)
        start_iso = datetime.fromtimestamp(start_ts, timezone.utc).isoformat() if start_ts else now_utc

        format_tag = categorize_game_format(comp_name, sport_id)
        sport_cat = "CYBER_FIFA" if sport_id == 85 else ("PES_EFOOTBALL" if sport_id == 144 else "SEGA_FOOTBALL")

        # Resolve Real Team Logos
        home_logo = get_team_logo(home_team)
        away_logo = get_team_logo(away_team)

        sc = m.get("SC", {})
        fs = sc.get("FS", {})
        
        info_str = sc.get("I", "")
        if "Paris avant le début" in info_str or not fs:
            match_status = "SCHEDULED"
            h_score = None
            a_score = None
        else:
            match_status = "IN_PLAY"
            h_score = int(fs.get("S1", 0))
            a_score = int(fs.get("S2", 0))

        odds_parsed = parse_odds_from_feed(m.get("E", []))
        raw_json_str = json.dumps(m, ensure_ascii=False)

        cursor.execute("SELECT id, status, home_score, away_score FROM real_fifa_matches WHERE id = ?", (match_id,))
        existing = cursor.fetchone()

        if not existing:
            cursor.execute("""
            INSERT INTO real_fifa_matches (
                id, bookmaker, sport_id, sport_category, competition_id, competition_name, game_format_tag,
                home_team, away_team, home_logo_url, away_logo_url,
                scheduled_start_time, status, home_score, away_score,
                odds_1, odds_x, odds_2, odds_dc_1x, odds_dc_12, odds_dc_x2,
                odds_over_total, odds_under_total, odds_param_total,
                source_url, first_seen_at, last_seen_at, validation_status, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match_id, "BetWinner", sport_id, sport_cat, comp_id, comp_name, format_tag,
                home_team, away_team, home_logo, away_logo,
                start_iso, match_status, h_score, a_score,
                odds_parsed["1"], odds_parsed["x"], odds_parsed["2"],
                odds_parsed["1x"], odds_parsed["12"], odds_parsed["x2"],
                odds_parsed["over"], odds_parsed["under"], odds_parsed["param_total"],
                url, now_utc, now_utc, "PENDING", raw_json_str
            ))
            new_added += 1
        else:
            cursor.execute("""
            UPDATE real_fifa_matches SET
                status = ?,
                home_score = COALESCE(?, home_score),
                away_score = COALESCE(?, away_score),
                home_logo_url = COALESCE(home_logo_url, ?),
                away_logo_url = COALESCE(away_logo_url, ?),
                last_seen_at = ?,
                raw_json = ?
            WHERE id = ? AND status != 'FINISHED'
            """, (match_status, h_score, a_score, home_logo, away_logo, now_utc, raw_json_str, match_id))
            updated_cnt += 1

    # Detect finished matches
    cursor.execute("SELECT id, home_score, away_score FROM real_fifa_matches WHERE status = 'IN_PLAY'")
    in_play_rows = cursor.fetchall()
    for row in in_play_rows:
        pid, hs, as_ = row
        if pid not in current_feed_ids:
            cursor.execute("""
            UPDATE real_fifa_matches SET
                status = 'FINISHED',
                home_score = COALESCE(home_score, 0),
                away_score = COALESCE(away_score, 0),
                completed_at = ?,
                validation_status = 'CONFIRMED'
            WHERE id = ?
            """, (now_utc, pid))
            completed_cnt += 1

    cursor.execute("""
    INSERT INTO collection_logs (timestamp, endpoint_queried, http_status, matches_found, new_matches_added, matches_updated, matches_completed, error_message)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_utc, url, status_code, len(feed_matches), new_added, updated_cnt, completed_cnt, None))

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches;")
    total_stored = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'FINISHED';")
    total_finished = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'IN_PLAY';")
    total_live = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'SCHEDULED';")
    total_sched = cursor.fetchone()[0]

    cursor.execute("SELECT sport_category, COUNT(*) FROM real_fifa_matches GROUP BY sport_category;")
    sports_breakdown = dict(cursor.fetchall())

    conn.close()

    return {
        "success": True,
        "matches_in_feed": len(feed_matches),
        "new_added": new_added,
        "updated": updated_cnt,
        "completed": completed_cnt,
        "database_summary": {
            "total_matches": total_stored,
            "finished_confirmed": total_finished,
            "in_play": total_live,
            "scheduled": total_sched,
            "sports_breakdown": sports_breakdown
        }
    }

if __name__ == "__main__":
    res = sync_fifa_matches_cycle()
    print("Multi-Sport Sync Result:", json.dumps(res, indent=2, ensure_ascii=False))
