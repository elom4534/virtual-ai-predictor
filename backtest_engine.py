import numpy as np
from typing import List, Dict, Any, Tuple
import json

class BacktestEvaluationEngine:
    """
    Evaluates predictions against confirmed results.
    Calculates Brier Score, Log Loss, Calibration, Win Rates, and Sub-group segmentations.
    """
    
    @staticmethod
    def evaluate_all(predictions_and_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Accepts list of paired dicts containing prediction and match result.
        """
        valid_items = [
            item for item in predictions_and_matches 
            if item.get("home_score") is not None and item.get("away_score") is not None
        ]

        if not valid_items:
            return {
                "total_evaluated": 0,
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
        
        hits_1x2 = 0
        hits_dc = 0
        hits_o25 = 0
        hits_btts = 0
        hits_exact_top3 = 0

        brier_sum = 0.0
        log_loss_sum = 0.0
        
        # Calibration bins [0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0]
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

        simulated_profit_units = 0.0 # 1 unit stake per main pick

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

            # Determine actual outcome
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

            # Prediction probabilities
            p1 = float(item.get("prob_home_win", 0.40))
            px = float(item.get("prob_draw", 0.25))
            p2 = float(item.get("prob_away_win", 0.35))
            pred_vector = [p1, px, p2]

            # Brier Score for 1X2: sum of (p_k - o_k)^2
            match_brier = sum((pred_vector[k] - actual_vector[k]) ** 2 for k in range(3))
            brier_sum += match_brier
            bookmaker_stats[bookmaker]["brier_sum"] += match_brier

            # Log Loss for 1X2: -ln(p_actual)
            p_actual = max(0.01, min(0.99, pred_vector[0] if hs > as_ else (pred_vector[1] if hs == as_ else pred_vector[2])))
            log_loss_sum += -np.log(p_actual)

            # Check 1X2 Pick
            pred_1x2 = "1" if (p1 >= px and p1 >= p2) else ("X" if px >= p2 else "2")
            if pred_1x2 == actual_1x2:
                hits_1x2 += 1

            # Check Double Chance
            p_1x = float(item.get("prob_dc_1x", p1 + px))
            p_x2 = float(item.get("prob_dc_x2", px + p2))
            if (p_1x >= p_x2 and (actual_1x2 in ["1", "X"])) or (p_x2 > p_1x and (actual_1x2 in ["X", "2"])):
                hits_dc += 1

            # Check Over/Under 2.5
            p_o25 = float(item.get("prob_over25", 0.5))
            pred_o25 = p_o25 >= 0.50
            if pred_o25 == actual_o25:
                hits_o25 += 1

            # Check BTTS
            p_btts = float(item.get("prob_btts_yes", 0.5))
            pred_btts = p_btts >= 0.50
            if pred_btts == actual_btts:
                hits_btts += 1

            # Check Exact score top 3
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

            # Check Main Pick
            main_market = item.get("main_pick_market", "1X2")
            main_selection = item.get("main_pick_selection", "")
            is_main_hit = False

            if "1" in main_selection and actual_1x2 == "1":
                is_main_hit = True
            elif "2" in main_selection and actual_1x2 == "2":
                is_main_hit = True
            elif "Nul" in main_selection and actual_1x2 == "X":
                is_main_hit = True
            elif "1X" in main_selection and actual_1x2 in ["1", "X"]:
                is_main_hit = True
            elif "X2" in main_selection and actual_1x2 in ["X", "2"]:
                is_main_hit = True
            elif "Plus de 2.5" in main_selection and actual_o25:
                is_main_hit = True
            elif "Moins de 2.5" in main_selection and not actual_o25:
                is_main_hit = True
            elif "marquent (OUI)" in main_selection and actual_btts:
                is_main_hit = True

            if is_main_hit:
                hits_main_pick += 1
                bookmaker_stats[bookmaker]["hits"] += 1
                if conf_tier in confidence_stats:
                    confidence_stats[conf_tier]["hits"] += 1
                # Estimate return
                odds_val = item.get("odds_1") if "1 (" in main_selection else 1.85
                simulated_profit_units += ((odds_val or 1.85) - 1.0)
            else:
                simulated_profit_units -= 1.0

            # Calibration binning on predicted main prob
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

        # Summarize by bookmaker
        by_bm = {}
        for bm, st in bookmaker_stats.items():
            by_bm[bm] = {
                "total_matches": st["total"],
                "win_rate": round(st["hits"] / st["total"], 3) if st["total"] > 0 else 0.0,
                "brier_score": round(st["brier_sum"] / st["total"], 3) if st["total"] > 0 else 0.0
            }

        # Summarize by confidence
        by_conf = {}
        for ctier, st in confidence_stats.items():
            by_conf[ctier] = {
                "total_matches": st["total"],
                "win_rate": round(st["hits"] / st["total"], 3) if st["total"] > 0 else 0.0
            }

        roi_pct = round((simulated_profit_units / total_n) * 100, 2)

        return {
            "total_evaluated": total_n,
            "win_rate_main_pick": round(hits_main_pick / total_n, 3),
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
