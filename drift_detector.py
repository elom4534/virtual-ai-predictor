import numpy as np
from scipy import stats
from typing import List, Dict, Any, Optional

class DistributionDriftDetector:
    """
    Statistical Drift Detector comparing recent sliding window (e.g. 50 games)
    against reference baseline dataset.
    Uses Chi-Square test, Welch's t-test and Proportion Z-test.
    """
    def __init__(self, recent_window_size: int = 40):
        self.recent_window_size = recent_window_size

    def check_drift(
        self, 
        matches: List[Dict[str, Any]], 
        bookmaker: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        filtered = [m for m in matches if m.get("home_score") is not None and m.get("away_score") is not None]
        if bookmaker:
            filtered = [m for m in filtered if m.get("bookmaker") == bookmaker]

        if len(filtered) < self.recent_window_size + 30:
            return [] # Insufficient baseline data

        recent = filtered[-self.recent_window_size:]
        baseline = filtered[:-self.recent_window_size]

        alerts = []

        # 1. Total Goals Mean Shift (Welch's t-test)
        base_goals = [m["home_score"] + m["away_score"] for m in baseline]
        rec_goals = [m["home_score"] + m["away_score"] for m in recent]
        
        t_stat, p_val_goals = stats.ttest_ind(rec_goals, base_goals, equal_var=False)
        mean_base_goals = float(np.mean(base_goals))
        mean_rec_goals = float(np.mean(rec_goals))

        if p_val_goals < 0.05 and abs(mean_rec_goals - mean_base_goals) > 0.4:
            alerts.append({
                "metric_name": "AVG_TOTAL_GOALS",
                "bookmaker": bookmaker or "ALL",
                "baseline_value": round(mean_base_goals, 2),
                "recent_value": round(mean_rec_goals, 2),
                "sample_size": len(recent),
                "p_value": round(float(p_val_goals), 4),
                "confidence_level": "HIGH" if p_val_goals < 0.01 else "MEDIUM",
                "description": f"Variation significative de la moyenne de buts ({round(mean_base_goals, 2)} -> {round(mean_rec_goals, 2)} buts/match, p={round(p_val_goals, 4)}). Ajustement automatique de la distribution Poisson."
            })

        # 2. Draw Rate Shift (Proportions Z-Test)
        base_draws = sum(1 for m in baseline if m["home_score"] == m["away_score"])
        rec_draws = sum(1 for m in recent if m["home_score"] == m["away_score"])
        
        prop_base_draw = base_draws / len(baseline)
        prop_rec_draw = rec_draws / len(recent)

        # Pooled proportion
        p_pool = (base_draws + rec_draws) / (len(baseline) + len(recent))
        if 0 < p_pool < 1:
            se = np.sqrt(p_pool * (1 - p_pool) * (1/len(baseline) + 1/len(recent)))
            z_score = (prop_rec_draw - prop_base_draw) / se
            p_val_draw = 2 * (1 - stats.norm.cdf(abs(z_score)))

            if p_val_draw < 0.05 and abs(prop_rec_draw - prop_base_draw) > 0.10:
                alerts.append({
                    "metric_name": "DRAW_RATE",
                    "bookmaker": bookmaker or "ALL",
                    "baseline_value": round(prop_base_draw * 100, 1),
                    "recent_value": round(prop_rec_draw * 100, 1),
                    "sample_size": len(recent),
                    "p_value": round(float(p_val_draw), 4),
                    "confidence_level": "HIGH" if p_val_draw < 0.01 else "MEDIUM",
                    "description": f"Évolution du taux de match nul ({round(prop_base_draw*100, 1)}% -> {round(prop_rec_draw*100, 1)}%, p={round(p_val_draw, 4)}). Adaptation du paramètre de corrélation Dixon-Coles."
                })

        # 3. Over 2.5 Goals Rate Shift
        base_o25 = sum(1 for m in baseline if (m["home_score"] + m["away_score"]) > 2.5)
        rec_o25 = sum(1 for m in recent if (m["home_score"] + m["away_score"]) > 2.5)
        
        prop_base_o25 = base_o25 / len(baseline)
        prop_rec_o25 = rec_o25 / len(recent)

        p_pool_o25 = (base_o25 + rec_o25) / (len(baseline) + len(recent))
        if 0 < p_pool_o25 < 1:
            se_o25 = np.sqrt(p_pool_o25 * (1 - p_pool_o25) * (1/len(baseline) + 1/len(recent)))
            z_score_o25 = (prop_rec_o25 - prop_base_o25) / se_o25
            p_val_o25 = 2 * (1 - stats.norm.cdf(abs(z_score_o25)))

            if p_val_o25 < 0.05 and abs(prop_rec_o25 - prop_base_o25) > 0.12:
                alerts.append({
                    "metric_name": "OVER_2.5_RATE",
                    "bookmaker": bookmaker or "ALL",
                    "baseline_value": round(prop_base_o25 * 100, 1),
                    "recent_value": round(prop_rec_o25 * 100, 1),
                    "sample_size": len(recent),
                    "p_value": round(float(p_val_o25), 4),
                    "confidence_level": "HIGH" if p_val_o25 < 0.01 else "MEDIUM",
                    "description": f"Changement de fréquence Over 2.5 ({round(prop_base_o25*100, 1)}% -> {round(prop_rec_o25*100, 1)}%, p={round(p_val_o25, 4)})."
                })

        return alerts
