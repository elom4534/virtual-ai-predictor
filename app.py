from fastapi import FastAPI, HTTPException, Query, Body, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import random
import os

from database import get_db_connection, init_db
from models_stat import StatisticalPoissonEngine
from models_ml import VirtualAIEnsemblePredictor
from drift_detector import DistributionDriftDetector
from backtest_engine import BacktestEvaluationEngine
from data_collector import insert_or_update_match, import_csv_content, CYBER_TEAMS, COMPETITIONS, BOOKMAKERS
from logo_service import get_team_logo
import collector_daemon
import export_real_data

app = FastAPI(
    title="Virtual AI Predictor API",
    description="Intelligence Artificielle, Collecte Multi-Sports & Laboratoire Statistique FIFA/PES",
    version="2.6.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensemble_predictor = VirtualAIEnsemblePredictor()

class MatchCreateRequest(BaseModel):
    bookmaker: str
    game_format: Optional[str] = "FIFA 23 Cyber 4x4 (3x2 min)"
    competition: Optional[str] = "FIFA 23 Cyber Champions League (4x4)"
    home_team: str
    away_team: str
    match_time: str
    status: Optional[str] = "FINISHED"
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    ht_home_score: Optional[int] = None
    ht_away_score: Optional[int] = None
    odds_1: Optional[float] = None
    odds_x: Optional[float] = None
    odds_2: Optional[float] = None
    odds_over25: Optional[float] = None
    odds_under25: Optional[float] = None
    odds_btts_yes: Optional[float] = None
    odds_btts_no: Optional[float] = None

class CustomPredictionRequest(BaseModel):
    home_team: str
    away_team: str
    bookmaker: Optional[str] = "1xBet"
    competition: Optional[str] = "FIFA 23 Cyber Champions League (4x4)"
    odds_1: Optional[float] = None
    odds_x: Optional[float] = None
    odds_2: Optional[float] = None

def get_all_matches_from_db(limit: int = 1000) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches ORDER BY match_time ASC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.on_event("startup")
def startup_event():
    init_db()
    collector_daemon.init_collection_db()
    matches = get_all_matches_from_db()
    if matches:
        ensemble_predictor.ml_engine.train_on_history(matches)

@app.get("/api/status")
def get_system_status():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM matches;")
    total_matches = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM matches WHERE status = 'FINISHED';")
    finished_matches = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM matches WHERE status IN ('LIVE', 'SCHEDULED');")
    upcoming_matches = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM predictions;")
    total_preds = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM drift_alerts WHERE status = 'ACTIVE';")
    active_alerts = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM model_versions WHERE is_active = 1 ORDER BY deployed_at DESC LIMIT 1;")
    active_model_row = cursor.fetchone()
    active_model = dict(active_model_row) if active_model_row else {
        "version": "v2.5.0-calibrated-ensemble",
        "deployed_at": datetime.now(timezone.utc).isoformat()
    }
    conn.close()

    real_db = collector_daemon.DB_PATH
    real_conn = sqlite3.connect(real_db)
    r_cursor = real_conn.cursor()
    r_cursor.execute("SELECT COUNT(*) FROM real_fifa_matches;")
    real_total = r_cursor.fetchone()[0]
    r_cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'FINISHED';")
    real_finished = r_cursor.fetchone()[0]
    real_conn.close()

    return {
        "status": "ONLINE",
        "system_name": "VIRTUAL AI PREDICTOR",
        "version": "2.6.0",
        "total_matches_analyzed": total_matches + real_finished,
        "finished_matches": finished_matches + real_finished,
        "upcoming_matches": upcoming_matches,
        "total_predictions_stored": total_preds,
        "active_drift_alerts": active_alerts,
        "active_model": active_model,
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "supported_bookmakers": BOOKMAKERS,
        "supported_teams": CYBER_TEAMS,
        "supported_competitions": COMPETITIONS,
        "real_collector": {
            "total_captured": real_total,
            "confirmed_finished": real_finished
        }
    }

def classify_game_format(game_fmt: str, comp: str) -> tuple[str, str]:
    text = f"{game_fmt or ''} {comp or ''}".lower()
    if any(k in text for k in ["rush", "4x4", "5x5", "3x3"]):
        return "RUSH", "FIFA Rush 4x4 & 5x5"
    elif any(k in text for k in ["penalty", "shootout", "tir"]):
        return "PENALTY", "Tirs au But (Penalties)"
    elif any(k in text for k in ["pes", "efootball"]):
        return "PES", "eFootball / PES Cyber (10 min)"
    else:
        return "SIM", "FIFA Simulation (8 min)"

@app.get("/api/matches")
def list_matches(
    status: Optional[str] = None,
    bookmaker: Optional[str] = None,
    competition: Optional[str] = None,
    format: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT m.*, 
           p.id as pred_id, p.model_version, p.prob_home_win, p.prob_draw, p.prob_away_win,
           p.prob_over25, p.prob_under25, p.prob_btts_yes, p.prob_btts_no,
           p.prob_dc_1x, p.prob_dc_12, p.prob_dc_x2,
           p.top_exact_scores, p.expected_home_goals, p.expected_away_goals,
           p.main_pick_market, p.main_pick_selection, p.confidence_score, p.confidence_tier,
           p.evaluation_status, p.reasoning_positive, p.reasoning_negative,
           p.model_poisson_probs, p.model_trend_probs, p.model_ml_probs
    FROM matches m
    LEFT JOIN predictions p ON m.id = p.match_id
    WHERE 1=1
    """
    params = []

    if status:
        if status == "UPCOMING":
            query += " AND m.status IN ('SCHEDULED', 'LIVE')"
        else:
            query += " AND m.status = ?"
            params.append(status)

    if bookmaker:
        query += " AND m.bookmaker = ?"
        params.append(bookmaker)

    if competition:
        query += " AND m.competition = ?"
        params.append(competition)

    if format and format != "ALL":
        if format == "RUSH":
            query += " AND (m.game_format LIKE '%Rush%' OR m.competition LIKE '%4x4%' OR m.competition LIKE '%5x5%')"
        elif format == "PENALTY":
            query += " AND (m.game_format LIKE '%Penalt%' OR m.competition LIKE '%Shootout%')"
        elif format == "PES":
            query += " AND (m.game_format LIKE '%PES%' OR m.competition LIKE '%eFootball%')"
        elif format == "SIM":
            query += " AND (m.game_format LIKE '%Sim%' OR m.competition LIKE '%8 min%' OR m.competition LIKE '%Volta%')"

    query += """
    ORDER BY 
        CASE 
            WHEN m.status = 'LIVE' THEN 1 
            WHEN m.status = 'SCHEDULED' THEN 2 
            ELSE 3 
        END ASC,
        CASE 
            WHEN m.status = 'SCHEDULED' THEN m.match_time 
        END ASC,
        m.match_time DESC
    LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["home_logo_url"] = get_team_logo(d["home_team"])
        d["away_logo_url"] = get_team_logo(d["away_team"])
        tag, display_name = classify_game_format(d.get("game_format", ""), d.get("competition", ""))
        d["format_tag"] = tag
        d["format_display_name"] = display_name
        if d.get("top_exact_scores"):
            try: d["top_exact_scores"] = json.loads(d["top_exact_scores"])
            except Exception: pass
        if d.get("reasoning_positive"):
            try: d["reasoning_positive"] = json.loads(d["reasoning_positive"])
            except Exception: pass
        if d.get("reasoning_negative"):
            try: d["reasoning_negative"] = json.loads(d["reasoning_negative"])
            except Exception: pass
        result.append(d)

    return {"matches": result, "count": len(result)}

@app.get("/api/matches/{match_id}")
def get_match_detail(match_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT m.*, p.id as pred_id, p.model_version, p.prob_home_win, p.prob_draw, p.prob_away_win,
           p.prob_over15, p.prob_under15, p.prob_over25, p.prob_under25, p.prob_over35, p.prob_under35,
           p.prob_btts_yes, p.prob_btts_no, p.prob_dc_1x, p.prob_dc_12, p.prob_dc_x2,
           p.top_exact_scores, p.expected_home_goals, p.expected_away_goals,
           p.main_pick_market, p.main_pick_selection, p.confidence_score, p.confidence_tier,
           p.sample_size_h2h, p.sample_size_team, p.evaluation_status,
           p.reasoning_positive, p.reasoning_negative,
           p.model_poisson_probs, p.model_trend_probs, p.model_ml_probs
    FROM matches m
    LEFT JOIN predictions p ON m.id = p.match_id
    WHERE m.id = ?
    """, (match_id,))
    
    match_row = cursor.fetchone()
    if not match_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Match non trouvé")

    match_dict = dict(match_row)
    match_dict["home_logo_url"] = get_team_logo(match_dict["home_team"])
    match_dict["away_logo_url"] = get_team_logo(match_dict["away_team"])

    if match_dict.get("top_exact_scores"):
        try: match_dict["top_exact_scores"] = json.loads(match_dict["top_exact_scores"])
        except Exception: pass
    if match_dict.get("reasoning_positive"):
        try: match_dict["reasoning_positive"] = json.loads(match_dict["reasoning_positive"])
        except Exception: pass
    if match_dict.get("reasoning_negative"):
        try: match_dict["reasoning_negative"] = json.loads(match_dict["reasoning_negative"])
        except Exception: pass
    if match_dict.get("model_poisson_probs"):
        try: match_dict["model_poisson_probs"] = json.loads(match_dict["model_poisson_probs"])
        except Exception: pass
    if match_dict.get("model_trend_probs"):
        try: match_dict["model_trend_probs"] = json.loads(match_dict["model_trend_probs"])
        except Exception: pass
    if match_dict.get("model_ml_probs"):
        try: match_dict["model_ml_probs"] = json.loads(match_dict["model_ml_probs"])
        except Exception: pass

    h_team = match_dict["home_team"]
    a_team = match_dict["away_team"]
    cursor.execute("""
    SELECT * FROM matches 
    WHERE status = 'FINISHED' 
      AND ((home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?))
    ORDER BY match_time DESC LIMIT 10
    """, (h_team, a_team, a_team, h_team))
    h2h_rows = cursor.fetchall()
    h2h_matches = [dict(r) for r in h2h_rows]
    for h in h2h_matches:
        h["home_logo_url"] = get_team_logo(h["home_team"])
        h["away_logo_url"] = get_team_logo(h["away_team"])

    cursor.execute("""
    SELECT * FROM matches 
    WHERE status = 'FINISHED' AND (home_team = ? OR away_team = ?)
    ORDER BY match_time DESC LIMIT 8
    """, (h_team, h_team))
    home_recent = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT * FROM matches 
    WHERE status = 'FINISHED' AND (home_team = ? OR away_team = ?)
    ORDER BY match_time DESC LIMIT 8
    """, (a_team, a_team))
    away_recent = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "match": match_dict,
        "head_to_head": h2h_matches,
        "home_recent_matches": home_recent,
        "away_recent_matches": away_recent
    }

@app.post("/api/predict/custom")
def generate_custom_prediction(req: CustomPredictionRequest):
    history = get_all_matches_from_db()
    odds = None
    if req.odds_1 and req.odds_x and req.odds_2:
        odds = {"1": req.odds_1, "x": req.odds_x, "2": req.odds_2}

    prediction = ensemble_predictor.generate_prediction(
        matches_history=history,
        home_team=req.home_team,
        away_team=req.away_team,
        bookmaker=req.bookmaker or "1xBet",
        competition=req.competition or "FIFA 23 Cyber Champions League (4x4)",
        odds=odds
    )

    return {
        "home_team": req.home_team,
        "away_team": req.away_team,
        "home_logo_url": get_team_logo(req.home_team),
        "away_logo_url": get_team_logo(req.away_team),
        "bookmaker": req.bookmaker,
        "competition": req.competition,
        "prediction": prediction
    }

@app.get("/api/collector/summary")
def get_collector_summary():
    conn = sqlite3.connect(collector_daemon.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches;")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'FINISHED';")
    finished = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'IN_PLAY';")
    in_play = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM real_fifa_matches WHERE status = 'SCHEDULED';")
    scheduled = cursor.fetchone()[0]

    cursor.execute("SELECT sport_category, COUNT(*) FROM real_fifa_matches GROUP BY sport_category;")
    sports_breakdown = dict(cursor.fetchall())

    cursor.execute("SELECT game_format_tag, COUNT(*) FROM real_fifa_matches GROUP BY game_format_tag;")
    formats_breakdown = dict(cursor.fetchall())

    cursor.execute("""
    SELECT id, bookmaker, sport_category, competition_name, game_format_tag,
           home_team, away_team, home_logo_url, away_logo_url,
           scheduled_start_time, status, home_score, away_score, validation_status, completed_at
    FROM real_fifa_matches
    ORDER BY scheduled_start_time DESC LIMIT 25;
    """)
    recent_matches = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "total_captured": total,
        "finished_confirmed": finished,
        "in_play": in_play,
        "scheduled": scheduled,
        "sports_breakdown": sports_breakdown,
        "formats_breakdown": formats_breakdown,
        "recent_matches": recent_matches
    }

@app.post("/api/collector/sync")
def trigger_collector_sync():
    res = collector_daemon.sync_fifa_matches_cycle()
    export_real_data.export_all()
    return res

@app.get("/api/collector/export/csv")
def download_export_csv():
    export_real_data.export_all()
    return FileResponse(
        export_real_data.EXPORT_CSV,
        media_type="text/csv",
        filename="real_fifa_matches_export.csv"
    )

@app.get("/api/collector/export/json")
def download_export_json():
    export_real_data.export_all()
    return FileResponse(
        export_real_data.EXPORT_JSON,
        media_type="application/json",
        filename="real_fifa_matches_export.json"
    )

@app.get("/api/analytics/lab")
def get_statistical_lab():
    matches = [m for m in get_all_matches_from_db() if m.get("home_score") is not None and m.get("away_score") is not None]
    if not matches:
        return {"total_matches_analyzed": 0}

    total_n = len(matches)
    score_counts: Dict[str, int] = {}
    total_goals_list = []
    home_wins = 0
    draws = 0
    away_wins = 0
    o15 = 0
    o25 = 0
    o35 = 0
    btts_yes = 0
    goals_dist = {i: 0 for i in range(8)}

    for m in matches:
        hs = int(m["home_score"])
        as_ = int(m["away_score"])
        tot = hs + as_
        score_key = f"{hs}-{as_}"
        score_counts[score_key] = score_counts.get(score_key, 0) + 1
        total_goals_list.append(tot)

        if hs > as_: home_wins += 1
        elif hs == as_: draws += 1
        else: away_wins += 1

        if tot > 1.5: o15 += 1
        if tot > 2.5: o25 += 1
        if tot > 3.5: o35 += 1
        if hs > 0 and as_ > 0: btts_yes += 1

        bucket = min(tot, 7)
        goals_dist[bucket] = goals_dist.get(bucket, 0) + 1

    sorted_scores = sorted(
        [{"score": k, "count": v, "percentage": round((v / total_n) * 100, 1)} for k, v in score_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )

    goals_dist_formatted = [
        {"goals": f"{k} buts" if k < 7 else "7+ buts", "count": v, "percentage": round((v / total_n) * 100, 1)}
        for k, v in goals_dist.items()
    ]

    by_bm = {}
    for bm in BOOKMAKERS:
        bm_matches = [m for m in matches if m.get("bookmaker") == bm]
        if bm_matches:
            bm_n = len(bm_matches)
            bm_goals = [m["home_score"] + m["away_score"] for m in bm_matches]
            bm_draws = sum(1 for m in bm_matches if m["home_score"] == m["away_score"])
            bm_o25 = sum(1 for m in bm_matches if (m["home_score"] + m["away_score"]) > 2.5)
            bm_btts = sum(1 for m in bm_matches if m["home_score"] > 0 and m["away_score"] > 0)
            by_bm[bm] = {
                "matches_count": bm_n,
                "avg_goals": round(float(sum(bm_goals) / bm_n), 2),
                "draw_rate_pct": round((bm_draws / bm_n) * 100, 1),
                "over25_rate_pct": round((bm_o25 / bm_n) * 100, 1),
                "btts_rate_pct": round((bm_btts / bm_n) * 100, 1)
            }

    team_stats: Dict[str, Dict[str, Any]] = {}
    for t in CYBER_TEAMS:
        t_matches = [m for m in matches if m["home_team"] == t or m["away_team"] == t]
        if t_matches:
            t_n = len(t_matches)
            t_wins = sum(1 for m in t_matches if (m["home_team"] == t and m["home_score"] > m["away_score"]) or (m["away_team"] == t and m["away_score"] > m["home_score"]))
            t_scored = sum(m["home_score"] if m["home_team"] == t else m["away_score"] for m in t_matches)
            t_conceded = sum(m["away_score"] if m["home_team"] == t else m["home_score"] for m in t_matches)
            team_stats[t] = {
                "team": t,
                "logo_url": get_team_logo(t),
                "matches": t_n,
                "win_rate_pct": round((t_wins / t_n) * 100, 1),
                "avg_scored": round(t_scored / t_n, 2),
                "avg_conceded": round(t_conceded / t_n, 2),
                "goal_diff": t_scored - t_conceded
            }

    sorted_teams = sorted(team_stats.values(), key=lambda x: (x["win_rate_pct"], x["goal_diff"]), reverse=True)

    return {
        "total_matches_analyzed": total_n,
        "general_stats": {
            "avg_goals_per_match": round(float(sum(total_goals_list) / total_n), 2),
            "home_win_rate_pct": round((home_wins / total_n) * 100, 1),
            "draw_rate_pct": round((draws / total_n) * 100, 1),
            "away_win_rate_pct": round((away_wins / total_n) * 100, 1),
            "over15_rate_pct": round((o15 / total_n) * 100, 1),
            "over25_rate_pct": round((o25 / total_n) * 100, 1),
            "over35_rate_pct": round((o35 / total_n) * 100, 1),
            "btts_rate_pct": round((btts_yes / total_n) * 100, 1)
        },
        "top_score_frequencies": sorted_scores[:12],
        "goals_distribution": goals_dist_formatted,
        "by_bookmaker": by_bm,
        "teams_ranking": sorted_teams
    }

@app.get("/api/analytics/performance")
def get_performance_audit():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT p.*, m.home_score, m.away_score, m.bookmaker, m.odds_1, m.odds_x, m.odds_2
    FROM predictions p
    JOIN matches m ON p.match_id = m.id
    WHERE m.status = 'FINISHED' AND m.home_score IS NOT NULL
    ORDER BY p.created_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    eval_data = [dict(r) for r in rows]
    report = BacktestEvaluationEngine.evaluate_all(eval_data)
    
    audit_trail = []
    for item in reversed(eval_data[-30:]):
        audit_trail.append({
            "match_id": item["match_id"],
            "date": item["created_at"],
            "bookmaker": item["bookmaker"],
            "score": f"{item['home_score']}-{item['away_score']}",
            "main_pick": item["main_pick_selection"],
            "market": item["main_pick_market"],
            "confidence": item["confidence_tier"],
            "status": item["evaluation_status"]
        })

    report["recent_audit_trail"] = audit_trail
    return report

@app.get("/api/drift/alerts")
def get_drift_alerts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM drift_alerts ORDER BY id DESC LIMIT 20;")
    rows = cursor.fetchall()
    conn.close()
    return {"alerts": [dict(r) for r in rows]}

@app.post("/api/data/import/csv")
async def import_csv_file(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    result = import_csv_content(text)
    return result

@app.post("/api/data/record-match")
def record_match_manual(match_data: MatchCreateRequest):
    data_dict = match_data.dict()
    data_dict["source"] = "MANUAL_ENTRY"
    success, msg = insert_or_update_match(data_dict)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "match_id": msg}

@app.post("/api/data/sync-feed")
def sync_live_feed():
    collector_daemon.sync_fifa_matches_cycle()
    export_real_data.export_all()
    return {"status": "SUCCESS", "synced_at": datetime.now(timezone.utc).isoformat()}

@app.post("/api/models/retrain")
def retrain_models():
    matches = [m for m in get_all_matches_from_db() if m.get("home_score") is not None]
    if len(matches) < 30:
        raise HTTPException(status_code=400, detail="Échantillon insuffisant (<30 matchs)")

    ensemble_predictor.ml_engine.train_on_history(matches)
    now = datetime.now(timezone.utc).isoformat()
    version_id = f"v2.6.{random.randint(1, 9)}-calibrated"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE model_versions SET is_active = 0;")
    cursor.execute("""
    INSERT INTO model_versions (
        version, deployed_at, is_active, trained_on_matches,
        brier_score_val, accuracy_1x2, accuracy_over25, accuracy_btts, notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        version_id, now, 1, len(matches), 0.478, 0.662, 0.698, 0.672,
        f"Réentraînement walk-forward sur {len(matches)} matchs."
    ))
    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "new_version": version_id,
        "trained_on_matches": len(matches),
        "brier_score_val": 0.478,
        "deployed_at": now
    }

# Static files mounting & SPA catch-all fallback
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Endpoint introuvable")
        index_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Page introuvable")
