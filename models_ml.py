import numpy as np
from typing import Dict, List, Tuple, Any, Optional
import math
from sklearn.linear_model import LogisticRegression

class TrendMomentumModel:
    """
    Model B: Short-term Momentum, streak analysis and recent distribution shifts.
    """
    def __init__(self, window_size: int = 8):
        self.window_size = window_size

    def analyze_team_form(self, matches: List[Dict[str, Any]], team: str) -> Dict[str, Any]:
        team_matches = []
        for m in reversed(matches):
            if m.get("home_score") is None or m.get("away_score") is None:
                continue
            if m["home_team"] == team or m["away_team"] == team:
                team_matches.append(m)
                if len(team_matches) >= self.window_size:
                    break

        if not team_matches:
            return {
                "matches_count": 0, "wins": 0, "draws": 0, "losses": 0,
                "win_rate": 0.35, "draw_rate": 0.25, "loss_rate": 0.40,
                "avg_scored": 1.4, "avg_conceded": 1.4,
                "btts_rate": 0.52, "over25_rate": 0.54,
                "clean_sheet_rate": 0.15, "form_string": "N/A"
            }

        wins, draws, losses = 0, 0, 0
        scored, conceded = 0, 0
        btts_cnt, over25_cnt, clean_sheets = 0, 0, 0
        form_letters = []

        for m in team_matches:
            is_home = (m["home_team"] == team)
            s_for = m["home_score"] if is_home else m["away_score"]
            s_against = m["away_score"] if is_home else m["home_score"]
            
            scored += s_for
            conceded += s_against

            if s_against == 0:
                clean_sheets += 1
            if s_for > 0 and s_against > 0:
                btts_cnt += 1
            if (s_for + s_against) > 2.5:
                over25_cnt += 1

            if s_for > s_against:
                wins += 1
                form_letters.append("W")
            elif s_for == s_against:
                draws += 1
                form_letters.append("D")
            else:
                losses += 1
                form_letters.append("L")

        n = len(team_matches)
        return {
            "matches_count": n,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_rate": round(wins / n, 2),
            "draw_rate": round(draws / n, 2),
            "loss_rate": round(losses / n, 2),
            "avg_scored": round(scored / n, 2),
            "avg_conceded": round(conceded / n, 2),
            "btts_rate": round(btts_cnt / n, 2),
            "over25_rate": round(over25_cnt / n, 2),
            "clean_sheet_rate": round(clean_sheets / n, 2),
            "form_string": "".join(form_letters[:5])
        }

    def predict(
        self, 
        matches: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str
    ) -> Dict[str, Any]:
        home_form = self.analyze_team_form(matches, home_team)
        away_form = self.analyze_team_form(matches, away_team)

        p_home = (home_form.get("win_rate", 0.4) + away_form.get("loss_rate", 0.3)) / 2.0
        p_away = (away_form.get("win_rate", 0.35) + home_form.get("loss_rate", 0.35)) / 2.0
        p_draw = max(0.18, 1.0 - (p_home + p_away))

        total = p_home + p_draw + p_away
        p_home = round(p_home / total, 4)
        p_draw = round(p_draw / total, 4)
        p_away = round(p_away / total, 4)

        p_o25 = round((home_form.get("over25_rate", 0.55) + away_form.get("over25_rate", 0.55)) / 2.0, 4)
        p_btts = round((home_form.get("btts_rate", 0.52) + away_form.get("btts_rate", 0.52)) / 2.0, 4)

        return {
            "model_name": "Trend & Momentum Engine",
            "home_form": home_form,
            "away_form": away_form,
            "markets": {
                "1x2": {"home_win": p_home, "draw": p_draw, "away_win": p_away},
                "double_chance": {
                    "1x": round(p_home + p_draw, 4),
                    "12": round(p_home + p_away, 4),
                    "x2": round(p_draw + p_away, 4)
                },
                "over_under": {
                    "over_2.5": p_o25,
                    "under_2.5": round(1.0 - p_o25, 4)
                },
                "btts": {
                    "yes": p_btts,
                    "no": round(1.0 - p_btts, 4)
                }
            }
        }


class MachineLearningCalibratedModel:
    """
    Model C: Machine Learning model with Feature Engineering & Calibrated Probabilities.
    """
    def __init__(self):
        self.clf_1x2 = None
        self.clf_over25 = None
        self.clf_btts = None
        self.is_trained = False

    def extract_features(
        self, 
        matches_history: List[Dict[str, Any]], 
        home_team: str, 
        away_team: str, 
        odds: Optional[Dict[str, float]] = None
    ) -> np.ndarray:
        h_scored, h_conceded, h_matches = 0, 0, 0
        a_scored, a_conceded, a_matches = 0, 0, 0
        h2h_h_wins, h2h_draws, h2h_a_wins, h2h_tot = 0, 0, 0, 0

        # Fast scan over last 50 matches
        recent_scan = matches_history[-60:] if len(matches_history) > 60 else matches_history
        for m in recent_scan:
            hs = m.get("home_score")
            as_ = m.get("away_score")
            if hs is None or as_ is None:
                continue

            if m["home_team"] == home_team:
                h_scored += hs
                h_conceded += as_
                h_matches += 1
            elif m["away_team"] == home_team:
                h_scored += as_
                h_conceded += hs
                h_matches += 1

            if m["home_team"] == away_team:
                a_scored += hs
                a_conceded += as_
                a_matches += 1
            elif m["away_team"] == away_team:
                a_scored += as_
                a_conceded += hs
                a_matches += 1

            if (m["home_team"] == home_team and m["away_team"] == away_team) or \
               (m["home_team"] == away_team and m["away_team"] == home_team):
                h2h_tot += 1
                if hs > as_:
                    if m["home_team"] == home_team: h2h_h_wins += 1
                    else: h2h_a_wins += 1
                elif hs == as_:
                    h2h_draws += 1
                else:
                    if m["home_team"] == home_team: h2h_a_wins += 1
                    else: h2h_h_wins += 1

        h_att = (h_scored / max(1, h_matches))
        h_def = (h_conceded / max(1, h_matches))
        a_att = (a_scored / max(1, a_matches))
        a_def = (a_conceded / max(1, a_matches))

        odds_p1, odds_px, odds_p2 = 0.40, 0.25, 0.35
        if odds and odds.get("1") and odds.get("x") and odds.get("2"):
            try:
                inv_1 = 1.0 / odds["1"]
                inv_x = 1.0 / odds["x"]
                inv_2 = 1.0 / odds["2"]
                tot_inv = inv_1 + inv_x + inv_2
                odds_p1 = inv_1 / tot_inv
                odds_px = inv_x / tot_inv
                odds_p2 = inv_2 / tot_inv
            except Exception:
                pass

        features = [
            h_att,
            h_def,
            a_att,
            a_def,
            h2h_h_wins / max(1, h2h_tot),
            h2h_draws / max(1, h2h_tot),
            h2h_a_wins / max(1, h2h_tot),
            odds_p1,
            odds_px,
            odds_p2
        ]
        return np.array(features).reshape(1, -1)

    def train_on_history(self, matches: List[Dict[str, Any]]):
        if len(matches) < 20:
            return

        X, y_1x2, y_o25, y_btts = [], [], [], []

        # Subsample to keep training fast and robust
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
        if not self.is_trained or self.clf_1x2 is None:
            return {
                "model_name": "ML Calibrated Classifier (Prior)",
                "markets": {
                    "1x2": {"home_win": 0.44, "draw": 0.23, "away_win": 0.33},
                    "over_under": {"over_2.5": 0.54, "under_2.5": 0.46},
                    "btts": {"yes": 0.52, "no": 0.48}
                }
            }

        feat = self.extract_features(matches_history, home_team, away_team, odds)
        probs_1x2 = self.clf_1x2.predict_proba(feat)[0]
        prob_o25 = self.clf_over25.predict_proba(feat)[0][1]
        prob_btts = self.clf_btts.predict_proba(feat)[0][1]

        p_home = round(float(probs_1x2[0]), 4)
        p_draw = round(float(probs_1x2[1]) if len(probs_1x2) > 1 else 0.25, 4)
        p_away = round(float(probs_1x2[2]) if len(probs_1x2) > 2 else 0.35, 4)

        return {
            "model_name": "ML Calibrated Classifier",
            "markets": {
                "1x2": {"home_win": p_home, "draw": p_draw, "away_win": p_away},
                "double_chance": {
                    "1x": round(p_home + p_draw, 4),
                    "12": round(p_home + p_away, 4),
                    "x2": round(p_draw + p_away, 4)
                },
                "over_under": {
                    "over_2.5": round(float(prob_o25), 4),
                    "under_2.5": round(1.0 - float(prob_o25), 4)
                },
                "btts": {
                    "yes": round(float(prob_btts), 4),
                    "no": round(1.0 - float(prob_btts), 4)
                }
            }
        }


class VirtualAIEnsemblePredictor:
    """
    Model D: Calibrated Meta-Ensemble.
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
        competition: str = "FIFA 23 Cyber Champions League (4x4)",
        odds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        comp_matches = [m for m in matches_history if m.get("competition") == competition]
        dataset = comp_matches if len(comp_matches) >= 15 else matches_history

        res_poisson = self.poisson_engine.predict(dataset, home_team, away_team)
        res_trend = self.trend_engine.predict(dataset, home_team, away_team)
        res_ml = self.ml_engine.predict(dataset, home_team, away_team, odds)

        h2h_cnt = res_poisson["sample_size_h2h"]
        team_cnt = res_poisson["sample_size_team"]

        w_poisson, w_trend, w_ml = 0.40, 0.25, 0.35

        if team_cnt < 5:
            conf_tier = "INSUFFICIENT_DATA"
            conf_score = 42.0
            status_text = "Données historiques limitées : probabilités basées sur la moyenne de la ligue."
        elif team_cnt < 12:
            conf_tier = "LOW"
            conf_score = 62.0
            status_text = "Échantillon modéré : confiance modérée."
        elif team_cnt < 25:
            conf_tier = "MEDIUM"
            conf_score = 76.5
            status_text = "Historique solide : modèle calibré."
        else:
            conf_tier = "HIGH"
            conf_score = 89.0
            status_text = "Large volume de données : convergence statistique élevée."

        p_home = round(
            w_poisson * res_poisson["markets"]["1x2"]["home_win"] +
            w_trend * res_trend["markets"]["1x2"]["home_win"] +
            w_ml * res_ml["markets"]["1x2"]["home_win"], 4
        )
        p_draw = round(
            w_poisson * res_poisson["markets"]["1x2"]["draw"] +
            w_trend * res_trend["markets"]["1x2"]["draw"] +
            w_ml * res_ml["markets"]["1x2"]["draw"], 4
        )
        p_away = round(
            w_poisson * res_poisson["markets"]["1x2"]["away_win"] +
            w_trend * res_trend["markets"]["1x2"]["away_win"] +
            w_ml * res_ml["markets"]["1x2"]["away_win"], 4
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

        candidates = [
            ("1X2", f"1 ({home_team})", p_home, round(1.0 / max(0.01, p_home), 2)),
            ("1X2", f"2 ({away_team})", p_away, round(1.0 / max(0.01, p_away), 2)),
            ("DOUBLE_CHANCE", "1X (Domicile ou Nul)", round(p_home + p_draw, 4), round(1.0 / max(0.01, p_home + p_draw), 2)),
            ("DOUBLE_CHANCE", "X2 (Nul ou Extérieur)", round(p_draw + p_away, 4), round(1.0 / max(0.01, p_draw + p_away), 2)),
            ("OVER_UNDER_2.5", "Plus de 2.5 Buts", p_o25, round(1.0 / max(0.01, p_o25), 2)),
            ("OVER_UNDER_2.5", "Moins de 2.5 Buts", p_u25, round(1.0 / max(0.01, p_u25), 2)),
            ("BTTS", "Les 2 équipes marquent (OUI)", p_btts_yes, round(1.0 / max(0.01, p_btts_yes), 2))
        ]
        candidates.sort(key=lambda c: c[2], reverse=True)
        best_pick = candidates[0]
        alt_picks = candidates[1:4]

        reasoning_pos = []
        reasoning_neg = []

        if exp_home > 1.6:
            reasoning_pos.append(f"Attaque de {home_team} prolifique (xG estimé à {exp_home} buts).")
        if p_o25 > 0.60:
            reasoning_pos.append(f"Forte tendance offensive globale ({round(p_o25*100, 1)}% de probabilité d'Over 2.5).")
        if h2h_cnt >= 2:
            reasoning_pos.append(f"Historique direct solide : {h2h_cnt} confrontations directes analysées.")
        else:
            reasoning_neg.append("Échantillon H2H direct réduit entre ces deux équipes virtuelles.")

        if p_draw > 0.28:
            reasoning_neg.append("Risque élevé de match nul (variance tactique des simulations virtuelles).")
        if conf_tier == "INSUFFICIENT_DATA":
            reasoning_neg.append("Données limitées : marge d'incertitude statistique plus large.")

        return {
            "model_version": "v2.5.0-calibrated-ensemble",
            "confidence_score": conf_score,
            "confidence_tier": conf_tier,
            "confidence_description": status_text,
            "sample_size_h2h": h2h_cnt,
            "sample_size_team": team_cnt,
            "expected_goals": {"home": exp_home, "away": exp_away, "total": round(exp_home + exp_away, 2)},
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
                "market": best_pick[0],
                "selection": best_pick[1],
                "probability": best_pick[2],
                "fair_odds": best_pick[3]
            },
            "alternative_picks": [
                {
                    "market": alt[0],
                    "selection": alt[1],
                    "probability": alt[2],
                    "fair_odds": alt[3]
                }
                for alt in alt_picks
            ],
            "sub_models": {
                "poisson": res_poisson["markets"]["1x2"],
                "trend": res_trend["markets"]["1x2"],
                "ml": res_ml["markets"]["1x2"]
            },
            "reasoning": {
                "positive_factors": reasoning_pos,
                "negative_factors": reasoning_neg,
                "statistical_note": "Les résultats virtuels FIFA résultent de générateurs de nombres pseudo-aléatoires et de moteurs de jeu. Les probabilités indiquent une tendance statistique passée et ne constituent en aucun cas une garantie de résultat."
            }
        }
