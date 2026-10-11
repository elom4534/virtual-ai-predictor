import sqlite3
import csv
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "real_fifa_collection.db")
EXPORT_CSV = os.path.join(os.path.dirname(__file__), "real_fifa_matches_export.csv")
EXPORT_JSON = os.path.join(os.path.dirname(__file__), "real_fifa_matches_export.json")

def export_all():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, bookmaker, competition_id, competition_name, home_team, away_team,
           scheduled_start_time, status, home_score, away_score,
           odds_1, odds_x, odds_2, odds_dc_1x, odds_dc_12, odds_dc_x2,
           odds_over_total, odds_under_total, odds_param_total,
           first_seen_at, last_seen_at, validation_status
    FROM real_fifa_matches
    ORDER BY scheduled_start_time ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    dict_rows = [dict(r) for r in rows]

    # Write CSV
    if dict_rows:
        with open(EXPORT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=dict_rows[0].keys())
            writer.writeheader()
            writer.writerows(dict_rows)

    # Write JSON
    with open(EXPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(dict_rows, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(dict_rows)} real matches to CSV and JSON successfully.")
    return len(dict_rows)

if __name__ == "__main__":
    export_all()
