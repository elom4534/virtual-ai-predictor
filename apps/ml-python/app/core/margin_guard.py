"""
Margin Guard — fail-closed, marge >5% = rejet.
Gère exclusifs 2/3 issues, Double Chance, sous-marchés lines.
"""
from typing import List, Dict, Any
import math
from app.utils.parsing import parse_odds, safe_implied_prob
from app.core.taxonomy import classify, MarketCategory

def compute_margin_exclusive(odds_list: List[float]) -> float | None:
    """marge% = (sum(1/odds) -1)*100 pour marchés exclusifs."""
    if not odds_list or len(odds_list) < 2:
        return None
    probs = []
    for o in odds_list:
        p = safe_implied_prob(o)
        if p is None:
            return None
        probs.append(p)
    s = sum(probs)
    return (s - 1.0) * 100.0

def compute_margin_double_chance(odds_dc: List[float], odds_1x2: List[float] | None = None) -> Dict[str, Any]:
    """
    Double Chance: 1X, X2, 12. Non exclusif — formule dédiée + contrôle cohérence.
    On calcule marge DC séparément, et si 1X2 disponible on vérifie cohérence.
    Règle: si cohérence écart >7% → rejet (marché incohérent).
    """
    margin_dc = compute_margin_exclusive(odds_dc)
    # cohérence vs 1X2: la somme des probas DC /2 devrait ≈1 (chevauchement)
    # Simplifié: on vérifie juste que margin_dc n'est pas aberrant et que les cotes DC sont cohérentes
    # Ex: si 1X2 = [2.0,3.0,4.0] alors P(1X)=0.5+0.33=0.83 → cote DC 1X ≈1.20
    coherence_ok = True
    if odds_1x2 and len(odds_1x2)==3 and margin_dc is not None:
        try:
            p1, px, p2 = [1/o for o in odds_1x2]
            implied_dc = [p1+px, px+p2, p1+p2]
            # comparer avec implied proba DC observée
            observed_p_dc = [1/o for o in odds_dc]
            diffs = [abs(a-b) for a,b in zip(implied_dc, observed_p_dc)]
            if max(diffs) > 0.07:
                coherence_ok = False
        except Exception:
            coherence_ok = False
    return {"margin_pct": margin_dc, "coherence_ok": coherence_ok}


# ---------------------------------------------------------------------------
# Double Chance — marge EFFECTIVE (le marché n'est pas exclusif)
# ---------------------------------------------------------------------------
_DC_LABELS = {"1X": ("HOME", "DRAW"), "12": ("HOME", "AWAY"), "2X": ("DRAW", "AWAY")}


def _dc_label_of(sel: Dict[str, Any]) -> str | None:
    """Identifie la sélection DC (1X / 12 / 2X) par son libellé ou ses tags."""
    name = str(sel.get("name") or "").strip().upper().replace(" ", "")
    if name in _DC_LABELS:
        return name
    tags = {str(t).strip().upper() for t in (sel.get("tags") or [])}
    for label, pair in _DC_LABELS.items():
        if set(pair) <= tags:
            return label
    return None


def evaluate_double_chance(
    selections: List[Dict[str, Any]],
    odds_1x2: List[float] | None = None,
) -> Dict[str, Any]:
    """
    Marge RÉELLE d'un marché Double Chance.

    La formule exclusive (Σ 1/o − 1) est invalide sur un marché non exclusif :
    pour 1X/12/2X elle renvoie ~100% (les issues se recouvrent) et tous les
    marchés DC seraient rejetés à tort.

    On inverse donc les 3 cotes DC pour retrouver les probabilités exclusives :

        p_1x = P1 + Px      p_12 = P1 + P2      p_2x = Px + P2

        P1 = (p_1x + p_12 − p_2x) / 2
        Px = (p_1x + p_2x − p_12) / 2
        P2 = (p_12 + p_2x − p_1x) / 2

    puis   marge% = (P1 + Px + P2 − 1) × 100

    Si les 3 issues ne peuvent pas être identifiées → marge None → le marché
    est rejeté (fail-closed).

    `odds_1x2` (optionnel) permet un contrôle de cohérence : si les
    probabilités inversées diffèrent de plus de 7 % des probabilités observées
    sur le marché 1X2 du même match → marché incohérent → rejet.
    """
    by_label: Dict[str, float] = {}
    for sel in selections or []:
        if not isinstance(sel, dict):
            continue
        label = _dc_label_of(sel)
        if not label:
            continue
        raw = sel.get("odds") if "odds" in sel else sel.get("odds_internal")
        odd = parse_odds(raw)
        if odd is None:
            return {"margin_pct": None, "coherence_ok": False, "reason_code": "INVALID_ODDS_FORMAT"}
        by_label[label] = odd

    if len(by_label) != 3:
        return {"margin_pct": None, "coherence_ok": False, "reason_code": "INCOMPLETE_DOUBLE_CHANCE"}

    p_1x = 1.0 / by_label["1X"]
    p_12 = 1.0 / by_label["12"]
    p_2x = 1.0 / by_label["2X"]

    p1 = (p_1x + p_12 - p_2x) / 2.0
    px = (p_1x + p_2x - p_12) / 2.0
    p2 = (p_12 + p_2x - p_1x) / 2.0

    # probabilités négatives → marché incohérent → fail-closed
    if p1 < -1e-9 or px < -1e-9 or p2 < -1e-9:
        return {"margin_pct": None, "coherence_ok": False, "reason_code": "DOUBLE_CHANCE_INCOHERENT"}

    margin = (p1 + px + p2 - 1.0) * 100.0

    coherence_ok = True
    if odds_1x2 and len(odds_1x2) == 3:
        try:
            obs = [1.0 / o for o in odds_1x2]
            diffs = [abs(a - b) for a, b in zip([p1, px, p2], obs)]
            if max(diffs) > 0.07:
                coherence_ok = False
        except Exception:
            coherence_ok = False

    return {
        "margin_pct": margin,
        "coherence_ok": coherence_ok,
        "implied_1x2": [p1, px, p2],
    }

def scan_markets(markets: List[Dict[str, Any]], threshold_pct: float = 5.0) -> Dict[str, List[Dict]]:
    validated = []
    rejected = []

    for m in markets:
        market_id = m.get("market_id", "unknown")
        market_type = m.get("market_type", "UNKNOWN")
        line = m.get("line")
        selections = m.get("selections", [])
        category = classify(market_type)

        if category == MarketCategory.REJECT:
            rejected.append({"market_id": market_id, "reason_code": "REJECT_CATEGORY", "category": str(category)})
            continue
        if not selections or len(selections) < 2:
            rejected.append({"market_id": market_id, "reason_code": "INCOMPLETE_MARKET"})
            continue

        # Parse odds
        parsed_odds = []
        valid_selections = []
        for s in selections:
            raw_odds = s.get("odds") if "odds" in s else s.get("odds_internal")
            parsed = parse_odds(raw_odds)
            if parsed is None:
                # une cote invalide → tout le marché rejeté (fail-closed)
                parsed_odds = None
                break
            parsed_odds.append(parsed)
            valid_selections.append(s)

        if parsed_odds is None:
            rejected.append({"market_id": market_id, "reason_code": "INVALID_ODDS_FORMAT"})
            continue

        # Calcul marge selon catégorie
        margin = None
        coherence_ok = True
        if category in (MarketCategory.EXCLUSIVE_2, MarketCategory.EXCLUSIVE_3, MarketCategory.HANDICAP):
            margin = compute_margin_exclusive(parsed_odds)
        elif category == MarketCategory.NON_EXCLUSIVE:
            # Double Chance : marché NON exclusif → on inverse les 3 cotes pour
            # obtenir la marge réelle du bookmaker (la formule exclusive donne
            # ~100 % et rejetterait tous les marchés DC à tort).
            odds_1x2 = m.get("_odds_1x2_ref")
            res = evaluate_double_chance(valid_selections, odds_1x2)
            margin = res["margin_pct"]
            coherence_ok = res["coherence_ok"]
            if not coherence_ok:
                rejected.append({
                    "market_id": market_id,
                    "margin_pct": round(margin, 2) if margin is not None else None,
                    "reason_code": res.get("reason_code") or "DOUBLE_CHANCE_INCOHERENT",
                })
                continue
        else:
            rejected.append({"market_id": market_id, "reason_code": "UNKNOWN_CATEGORY"})
            continue

        if margin is None:
            rejected.append({"market_id": market_id, "reason_code": "MARGIN_NOT_COMPUTABLE"})
            continue
        if math.isnan(margin) or math.isinf(margin):
            rejected.append({"market_id": market_id, "reason_code": "MARGIN_NAN_INF"})
            continue

        # Décision threshold
        if margin <= threshold_pct:
            # validated: chaque sélection est une option éligible
            for sel, odds in zip(valid_selections, parsed_odds):
                validated.append({
                    "market_id": market_id,
                    "market_type": market_type,
                    "line": line,
                    "selection_id": sel.get("selection_id"),
                    "margin_pct": round(margin, 2),
                    "reason_code": "OK",
                })
        else:
            rejected.append({
                "market_id": market_id,
                "margin_pct": round(margin, 2),
                "reason_code": "MARGIN_GT_5",
                "threshold": threshold_pct
            })

    return {"validated_options": validated, "rejected_options": rejected}

# Fonction utilitaire pour endpoint
def scan_event_markets(event_id: str, markets: List[Dict], threshold_pct: float = 5.0) -> Dict:
    result = scan_markets(markets, threshold_pct)
    return {
        "event_id": event_id,
        **result,
        "as_of": __import__("datetime").datetime.utcnow().isoformat() + "Z"
    }
