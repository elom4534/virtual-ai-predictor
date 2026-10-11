import math
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

def poisson_prob(k: int, lambd: float) -> float:
    """Computes standard Poisson probability P(X=k | lambda)."""
    if lambd <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

def dixon_coles_tau(x: int, y: int, lambd: float, mu: float, rho: float = -0.05) -> float:
    """
    Dixon-Coles adjustment parameter tau(x, y, lambda, mu, rho)
    accounting for low-scoring interdependence (0-0, 1-0, 0-1, 1-1).
    """
    if x == 0 and y == 0:
        return max(0.0, 1.0 - (lambd * mu * rho))
    elif x == 0 and y == 1:
        return max(0.0, 1.0 + (lambd * rho))
    elif x == 1 and y == 0:
        return max(0.0, 1.0 + (mu * rho))
    elif x == 1 and y == 1:
        return max(0.0, 1.0 - rho)
    return 1.0

def compute_bivariate_poisson_matrix(
    lambd: float, 
    mu: float, 
    max_goals: int = 8, 
    rho: float = -0.04
) -> np.ndarray:
    """
    Builds the probability score grid [0..max_goals, 0..max_goals]
    using Dixon-Coles adjusted Poisson model.
    """
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            px = poisson_prob(x, lambd)
            py = poisson_prob(y, mu)
            tau = dixon_coles_tau(x, y, lambd, mu, rho)
            matrix[x, y] = px * py * tau
    
    # Normalize to ensure sum of probabilities equals exactly 1.0
    total = np.sum(matrix)
    if total > 0:
        matrix /= total
    return matrix

def calculate_market_probabilities_from_matrix(matrix: np.ndarray) -> Dict[str, Any]:
    """Derives all betting markets from the score probability matrix."""
    max_goals = matrix.shape[0] - 1
    
    p_home_win = 0.0
    p_draw = 0.0
    p_away_win = 0.0
    
    p_over15 = 0.0
    p_over25 = 0.0
    p_over35 = 0.0
    p_over45 = 0.0
    
    p_btts_yes = 0.0
    
    exact_scores: List[Dict[str, Any]] = []
    
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p = float(matrix[x, y])
            if x > y:
                p_home_win += p
            elif x == y:
                p_draw += p
            else:
                p_away_win += p
                
            total_goals = x + y
            if total_goals > 1.5:
                p_over15 += p
            if total_goals > 2.5:
                p_over25 += p
            if total_goals > 3.5:
                p_over35 += p
            if total_goals > 4.5:
                p_over45 += p
                
            if x >= 1 and y >= 1:
                p_btts_yes += p
                
            exact_scores.append({
                "score": f"{x}-{y}",
                "home_goals": x,
                "away_goals": y,
                "prob": round(p, 4),
                "odds_fair": round(1.0 / p, 2) if p > 0.001 else 999.0
            })
            
    exact_scores.sort(key=lambda s: s["prob"], reverse=True)
    
    return {
        "1x2": {
            "home_win": round(p_home_win, 4),
            "draw": round(p_draw, 4),
            "away_win": round(p_away_win, 4)
        },
        "double_chance": {
            "1x": round(p_home_win + p_draw, 4),
            "12": round(p_home_win + p_away_win, 4),
            "x2": round(p_draw + p_away_win, 4)
        },
        "over_under": {
            "over_1.5": round(p_over15, 4),
            "under_1.5": round(1.0 - p_over15, 4),
            "over_2.5": round(p_over25, 4),
            "under_2.5": round(1.0 - p_over25, 4),
            "over_3.5": round(p_over35, 4),
            "under_3.5": round(1.0 - p_over35, 4),
            "over_4.5": round(p_over45, 4),
            "under_4.5": round(1.0 - p_over45, 4)
        },
        "btts": {
            "yes": round(p_btts_yes, 4),
            "no": round(1.0 - p_btts_yes, 4)
        },
        "top_exact_scores": exact_scores[:6]
    }

class StatisticalPoissonEngine:
    """
    Computes statistical attack/defense ratings and generates
    expected goals (xG) and Dixon-Coles distributions.
    """
    def __init__(self, decay_factor: float = 0.96):
        self.decay_factor = decay_factor

    def compute_team_ratings(
        self, 
        matches: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str
    ) -> Tuple[float, float, int, int]:
        """
        Calculates lambda (home expected goals) and mu (away expected goals)
        based on past matches with exponential time decay.
        """
        if not matches:
            return 1.45, 1.25, 0, 0 # baseline league average

        home_scored, home_conceded, home_weight = [], [], []
        away_scored, away_conceded, away_weight = [], [], []
        
        league_home_goals = []
        league_away_goals = []

        h2h_count = 0
        team_matches_count = 0

        # Sort matches chronologically ascending if possible
        for i, m in enumerate(reversed(matches)):
            # exponential weight: more recent matches get higher weight
            w = math.pow(self.decay_factor, i)
            hs = m.get("home_score", 0)
            as_ = m.get("away_score", 0)
            
            if hs is None or as_ is None:
                continue

            league_home_goals.append(hs)
            league_away_goals.append(as_)

            # Check if this match involves home_team
            if m["home_team"] == home_team:
                home_scored.append(hs * w)
                home_conceded.append(as_ * w)
                home_weight.append(w)
                team_matches_count += 1
            elif m["away_team"] == home_team:
                home_scored.append(as_ * w)
                home_conceded.append(hs * w)
                home_weight.append(w)
                team_matches_count += 1

            # Check if this match involves away_team
            if m["home_team"] == away_team:
                away_scored.append(hs * w)
                away_conceded.append(as_ * w)
                away_weight.append(w)
            elif m["away_team"] == away_team:
                away_scored.append(as_ * w)
                away_conceded.append(hs * w)
                away_weight.append(w)

            # Check H2H
            if (m["home_team"] == home_team and m["away_team"] == away_team) or \
               (m["home_team"] == away_team and m["away_team"] == home_team):
                h2h_count += 1

        avg_league_home = np.mean(league_home_goals) if league_home_goals else 1.45
        avg_league_away = np.mean(league_away_goals) if league_away_goals else 1.20

        # Home team offensive and defensive strengths
        if home_weight and sum(home_weight) > 0:
            home_att = (sum(home_scored) / sum(home_weight)) / max(avg_league_home, 0.5)
            home_def = (sum(home_conceded) / sum(home_weight)) / max(avg_league_away, 0.5)
        else:
            home_att = 1.0
            home_def = 1.0

        # Away team offensive and defensive strengths
        if away_weight and sum(away_weight) > 0:
            away_att = (sum(away_scored) / sum(away_weight)) / max(avg_league_away, 0.5)
            away_def = (sum(away_conceded) / sum(away_weight)) / max(avg_league_home, 0.5)
        else:
            away_att = 1.0
            away_def = 1.0

        # Expected goals with slight home field edge (common even in virtuals due to game engine seeding)
        home_edge = 1.08
        lambd = max(0.2, avg_league_home * home_att * away_def * home_edge)
        mu = max(0.2, avg_league_away * away_att * home_def)

        return round(float(lambd), 2), round(float(mu), 2), h2h_count, team_matches_count

    def predict(
        self, 
        matches: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str
    ) -> Dict[str, Any]:
        lambd, mu, h2h_cnt, team_cnt = self.compute_team_ratings(matches, home_team, away_team)
        matrix = compute_bivariate_poisson_matrix(lambd, mu)
        markets = calculate_market_probabilities_from_matrix(matrix)
        
        return {
            "model_name": "Statistical Poisson & Dixon-Coles",
            "expected_goals": {"home": lambd, "away": mu, "total": round(lambd + mu, 2)},
            "markets": markets,
            "sample_size_h2h": h2h_cnt,
            "sample_size_team": team_cnt
        }
