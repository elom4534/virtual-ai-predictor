import numpy as np
from typing import Dict, List, Tuple, Any, Optional
import math
import json
import re

class TrendMomentumModel:
    """
    Model B: Exponential Time-Decay Weighted Poisson & Form Tracker.
    """
    def __init__(self, window_size: int = 10, decay_rate: float = 0.08):
        self.window_size = window_size
        self.decay_rate = decay_rate

    def analyze_team_form(self, matches: List[Dict[str, Any]], team: str) -> Dict[str, Any]:
        team_matches = []
        for m in matches:
            if m.get("home_team") == team or m.get("away_team") == team:
                if m.get("home_score") is not None and m.get("away_score") is not None:
                    team_matches.append(m)

        team_matches.sort(key=lambda x: x.get("match_time", ""), reverse=True)
        recent = team_matches[:self.window_size]

        if not recent:
            return {
                "sample_size": 0,
                "weighted_goals_scored": 1.4,
                "weighted_goals_conceded": 1.2,
                "form_points": 1.5,
                "streak": "N/A"
            }

        total_weight = 0.0
        w_scored = 0.0
        w_conceded = 0.0
        points = 0.0

        for idx, m in enumerate(recent):
            weight = math.exp(-self.decay_rate * idx)
            total_weight += weight

            is_home = (m.get("home_team") == team)
            scored = m["home_score"] if is_home else m["away_score"]
            conceded = m["away_score"] if is_home else m["home_score"]

            w_scored += scored * weight
            w_conceded += conceded * weight

            if scored > conceded:
                points += 3.0 * weight
            elif scored == conceded:
                points += 1.0 * weight

        return {
            "sample_size": len(recent),
            "weighted_goals_scored": round(w_scored / total_weight, 3),
            "weighted_goals_conceded": round(w_conceded / total_weight, 3),
            "form_points_per_match": round(points / total_weight, 2)
        }

    def predict(
        self, 
        matches_history: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str
    ) -> Dict[str, Any]:
        h_form = self.analyze_team_form(matches_history, home_team)
        a_form = self.analyze_team_form(matches_history, away_team)

        exp_h = max(0.4, (h_form["weighted_goals_scored"] + a_form["weighted_goals_conceded"]) / 2.0)
        exp_a = max(0.3, (a_form["weighted_goals_scored"] + h_form["weighted_goals_conceded"]) / 2.0)

        tot = exp_h + exp_a + 0.8
        p_home = round(exp_h / tot, 4)
        p_away = round(exp_a / tot, 4)
        p_draw = round(max(0.12, 1.0 - (p_home + p_away)), 4)
        p_sum = p_home + p_draw + p_away

        p_o25 = round(1.0 - math.exp(-((exp_h + exp_a) / 2.8) * 1.8), 4)
        p_btts = round((1.0 - math.exp(-exp_h)) * (1.0 - math.exp(-exp_a)), 4)

        return {
            "model_name": "Trend Momentum (Time Decay)",
            "expected_goals": {"home": round(exp_h, 2), "away": round(exp_a, 2)},
            "markets": {
                "1x2": {
                    "home_win": round(p_home / p_sum, 4),
                    "draw": round(p_draw / p_sum, 4),
                    "away_win": round(p_away / p_sum, 4)
                },
                "over_under": {
                    "over_2.5": min(0.92, max(0.15, p_o25)),
                    "under_2.5": round(1.0 - min(0.92, max(0.15, p_o25)), 4)
                },
                "btts": {
                    "yes": min(0.90, max(0.18, p_btts)),
                    "no": round(1.0 - min(0.90, max(0.18, p_btts)), 4)
                }
            }
        }


class MachineLearningCalibratedModel:
    """
    Model C: Logistic & Odds-Implied Probability Machine Learning Model.
    """
    def __init__(self):
        from sklearn.linear_model import LogisticRegression
        self.clf_1x2: Optional[LogisticRegression] = None
        self.clf_over25: Optional[LogisticRegression] = None
        self.clf_btts: Optional[LogisticRegression] = None
        self.is_trained = False

    def extract_features(
        self, 
        matches: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str, 
        odds: Optional[Dict[str, float]] = None
    ) -> np.ndarray:
        # 1. Market Implied Probabilities from Odds
        o1 = float(odds.get("1", 2.40)) if odds and odds.get("1") else 2.40
        ox = float(odds.get("x", 3.30)) if odds and odds.get("x") else 3.30
        o2 = float(odds.get("2", 2.70)) if odds and odds.get("2") else 2.70

        inv1, invx, inv2 = 1.0 / max(1.01, o1), 1.0 / max(1.01, ox), 1.0 / max(1.01, o2)
        margin = inv1 + invx + inv2
        odds_p1 = inv1 / margin
        odds_px = invx / margin
        odds_p2 = inv2 / margin

        # 2. Team Historical Goal Stats
        h_scored, h_conceded, h_matches = 0, 0, 0
        a_scored, a_conceded, a_matches = 0, 0, 0

        h2h_h_wins, h2h_draws, h2h_a_wins, h2h_tot = 0, 0, 0, 0

        for m in matches:
            hs = m.get("home_score")
            as_ = m.get("away_score")
            if hs is None or as_ is None:
                continue

            # Home stats
            if m.get("home_team") == home_team:
                h_scored += hs
                h_conceded += as_
                h_matches += 1
            elif m.get("away_team") == home_team:
                h_scored += as_
                h_conceded += hs
                h_matches += 1

            # Away stats
            if m.get("home_team") == away_team:
                a_scored += hs
                a_conceded += as_
                a_matches += 1
            elif m.get("away_team") == away_team:
                a_scored += as_
                a_conceded += hs
                a_matches += 1

            # H2H
            if (m.get("home_team") == home_team and m.get("away_team") == away_team) or \
               (m.get("home_team") == away_team and m.get("away_team") == home_team):
                h2h_tot += 1
                is_curr_home = (m.get("home_team") == home_team)
                m_h_score = hs if is_curr_home else as_
                m_a_score = as_ if is_curr_home else hs
                if m_h_score > m_a_score:
                    h2h_h_wins += 1
                elif m_h_score == m_a_score:
                    h2h_draws += 1
                else:
                    h2h_a_wins += 1

        h_att = (h_scored / max(1, h_matches))
        h_def = (h_conceded / max(1, h_matches))
        a_att = (a_scored / max(1, a_matches))
        a_def = (a_conceded / max(1, a_matches))

        features = [
            h_att, h_def, a_att, a_def,
            h2h_h_wins / max(1, h2h_tot),
            h2h_draws / max(1, h2h_tot),
            h2h_a_wins / max(1, h2h_tot),
            odds_p1, odds_px, odds_p2
        ]
        return np.array(features).reshape(1, -1)

    def train_on_history(self, matches: List[Dict[str, Any]]):
        from sklearn.linear_model import LogisticRegression
        if len(matches) < 20:
            return

        X, y_1x2, y_o25, y_btts = [], [], [], []

        step = 1 if len(matches) < 100 else 2
        for idx in range(15, len(matches), step):
            history = matches[:idx]
            target_match = matches[idx]
            
            hs = target_match.get("home_score")
            as_ = target_match.get("away_score")
            if hs is None or as_ is None:
                continue

            odds_dict = {
                "1": target_match.get("odds_1"),
                "x": target_match.get("odds_x"),
                "2": target_match.get("odds_2")
            }
            feat = self.extract_features(
                history, 
                target_match["home_team"], 
                target_match["away_team"], 
                odds_dict
            )[0]
            
            if hs > as_:
                label_1x2 = 0
            elif hs == as_:
                label_1x2 = 1
            else:
                label_1x2 = 2

            label_o25 = 1 if (hs + as_) > 2.5 else 0
            label_btts = 1 if (hs > 0 and as_ > 0) else 0

            X.append(feat)
            y_1x2.append(label_1x2)
            y_o25.append(label_o25)
            y_btts.append(label_btts)

        if len(X) < 15:
            return

        X = np.array(X)
        self.clf_1x2 = LogisticRegression(max_iter=300, C=1.0)
        self.clf_1x2.fit(X, y_1x2)

        self.clf_over25 = LogisticRegression(max_iter=300, C=1.0)
        self.clf_over25.fit(X, y_o25)

        self.clf_btts = LogisticRegression(max_iter=300, C=1.0)
        self.clf_btts.fit(X, y_btts)

        self.is_trained = True

    def predict(
        self, 
        matches_history: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str, 
        odds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        # Market priors
        o1 = float(odds.get("1", 2.40)) if odds and odds.get("1") else 2.40
        ox = float(odds.get("x", 3.30)) if odds and odds.get("x") else 3.30
        o2 = float(odds.get("2", 2.70)) if odds and odds.get("2") else 2.70
        inv1, invx, inv2 = 1.0 / max(1.01, o1), 1.0 / max(1.01, ox), 1.0 / max(1.01, o2)
        margin = inv1 + invx + inv2
        m_p1, m_px, m_p2 = inv1 / margin, invx / margin, inv2 / margin

        if not self.is_trained or self.clf_1x2 is None:
            return {
                "model_name": "Odds-Implied ML Model",
                "markets": {
                    "1x2": {"home_win": round(m_p1, 4), "draw": round(m_px, 4), "away_win": round(m_p2, 4)},
                    "over_under": {"over_2.5": 0.55, "under_2.5": 0.45},
                    "btts": {"yes": 0.54, "no": 0.46}
                }
            }

        feat = self.extract_features(matches_history, home_team, away_team, odds)
        probs_1x2 = self.clf_1x2.predict_proba(feat)[0]
        prob_o25 = float(self.clf_over25.predict_proba(feat)[0][1])
        prob_btts = float(self.clf_btts.predict_proba(feat)[0][1])

        p_home = round(0.55 * float(probs_1x2[0]) + 0.45 * m_p1, 4)
        p_draw = round(0.55 * (float(probs_1x2[1]) if len(probs_1x2) > 1 else 0.25) + 0.45 * m_px, 4)
        p_away = round(0.55 * (float(probs_1x2[2]) if len(probs_1x2) > 2 else 0.35) + 0.45 * m_p2, 4)
        tot = p_home + p_draw + p_away

        return {
            "model_name": "Odds-Calibrated Logistic Model",
            "markets": {
                "1x2": {
                    "home_win": round(p_home / tot, 4),
                    "draw": round(p_draw / tot, 4),
                    "away_win": round(p_away / tot, 4)
                },
                "over_under": {
                    "over_2.5": round(prob_o25, 4),
                    "under_2.5": round(1.0 - prob_o25, 4)
                },
                "btts": {
                    "yes": round(prob_btts, 4),
                    "no": round(1.0 - prob_btts, 4)
                }
            }
        }


class VirtualAIEnsemblePredictor:
    """
    Model D: Calibrated Meta-Ensemble with High-Accuracy Sharp Pick Engine.
    Analyzes Odds, xG Goals Expectancy, and Probability Density.
    """
    def __init__(self):
        from models_stat import StatisticalPoissonEngine
        self.poisson_engine = StatisticalPoissonEngine()
        self.trend_engine = TrendMomentumModel()
        self.ml_engine = MachineLearningCalibratedModel()

    def generate_prediction(
        self,
        matches_history: List[Dict[str, Any]],
        home_team: str,
        away_team: str,
        bookmaker: str = "1xBet",
        competition: str = "FC 26. Champions League",
        odds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        comp_matches = [m for m in matches_history if m.get("competition") == competition]
        dataset = comp_matches if len(comp_matches) >= 12 else matches_history

        res_poisson = self.poisson_engine.predict(dataset, home_team, away_team)
        res_trend = self.trend_engine.predict(dataset, home_team, away_team)
        res_ml = self.ml_engine.predict(dataset, home_team, away_team, odds)

        h2h_cnt = res_poisson["sample_size_h2h"]
        team_cnt = res_poisson["sample_size_team"]

        # Parse Bookmaker Odds
        o1 = float(odds.get("1", 2.20)) if odds and odds.get("1") else 2.20
        ox = float(odds.get("x", 3.40)) if odds and odds.get("x") else 3.40
        o2 = float(odds.get("2", 2.90)) if odds and odds.get("2") else 2.90
        inv1, invx, inv2 = 1.0 / max(1.01, o1), 1.0 / max(1.01, ox), 1.0 / max(1.01, o2)
        margin = inv1 + invx + inv2
        m_p1, m_px, m_p2 = inv1 / margin, invx / margin, inv2 / margin

        # Weighted Ensemble: Poisson (35%), Form Trend (20%), Odds-Calibrated ML (45%)
        w_poisson, w_trend, w_ml = 0.35, 0.20, 0.45

        p_home = (
            w_poisson * res_poisson["markets"]["1x2"]["home_win"] +
            w_trend * res_trend["markets"]["1x2"]["home_win"] +
            w_ml * res_ml["markets"]["1x2"]["home_win"]
        )
        p_draw = (
            w_poisson * res_poisson["markets"]["1x2"]["draw"] +
            w_trend * res_trend["markets"]["1x2"]["draw"] +
            w_ml * res_ml["markets"]["1x2"]["draw"]
        )
        p_away = (
            w_poisson * res_poisson["markets"]["1x2"]["away_win"] +
            w_trend * res_trend["markets"]["1x2"]["away_win"] +
            w_ml * res_ml["markets"]["1x2"]["away_win"]
        )
        tot_1x2 = p_home + p_draw + p_away
        p_home = round(p_home / tot_1x2, 4)
        p_draw = round(p_draw / tot_1x2, 4)
        p_away = round(p_away / tot_1x2, 4)

        p_o25 = round(
            w_poisson * res_poisson["markets"]["over_under"]["over_2.5"] +
            w_trend * res_trend["markets"]["over_under"]["over_2.5"] +
            w_ml * res_ml["markets"]["over_under"]["over_2.5"], 4
        )
        p_u25 = round(1.0 - p_o25, 4)

        p_o15 = res_poisson["markets"]["over_under"]["over_1.5"]
        p_u15 = res_poisson["markets"]["over_under"]["under_1.5"]
        p_o35 = res_poisson["markets"]["over_under"]["over_3.5"]
        p_u35 = res_poisson["markets"]["over_under"]["under_3.5"]

        p_btts_yes = round(
            w_poisson * res_poisson["markets"]["btts"]["yes"] +
            w_trend * res_trend["markets"]["btts"]["yes"] +
            w_ml * res_ml["markets"]["btts"]["yes"], 4
        )
        p_btts_no = round(1.0 - p_btts_yes, 4)

        top_exact = res_poisson["markets"]["top_exact_scores"]
        exp_home = res_poisson["expected_goals"]["home"]
        exp_away = res_poisson["expected_goals"]["away"]
        tot_exp = round(exp_home + exp_away, 2)

        # -------------------------------------------------------------
        # SHARP INTELLIGENT PICK SELECTOR (ZERO BIAS, VALUE & CONFIDENCE)
        # -------------------------------------------------------------
        clean_home = home_team.replace(" Cyber", "").replace(" FC", "").replace("1. ", "").strip()
        clean_away = away_team.replace(" Cyber", "").replace(" FC", "").replace("1. ", "").strip()

        is_rush = any(k in competition.lower() for k in ["rush", "5x5", "4x4", "3x3"])

        best_market = "1X2"
        best_selection = f"Victoire {clean_home}"
        best_prob = p_home
        fair_odd = round(1.0 / max(0.01, p_home), 2)
        conf_tier = "HIGH"
        conf_score = 82.0

        if is_rush:
            # RUSH 5x5 / 4x4 : High goal density matches
            if p_btts_yes > 0.70:
                best_market = "BTTS"
                best_selection = "Les 2 équipes marquent (OUI)"
                best_prob = p_btts_yes
                conf_score = round(p_btts_yes * 100, 1)
            elif p_o25 > 0.72:
                best_market = "OVER_UNDER_2.5"
                best_selection = "Plus de 2.5 Buts"
                best_prob = p_o25
                conf_score = round(p_o25 * 100, 1)
            elif p_home > p_away and p_home > 0.50:
                best_market = "1X2"
                best_selection = f"Victoire {clean_home} (1)"
                best_prob = p_home
                conf_score = round(p_home * 100, 1)
            else:
                best_market = "1X2"
                best_selection = f"Victoire {clean_away} (2)"
                best_prob = p_away
                conf_score = round(p_away * 100, 1)
        else:
            # STANDARD 11v11 SIMULATION MATCHES
            # Case 1: Away Heavy Favorite (e.g. Bayern Munich, Mainz, Real Madrid playing away)
            if (o2 <= 1.85 and p_away >= 0.48) or (p_away >= 0.54 and p_away > p_home * 1.3):
                best_market = "1X2"
                best_selection = f"Victoire {clean_away} (2)"
                best_prob = p_away
                conf_tier = "HIGH"
                conf_score = min(92.0, max(75.0, round(p_away * 100, 1)))

            # Case 2: Home Heavy Favorite (e.g. Man City, Real Madrid playing home)
            elif (o1 <= 1.85 and p_home >= 0.48) or (p_home >= 0.54 and p_home > p_away * 1.3):
                best_market = "1X2"
                best_selection = f"Victoire {clean_home} (1)"
                best_prob = p_home
                conf_tier = "HIGH"
                conf_score = min(92.0, max(75.0, round(p_home * 100, 1)))

            # Case 3: High Offensive Expectancy (Both teams score heavily)
            elif p_o25 >= 0.65 and tot_exp >= 2.9:
                best_market = "OVER_UNDER_2.5"
                best_selection = "Plus de 2.5 Buts"
                best_prob = p_o25
                conf_tier = "HIGH"
                conf_score = min(90.0, max(72.0, round(p_o25 * 100, 1)))

            # Case 4: BTTS High Probability
            elif p_btts_yes >= 0.66:
                best_market = "BTTS"
                best_selection = "Les 2 équipes marquent (OUI)"
                best_prob = p_btts_yes
                conf_tier = "HIGH"
                conf_score = min(88.0, max(70.0, round(p_btts_yes * 100, 1)))

            # Case 5: Away slight edge -> Double Chance X2
            elif p_away >= p_home and (p_away + p_draw) >= 0.65:
                best_market = "DOUBLE_CHANCE"
                best_selection = f"X2 ({clean_away} ou Nul)"
                best_prob = round(p_away + p_draw, 4)
                conf_tier = "MEDIUM"
                conf_score = min(85.0, max(68.0, round((p_away + p_draw) * 100, 1)))

            # Case 6: Home slight edge -> Double Chance 1X
            elif p_home > p_away and (p_home + p_draw) >= 0.65:
                best_market = "DOUBLE_CHANCE"
                best_selection = f"1X ({clean_home} ou Nul)"
                best_prob = round(p_home + p_draw, 4)
                conf_tier = "MEDIUM"
                conf_score = min(85.0, max(68.0, round((p_home + p_draw) * 100, 1)))

            # Case 7: Tight low-scoring match
            elif p_u25 >= 0.62:
                best_market = "OVER_UNDER_2.5"
                best_selection = "Moins de 2.5 Buts"
                best_prob = p_u25
                conf_tier = "MEDIUM"
                conf_score = min(82.0, max(65.0, round(p_u25 * 100, 1)))
            else:
                best_market = "1X2"
                best_selection = f"Victoire {clean_home} (1)" if p_home >= p_away else f"Victoire {clean_away} (2)"
                best_prob = max(p_home, p_away)
                conf_tier = "LOW"
                conf_score = 64.0

        fair_odd = round(1.0 / max(0.01, best_prob), 2)

        # Reasoning
        reasoning_pos = []
        reasoning_neg = []

        if "Victoire" in best_selection:
            fav = clean_home if "1" in best_selection or clean_home in best_selection else clean_away
            reasoning_pos.append(f"Indicateur de supériorité nette pour {fav} (Cotes & xG en faveur de la victoire directe).")
        elif "Plus de 2.5" in best_selection or "marquent" in best_selection:
            reasoning_pos.append(f"Dynamique offensive élevée : total d'xG combiné estimé à {tot_exp} buts.")
        elif "Double Chance" in best_selection:
            reasoning_pos.append("Sécurisation du résultat via double chance sur match à variance modérée.")

        if o1 and o2:
            reasoning_pos.append(f"Cotes réelles intégrées : 1={o1} | N={ox} | 2={o2}.")

        if abs(p_home - p_away) < 0.08:
            reasoning_neg.append("Équilibre statistique serré entre les deux formations.")

        return {
            "model_version": "v2.7.0-sharp-ensemble",
            "confidence_score": conf_score,
            "confidence_tier": conf_tier,
            "confidence_description": f"Analyse statistique et lecture des cotes ({conf_score}% confiance).",
            "sample_size_h2h": h2h_cnt,
            "sample_size_team": team_cnt,
            "expected_goals": {"home": exp_home, "away": exp_away, "total": tot_exp},
            "markets": {
                "1x2": {
                    "home_win": p_home,
                    "draw": p_draw,
                    "away_win": p_away
                },
                "double_chance": {
                    "1x": round(p_home + p_draw, 4),
                    "12": round(p_home + p_away, 4),
                    "x2": round(p_draw + p_away, 4)
                },
                "over_under": {
                    "over_1.5": p_o15,
                    "under_1.5": p_u15,
                    "over_2.5": p_o25,
                    "under_2.5": p_u25,
                    "over_3.5": p_o35,
                    "under_3.5": p_u35
                },
                "btts": {
                    "yes": p_btts_yes,
                    "no": p_btts_no
                },
                "exact_scores": top_exact[:4]
            },
            "main_pick": {
                "market": best_market,
                "selection": best_selection,
                "probability": best_prob,
                "fair_odds": fair_odd
            },
            "alternative_picks": [
                {
                    "market": "OVER_UNDER_2.5",
                    "selection": "Plus de 2.5 Buts" if p_o25 >= 0.50 else "Moins de 2.5 Buts",
                    "probability": max(p_o25, p_u25),
                    "fair_odds": round(1.0 / max(0.01, max(p_o25, p_u25)), 2)
                },
                {
                    "market": "BTTS",
                    "selection": "Les 2 équipes marquent (OUI)" if p_btts_yes >= 0.50 else "Les 2 marquent (NON)",
                    "probability": max(p_btts_yes, p_btts_no),
                    "fair_odds": round(1.0 / max(0.01, max(p_btts_yes, p_btts_no)), 2)
                }
            ],
            "sub_models": {
                "poisson": res_poisson["markets"]["1x2"],
                "trend": res_trend["markets"]["1x2"],
                "ml": res_ml["markets"]["1x2"]
            },
            "reasoning": {
                "positive_factors": reasoning_pos,
                "negative_factors": reasoning_neg
            }
        }
