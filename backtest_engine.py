import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import json
import re

def evaluate_market_selection(
    market_type: Optional[str], 
    selection: Optional[str], 
    home_score: Any, 
    away_score: Any
) -> Optional[bool]:
    """
    Deterministic evaluation of any market selection against confirmed match scores.
    Returns:
      - True  : WIN / HIT
      - False : LOSS / MISS
      - None  : UNRECOGNIZED_MARKET / EXCLUDED (does not penalize as a loss)
    """
    if market_type is None or selection is None:
        return None

    try:
        hs = int(home_score)
        as_ = int(away_score)
    except (ValueError, TypeError):
        return None

    total_goals = hs + as_
    m_type = str(market_type).strip().upper()
    sel = str(selection).strip()

    if not sel:
        return None

    if m_type in ["1X2", "MATCH_WINNER"]:
        if sel.startswith(("1X", "12", "X2")):
            return None
        if sel == "1" or sel.startswith("1 (") or "Victoire Domicile" in sel or "(1)" in sel or "(1" in sel:
            return hs > as_
        elif sel == "X" or sel == "Nul" or sel.startswith("X (") or "Match Nul" in sel or "(X)" in sel or "(X" in sel:
            return hs == as_
        elif sel == "2" or sel.startswith("2 (") or "Victoire Extérieur" in sel or "(2)" in sel or "(2" in sel:
            return as_ > hs
        return None

    elif m_type in ["DOUBLE_CHANCE", "DC"]:
        if sel == "1X" or sel.startswith("1X (") or sel.startswith("1X "):
            return hs >= as_
        elif sel == "X2" or sel.startswith("X2 (") or sel.startswith("X2 "):
            return as_ >= hs
        elif sel == "12" or sel.startswith("12 (") or sel.startswith("12 "):
            return hs != as_
        return None

    elif m_type in ["OVER_UNDER_2.5", "OVER_UNDER", "TOTALS"]:
        if re.search(r'\b(Plus de|Over|>)\s*2\.5\b', sel, re.IGNORECASE) or "Plus de 2.5" in sel or "Over 2.5" in sel:
            return total_goals > 2.5
        elif re.search(r'\b(Moins de|Under|<)\s*2\.5\b', sel, re.IGNORECASE) or "Moins de 2.5" in sel or "Under 2.5" in sel:
            return total_goals < 2.5
        return None

    elif m_type in ["BTTS", "BOTH_TEAMS_TO_SCORE"]:
        if re.search(r'\b(OUI|YES)\b', sel, re.IGNORECASE) or "(OUI)" in sel.upper() or "(YES)" in sel.upper():
            return hs > 0 and as_ > 0
        elif re.search(r'\b(NON|NO)\b', sel, re.IGNORECASE) or "(NON)" in sel.upper() or "(NO)" in sel.upper():
            return hs == 0 or as_ == 0
        return None

    return None

class BacktestEvaluationEngine:
    """
    Evaluates predictions against confirmed results.
    Calculates Brier Score, Log Loss, Calibration, Win Rates, and Sub-group segmentations.
    """
    
    @staticmethod
    def evaluate_all(predictions_and_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid_items = [
            item for item in predictions_and_matches 
            if item.get("home_score") is not None and item.get("away_score") is not None
        ]

        if not valid_items:
            return {
                "total_evaluated": 0,
                "total_excluded": 0,
                "win_rate_main_pick": 0.0,
                "brier_score_1x2": 0.0,
                "log_loss_1x2": 0.0,
                "markets_accuracy": {},
                "by_bookmaker": {},
                "by_confidence": {},
                "calibration_curve": [],
                "roi_simulation": 0.0
            }

        total_n = len(valid_items)
        hits_main_pick = 0
        evaluated_main_picks = 0
        excluded_main_picks = 0
        
        hits_1x2 = 0
        hits_dc = 0
        hits_o25 = 0
        hits_btts = 0
        hits_exact_top3 = 0

        brier_sum = 0.0
        log_loss_sum = 0.0
        
        bins = [
            {"min": 0.0, "max": 0.2, "count": 0, "predicted_sum": 0.0, "observed_hits": 0},
            {"min": 0.2, "max": 0.4, "count": 0, "predicted_sum": 0.0, "observed_hits": 0},
            {"min": 0.4, "max": 0.6, "count": 0, "predicted_sum": 0.0, "observed_hits": 0},
            {"min": 0.6, "max": 0.8, "count": 0, "predicted_sum": 0.0, "observed_hits": 0},
            {"min": 0.8, "max": 1.0, "count": 0, "predicted_sum": 0.0, "observed_hits": 0}
        ]

        bookmaker_stats: Dict[str, Dict[str, Any]] = {}
        confidence_stats: Dict[str, Dict[str, Any]] = {
            "HIGH": {"total": 0, "hits": 0},
            "MEDIUM": {"total": 0, "hits": 0},
            "LOW": {"total": 0, "hits": 0},
            "INSUFFICIENT_DATA": {"total": 0, "hits": 0}
        }

        simulated_profit_units = 0.0

        for item in valid_items:
            hs = int(item["home_score"])
            as_ = int(item["away_score"])
            bookmaker = item.get("bookmaker", "1xBet")
            conf_tier = item.get("confidence_tier", "MEDIUM")

            if bookmaker not in bookmaker_stats:
                bookmaker_stats[bookmaker] = {"total": 0, "hits": 0, "brier_sum": 0.0}

            bookmaker_stats[bookmaker]["total"] += 1
            if conf_tier in confidence_stats:
                confidence_stats[conf_tier]["total"] += 1

            if hs > as_:
                actual_1x2 = "1"
                actual_vector = [1.0, 0.0, 0.0]
            elif hs == as_:
                actual_1x2 = "X"
                actual_vector = [0.0, 1.0, 0.0]
            else:
                actual_1x2 = "2"
                actual_vector = [0.0, 0.0, 1.0]

            actual_o25 = (hs + as_) > 2.5
            actual_btts = (hs > 0 and as_ > 0)
            actual_score_str = f"{hs}-{as_}"

            p1 = float(item.get("prob_home_win", 0.40))
            px = float(item.get("prob_draw", 0.25))
            p2 = float(item.get("prob_away_win", 0.35))
            pred_vector = [p1, px, p2]

            match_brier = sum((pred_vector[k] - actual_vector[k]) ** 2 for k in range(3))
            brier_sum += match_brier
            bookmaker_stats[bookmaker]["brier_sum"] += match_brier

            p_actual = max(0.01, min(0.99, pred_vector[0] if hs > as_ else (pred_vector[1] if hs == as_ else pred_vector[2])))
            log_loss_sum += -np.log(p_actual)

            pred_1x2 = "1" if (p1 >= px and p1 >= p2) else ("X" if px >= p2 else "2")
            if pred_1x2 == actual_1x2:
                hits_1x2 += 1

            p_1x = float(item.get("prob_dc_1x", p1 + px))
            p_x2 = float(item.get("prob_dc_x2", px + p2))
            if (p_1x >= p_x2 and (actual_1x2 in ["1", "X"])) or (p_x2 > p_1x and (actual_1x2 in ["X", "2"])):
                hits_dc += 1

            p_o25 = float(item.get("prob_over25", 0.5))
            pred_o25 = p_o25 >= 0.50
            if pred_o25 == actual_o25:
                hits_o25 += 1

            p_btts = float(item.get("prob_btts_yes", 0.5))
            pred_btts = p_btts >= 0.50
            if pred_btts == actual_btts:
                hits_btts += 1

            top_scores_raw = item.get("top_exact_scores")
            if isinstance(top_scores_raw, str):
                try:
                    top_scores = json.loads(top_scores_raw)
                except Exception:
                    top_scores = []
            elif isinstance(top_scores_raw, list):
                top_scores = top_scores_raw
            else:
                top_scores = []

            top_scores_str = [s.get("score") for s in top_scores[:3]]
            if actual_score_str in top_scores_str:
                hits_exact_top3 += 1

            # Strict main pick evaluation using deterministic market handler
            main_market = item.get("main_pick_market", "1X2")
            main_selection = item.get("main_pick_selection", "")
            is_main_hit = evaluate_market_selection(main_market, main_selection, hs, as_)

            if is_main_hit is True:
                hits_main_pick += 1
                evaluated_main_picks += 1
                bookmaker_stats[bookmaker]["hits"] += 1
                if conf_tier in confidence_stats:
                    confidence_stats[conf_tier]["hits"] += 1
                odds_val = item.get("odds_1") if "1 (" in main_selection else 1.85
                simulated_profit_units += ((odds_val or 1.85) - 1.0)
            elif is_main_hit is False:
                evaluated_main_picks += 1
                simulated_profit_units -= 1.0
            else:
                # UNRECOGNIZED / EXCLUDED - not counted in evaluated denominator
                excluded_main_picks += 1

            pred_conf = max(p1, px, p2)
            obs_val = 1 if pred_1x2 == actual_1x2 else 0
            for b in bins:
                if b["min"] <= pred_conf < b["max"] or (b["max"] == 1.0 and pred_conf == 1.0):
                    b["count"] += 1
                    b["predicted_sum"] += pred_conf
                    b["observed_hits"] += obs_val
                    break

        calibration_curve = []
        for b in bins:
            if b["count"] > 0:
                calibration_curve.append({
                    "bin_range": f"{int(b['min']*100)}-{int(b['max']*100)}%",
                    "count": b["count"],
                    "avg_predicted": round(b["predicted_sum"] / b["count"], 3),
                    "empirical_win_rate": round(b["observed_hits"] / b["count"], 3)
                })

        by_bm = {}
        for bm, st in bookmaker_stats.items():
            by_bm[bm] = {
                "total_matches": st["total"],
                "win_rate": round(st["hits"] / st["total"], 3) if st["total"] > 0 else 0.0,
                "brier_score": round(st["brier_sum"] / st["total"], 3) if st["total"] > 0 else 0.0
            }

        by_conf = {}
        for ctier, st in confidence_stats.items():
            by_conf[ctier] = {
                "total_matches": st["total"],
                "win_rate": round(st["hits"] / st["total"], 3) if st["total"] > 0 else 0.0
            }

        denom = evaluated_main_picks if evaluated_main_picks > 0 else 1
        roi_pct = round((simulated_profit_units / denom) * 100, 2)

        return {
            "total_evaluated": evaluated_main_picks,
            "total_excluded": excluded_main_picks,
            "win_rate_main_pick": round(hits_main_pick / denom, 3),
            "brier_score_1x2": round(brier_sum / total_n, 3),
            "log_loss_1x2": round(log_loss_sum / total_n, 3),
            "roi_simulation_pct": roi_pct,
            "markets_accuracy": {
                "1x2": round(hits_1x2 / total_n, 3),
                "double_chance": round(hits_dc / total_n, 3),
                "over_under_2.5": round(hits_o25 / total_n, 3),
                "btts": round(hits_btts / total_n, 3),
                "exact_score_top3": round(hits_exact_top3 / total_n, 3)
            },
            "by_bookmaker": by_bm,
            "by_confidence": by_conf,
            "calibration_curve": calibration_curve
        }
