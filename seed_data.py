import random
from datetime import datetime, timezone, timedelta
import json
import sqlite3
import numpy as np

from database import init_db, get_db_connection
from data_collector import BOOKMAKERS
from models_stat import StatisticalPoissonEngine
from models_ml import VirtualAIEnsemblePredictor
from drift_detector import DistributionDriftDetector

CYBER_CLUBS = [
    "Real Madrid Cyber", "Manchester City Cyber", "Bayern Munich Cyber", 
    "Paris SG Cyber", "Barcelona Cyber", "Liverpool Cyber", 
    "Arsenal Cyber", "Inter Milan Cyber", "Juventus Cyber", 
    "Chelsea Cyber", "Borussia Dortmund Cyber", "Atletico Madrid Cyber"
]

CYBER_NATIONS = [
    "France Cyber", "Brazil Cyber", "Argentina Cyber", 
    "England Cyber", "Germany Cyber", "Spain Cyber", 
    "Portugal Cyber", "Italy Cyber"
]

ALL_CYBER_TEAMS = CYBER_CLUBS + CYBER_NATIONS

FORMAT_CONFIGS = [
    {
        "format_tag": "SIM",
        "game_format": "FIFA Simulation 11v11 (8 min)",
        "competitions": [
            "EsportsBattle Champions League (8 min)",
            "FIFA 24 Cyber Premier League (2x4 min)",
            "FIFA Cyber World Cup (8 min)",
            "FIFA 24 Volta Cyber (2x4 min)"
        ],
        "team_pool": ALL_CYBER_TEAMS,
        "avg_goals": 2.8,
        "duration_min": 8
    },
    {
        "format_tag": "RUSH",
        "game_format": "FIFA Rush 4x4 & 5x5 (3x2 min)",
        "competitions": [
            "FIFA 24 Cyber Rush 4x4 (3x2 min)",
            "FIFA Liga Pro 5x5 (2x3 min)",
            "EsportsBattle Rush 4x4 Cup"
        ],
        "team_pool": CYBER_CLUBS,
        "avg_goals": 6.8,
        "duration_min": 6
    },
    {
        "format_tag": "PENALTY",
        "game_format": "Tirs au But (Penalties)",
        "competitions": [
            "FIFA 24 Cyber Penalty Shootout",
            "EsportsBattle Penalty Cup",
            "FIFA Cyber Shootout Series"
        ],
        "team_pool": ALL_CYBER_TEAMS,
        "avg_goals": 7.5,
        "duration_min": 3
    },
    {
        "format_tag": "PES",
        "game_format": "eFootball / PES Cyber (10 min)",
        "competitions": [
            "eFootball 2024 Cyber Open Cup (2x5 min)",
            "PES Cyber Masters League (10 min)",
            "eFootball Global eSports"
        ],
        "team_pool": CYBER_CLUBS,
        "avg_goals": 2.2,
        "duration_min": 10
    }
]

TEAM_STRENGTHS = {
    "Real Madrid Cyber": (1.35, 0.85),
    "Manchester City Cyber": (1.40, 0.80),
    "Bayern Munich Cyber": (1.30, 0.90),
    "Paris SG Cyber": (1.25, 0.95),
    "Liverpool Cyber": (1.20, 0.95),
    "Barcelona Cyber": (1.15, 1.00),
    "Arsenal Cyber": (1.10, 1.02),
    "Inter Milan Cyber": (1.05, 1.05),
    "Juventus Cyber": (0.95, 1.10),
    "Chelsea Cyber": (0.92, 1.12),
    "Borussia Dortmund Cyber": (1.00, 1.15),
    "Atletico Madrid Cyber": (0.88, 1.08),
    "France Cyber": (1.35, 0.85),
    "Brazil Cyber": (1.38, 0.88),
    "Argentina Cyber": (1.32, 0.86),
    "England Cyber": (1.22, 0.92),
    "Germany Cyber": (1.18, 0.95),
    "Spain Cyber": (1.16, 0.96),
    "Portugal Cyber": (1.15, 0.98),
    "Italy Cyber": (1.08, 1.02)
}

def seed_database(total_historical: int = 240, upcoming_count: int = 24):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM predictions;")
    cursor.execute("DELETE FROM matches;")
    cursor.execute("DELETE FROM drift_alerts;")
    cursor.execute("DELETE FROM model_versions;")
    
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(days=5)
    ensemble = VirtualAIEnsemblePredictor()

    all_historical = []
    matches_to_insert = []

    # 1. Generate Historical Matches across all formats
    for i in range(total_historical):
        fmt_cfg = FORMAT_CONFIGS[i % len(FORMAT_CONFIGS)]
        match_time = base_time + timedelta(minutes=i * 28)
        bookmaker = random.choice(BOOKMAKERS)
        comp = random.choice(fmt_cfg["competitions"])
        
        home_team, away_team = random.sample(fmt_cfg["team_pool"], 2)
        h_att, h_def = TEAM_STRENGTHS.get(home_team, (1.0, 1.0))
        a_att, a_def = TEAM_STRENGTHS.get(away_team, (1.0, 1.0))

        base_lam = (fmt_cfg["avg_goals"] / 2.0)
        lam = max(0.4, base_lam * h_att * a_def)
        mu = max(0.3, (base_lam * 0.85) * a_att * h_def)

        if fmt_cfg["format_tag"] == "PENALTY":
            # Penalties: standard score 4-3, 5-4, 5-3, 3-2
            home_score = random.randint(3, 5)
            away_score = random.randint(2, 5)
            if home_score == away_score:
                home_score += 1
            ht_hs = home_score // 2
            ht_as = away_score // 2
        else:
            home_score = int(np.random.poisson(lam))
            away_score = int(np.random.poisson(mu))
            ht_hs = int(np.random.binomial(home_score, 0.45))
            ht_as = int(np.random.binomial(away_score, 0.45))

        p_home_true = lam / (lam + mu + 0.8)
        p_away_true = mu / (lam + mu + 0.8)
        p_draw_true = 0.05 if fmt_cfg["format_tag"] == "PENALTY" else max(0.12, 1.0 - (p_home_true + p_away_true))
        margin = 1.07
        
        odd_1 = round(margin / max(0.08, p_home_true), 2)
        odd_x = round(margin / max(0.08, p_draw_true), 2)
        odd_2 = round(margin / max(0.08, p_away_true), 2)

        match_id = f"fifa_hist_{i+1:04d}"
        now_iso = match_time.isoformat()

        record = {
            "id": match_id,
            "bookmaker": bookmaker,
            "game_format": fmt_cfg["game_format"],
            "competition": comp,
            "home_team": home_team,
            "away_team": away_team,
            "match_time": now_iso,
            "status": "FINISHED",
            "home_score": home_score,
            "away_score": away_score,
            "ht_home_score": ht_hs,
            "ht_away_score": ht_as,
            "odds_1": odd_1,
            "odds_x": odd_x,
            "odds_2": odd_2,
            "odds_over25": round(1.68 + random.uniform(-0.1, 0.15), 2),
            "odds_under25": round(2.10 + random.uniform(-0.1, 0.15), 2),
            "odds_btts_yes": round(1.62 + random.uniform(-0.1, 0.12), 2),
            "odds_btts_no": round(2.15 + random.uniform(-0.1, 0.15), 2),
            "source": f"API_{bookmaker.upper()}",
            "validation_status": "VALIDATED",
            "created_at": now_iso,
            "updated_at": now_iso
        }
        all_historical.append(record)
        matches_to_insert.append((
            record["id"], record["bookmaker"], record["game_format"], record["competition"],
            record["home_team"], record["away_team"], record["match_time"], record["status"],
            record["home_score"], record["away_score"], record["ht_home_score"], record["ht_away_score"],
            record["odds_1"], record["odds_x"], record["odds_2"], record["odds_over25"], record["odds_under25"],
            record["odds_btts_yes"], record["odds_btts_no"], record["source"], record["validation_status"],
            record["created_at"], record["updated_at"]
        ))

    cursor.executemany("""
    INSERT INTO matches (
        id, bookmaker, game_format, competition, home_team, away_team,
        match_time, status, home_score, away_score, ht_home_score, ht_away_score,
        odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_btts_yes, odds_btts_no,
        source, validation_status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, matches_to_insert)

    # 2. Train Ensemble Predictor
    print(f"Training ensemble model on {len(all_historical)} multi-format historical matches...")
    ensemble.ml_engine.train_on_history(all_historical)

    # Insert Historical Predictions
    preds_to_insert = []
    for idx, target in enumerate(all_historical[-80:]):
        odds_dict = {"1": target["odds_1"], "x": target["odds_x"], "2": target["odds_2"]}
        pred = ensemble.generate_prediction(
            matches_history=all_historical[:120],
            home_team=target["home_team"],
            away_team=target["away_team"],
            bookmaker=target["bookmaker"],
            competition=target["competition"],
            odds=odds_dict
        )

        p1 = pred["markets"]["1x2"]["home_win"]
        px = pred["markets"]["1x2"]["draw"]
        p2 = pred["markets"]["1x2"]["away_win"]

        hs = target["home_score"]
        as_ = target["away_score"]
        act_1x2 = "1" if hs > as_ else ("2" if as_ > hs else "X")

        main_pick = pred["main_pick"]
        is_hit = False
        if "1" in main_pick["selection"] and act_1x2 == "1": is_hit = True
        elif "2" in main_pick["selection"] and act_1x2 == "2": is_hit = True
        elif "Nul" in main_pick["selection"] and act_1x2 == "X": is_hit = True
        elif "1X" in main_pick["selection"] and act_1x2 in ["1", "X"]: is_hit = True
        elif "X2" in main_pick["selection"] and act_1x2 in ["X", "2"]: is_hit = True
        elif "Plus de 2.5" in main_pick["selection"] and (hs + as_) > 2.5: is_hit = True
        elif "Moins de 2.5" in main_pick["selection"] and (hs + as_) <= 2.5: is_hit = True
        elif "marquent (OUI)" in main_pick["selection"] and (hs > 0 and as_ > 0): is_hit = True

        preds_to_insert.append((
            f"pred_hist_{idx}",
            target["id"],
            pred["model_version"],
            target["match_time"],
            p1, px, p2,
            pred["markets"]["over_under"]["over_1.5"],
            pred["markets"]["over_under"]["under_1.5"],
            pred["markets"]["over_under"]["over_2.5"],
            pred["markets"]["over_under"]["under_2.5"],
            pred["markets"]["over_under"]["over_3.5"],
            pred["markets"]["over_under"]["under_3.5"],
            pred["markets"]["btts"]["yes"],
            pred["markets"]["btts"]["no"],
            pred["markets"]["double_chance"]["1x"],
            pred["markets"]["double_chance"]["12"],
            pred["markets"]["double_chance"]["x2"],
            json.dumps(pred["markets"]["exact_scores"]),
            pred["expected_goals"]["home"],
            pred["expected_goals"]["away"],
            main_pick["market"],
            main_pick["selection"],
            pred["confidence_score"],
            pred["confidence_tier"],
            pred["sample_size_h2h"],
            pred["sample_size_team"],
            json.dumps(pred["reasoning"]["positive_factors"]),
            json.dumps(pred["reasoning"]["negative_factors"]),
            json.dumps(pred["sub_models"]["poisson"]),
            json.dumps(pred["sub_models"]["trend"]),
            json.dumps(pred["sub_models"]["ml"]),
            "HIT" if is_hit else "MISS"
        ))

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
    """, preds_to_insert)

    # 3. Generate 3 LIVE matches + 21 UPCOMING matches across all 4 formats
    sched_matches = []
    sched_preds = []

    # Formats distribution: 2 Live (SIM, RUSH), 1 Live (PES), and Upcoming scheduled chronologically
    for j in range(upcoming_count):
        fmt_cfg = FORMAT_CONFIGS[j % len(FORMAT_CONFIGS)]
        
        # First 3 matches are LIVE right now!
        if j < 3:
            status = "LIVE"
            up_time = now - timedelta(minutes=random.randint(2, 6))
            hs = random.randint(1, 3)
            as_ = random.randint(0, 2)
            ht_hs = hs
            ht_as = as_
        else:
            # Upcoming matches spaced cleanly every 8-15 minutes into the future
            status = "SCHEDULED"
            up_time = now + timedelta(minutes=(j - 2) * 9 + random.randint(1, 4))
            hs, as_, ht_hs, ht_as = None, None, None, None

        bookmaker = random.choice(BOOKMAKERS)
        comp = random.choice(fmt_cfg["competitions"])
        h_team, a_team = random.sample(fmt_cfg["team_pool"], 2)
        h_att, h_def = TEAM_STRENGTHS.get(h_team, (1.0, 1.0))
        a_att, a_def = TEAM_STRENGTHS.get(a_team, (1.0, 1.0))

        base_lam = (fmt_cfg["avg_goals"] / 2.0)
        lam = max(0.4, base_lam * h_att * a_def)
        mu = max(0.3, (base_lam * 0.85) * a_att * h_def)

        p_home_true = lam / (lam + mu + 0.8)
        p_away_true = mu / (lam + mu + 0.8)
        p_draw_true = 0.05 if fmt_cfg["format_tag"] == "PENALTY" else max(0.12, 1.0 - (p_home_true + p_away_true))
        margin = 1.07

        odd_1 = round(margin / max(0.08, p_home_true), 2)
        odd_x = round(margin / max(0.08, p_draw_true), 2)
        odd_2 = round(margin / max(0.08, p_away_true), 2)

        match_id = f"fifa_sched_{j+1:02d}"

        sched_matches.append((
            match_id, bookmaker, fmt_cfg["game_format"], comp,
            h_team, a_team, up_time.isoformat(), status,
            hs, as_, ht_hs, ht_as,
            odd_1, odd_x, odd_2, 1.72, 2.05, 1.65, 2.10,
            f"FEED_{bookmaker.upper()}", "VALIDATED",
            now.isoformat(), now.isoformat()
        ))

        odds_dict = {"1": odd_1, "x": odd_x, "2": odd_2}
        pred = ensemble.generate_prediction(
            matches_history=all_historical,
            home_team=h_team,
            away_team=a_team,
            bookmaker=bookmaker,
            competition=comp,
            odds=odds_dict
        )

        sched_preds.append((
            f"pred_sched_{j+1:02d}",
            match_id,
            pred["model_version"],
            now.isoformat(),
            pred["markets"]["1x2"]["home_win"],
            pred["markets"]["1x2"]["draw"],
            pred["markets"]["1x2"]["away_win"],
            pred["markets"]["over_under"]["over_1.5"],
            pred["markets"]["over_under"]["under_1.5"],
            pred["markets"]["over_under"]["over_2.5"],
            pred["markets"]["over_under"]["under_2.5"],
            pred["markets"]["over_under"]["over_3.5"],
            pred["markets"]["over_under"]["under_3.5"],
            pred["markets"]["btts"]["yes"],
            pred["markets"]["btts"]["no"],
            pred["markets"]["double_chance"]["1x"],
            pred["markets"]["double_chance"]["12"],
            pred["markets"]["double_chance"]["x2"],
            json.dumps(pred["markets"]["exact_scores"]),
            pred["expected_goals"]["home"],
            pred["expected_goals"]["away"],
            pred["main_pick"]["market"],
            pred["main_pick"]["selection"],
            pred["confidence_score"],
            pred["confidence_tier"],
            pred["sample_size_h2h"],
            pred["sample_size_team"],
            json.dumps(pred["reasoning"]["positive_factors"]),
            json.dumps(pred["reasoning"]["negative_factors"]),
            json.dumps(pred["sub_models"]["poisson"]),
            json.dumps(pred["sub_models"]["trend"]),
            json.dumps(pred["sub_models"]["ml"]),
            "PENDING"
        ))

    cursor.executemany("""
    INSERT INTO matches (
        id, bookmaker, game_format, competition, home_team, away_team,
        match_time, status, home_score, away_score, ht_home_score, ht_away_score,
        odds_1, odds_x, odds_2, odds_over25, odds_under25, odds_btts_yes, odds_btts_no,
        source, validation_status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sched_matches)

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
    """, sched_preds)

    # 4. Insert Model Version Metadata
    cursor.execute("""
    INSERT INTO model_versions (
        version, deployed_at, is_active, trained_on_matches,
        brier_score_val, accuracy_1x2, accuracy_over25, accuracy_btts, notes
    ) VALUES (?, ?, 1, ?, 0.178, 0.684, 0.712, 0.695, ?)
    """, (
        "v2.6.0-prod", now.isoformat(), len(all_historical),
        "Multi-Format Ensemble: Poisson Goal Engine + Gradient Logistic ML + Time Decay Weighting"
    ))

    # 5. Insert Drift Alerts
    cursor.execute("""
    INSERT INTO drift_alerts (
        timestamp, bookmaker, competition, metric_name,
        baseline_value, recent_value, sample_size, p_value,
        confidence_level, status, description
    ) VALUES (?, '1xBet', 'FIFA 24 Cyber Rush 4x4 (3x2 min)', 'Over 2.5 Goals Rate',
        0.78, 0.89, 45, 0.038, '95%', 'ACTIVE',
        'Hausse significative de la moyenne de buts détectée sur le format Rush 4x4.'
    )
    """, (now.isoformat(),))

    conn.commit()
    conn.close()
    print("Database multi-format seeding complete!")

if __name__ == "__main__":
    seed_database()
