import sqlite3
import json
import os
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "virtual_fifa.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Matches table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        bookmaker TEXT NOT NULL,
        game_format TEXT NOT NULL,
        competition TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        match_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'FINISHED', -- 'SCHEDULED', 'LIVE', 'FINISHED'
        home_score INTEGER,
        away_score INTEGER,
        ht_home_score INTEGER,
        ht_away_score INTEGER,
        odds_1 REAL,
        odds_x REAL,
        odds_2 REAL,
        odds_over25 REAL,
        odds_under25 REAL,
        odds_btts_yes REAL,
        odds_btts_no REAL,
        source TEXT NOT NULL DEFAULT 'MANUAL',
        validation_status TEXT NOT NULL DEFAULT 'VALIDATED',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Predictions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        prob_home_win REAL NOT NULL,
        prob_draw REAL NOT NULL,
        prob_away_win REAL NOT NULL,
        prob_over15 REAL,
        prob_under15 REAL,
        prob_over25 REAL,
        prob_under25 REAL,
        prob_over35 REAL,
        prob_under35 REAL,
        prob_btts_yes REAL,
        prob_btts_no REAL,
        prob_dc_1x REAL,
        prob_dc_12 REAL,
        prob_dc_x2 REAL,
        top_exact_scores TEXT, -- JSON
        expected_home_goals REAL,
        expected_away_goals REAL,
        main_pick_market TEXT NOT NULL,
        main_pick_selection TEXT NOT NULL,
        confidence_score REAL NOT NULL,
        confidence_tier TEXT NOT NULL,
        sample_size_h2h INTEGER,
        sample_size_team INTEGER,
        reasoning_positive TEXT, -- JSON
        reasoning_negative TEXT, -- JSON
        model_poisson_probs TEXT, -- JSON
        model_trend_probs TEXT, -- JSON
        model_ml_probs TEXT, -- JSON
        evaluation_status TEXT DEFAULT 'PENDING', -- 'HIT', 'MISS', 'VOID'
        brier_score_1x2 REAL,
        log_loss_1x2 REAL,
        FOREIGN KEY (match_id) REFERENCES matches (id)
    );
    """)

    # Drift Alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drift_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        bookmaker TEXT NOT NULL,
        competition TEXT,
        metric_name TEXT NOT NULL,
        baseline_value REAL NOT NULL,
        recent_value REAL NOT NULL,
        sample_size INTEGER NOT NULL,
        p_value REAL NOT NULL,
        confidence_level TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        description TEXT NOT NULL
    );
    """)

    # Model Version Audit table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS model_versions (
        version TEXT PRIMARY KEY,
        deployed_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        trained_on_matches INTEGER NOT NULL,
        brier_score_val REAL NOT NULL,
        accuracy_1x2 REAL NOT NULL,
        accuracy_over25 REAL NOT NULL,
        accuracy_btts REAL NOT NULL,
        notes TEXT
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_time ON matches(match_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_bookmaker ON matches(bookmaker);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_preds_match ON predictions(match_id);")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
