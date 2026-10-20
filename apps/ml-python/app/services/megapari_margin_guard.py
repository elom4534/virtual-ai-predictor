"""
MegaPari Margin Guard & Caching Service — Python / FastAPI
Fail-Closed, production-ready, réutilisable 1xBet (même logique, ref différent)

Flux:
  LoadList/LoadSingle → Extraction marchés → Margin Guard (≤5%) → Redis 15min → Payload nettoyé (sans cotes)

Auteur: Backend Trading Sportif
"""
import math
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import redis.asyncio as redis  # async Redis
import os

from app.core.betb2b_adapter import adapt_betb2b_event
from app.core.margin_guard import evaluate_double_chance

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_TTL_SECONDS = 15 * 60  # 15 minutes — pré-match uniquement
MARGIN_THRESHOLD = 5.0  # %
PROVIDER = "MEGAPARI"

_redis_client: Optional[redis.Redis] = None

async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True, health_check_interval=10)
    return _redis_client

# ---------------------------------------------------------------------------
# Parsing robuste cotes — Fail-Closed sur toute anomalie
# ---------------------------------------------------------------------------
def parse_odds(raw: Any) -> Optional[float]:
    """Gère None, '', '1,85'→1.85, 0, -1, NaN, inf, manquant → None (rejet)"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
    elif isinstance(raw, str):
        s = raw.strip()
        if s == "":
            return None
        s = s.replace(",", ".")  # virgule décimale FR
        try:
            val = float(s)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    if val <= 1.0:  # cote ≤1 invalide (bookmaker ne propose jamais 1.0)
        return None
    if val > 1000:  # aberrant (erreur feed)
        return None
    return val

def implied_prob(odds: float) -> Optional[float]:
    try:
        if odds is None or odds <= 1.0:
            return None
        return 1.0 / odds
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Margin Guard — Formules trading sportif
# ---------------------------------------------------------------------------
def compute_margin_exclusive(odds_list: List[float]) -> Optional[float]:
    """
    Marchés exclusifs 2/3 issues (1X2, O/U, BTTS):
      marge% = (sum(1/odds) - 1) * 100
    Ex: [1.95, 1.95] → (0.5128+0.5128-1)*100 = 2.56% → validé
        [2.0, 3.0, 4.0] → 8.33% → rejet
    """
    if not odds_list or len(odds_list) < 2:
        return None
    probs = []
    for o in odds_list:
        p = implied_prob(o)
        if p is None:
            return None
        probs.append(p)
    return (sum(probs) - 1.0) * 100.0

def compute_margin_double_chance(odds_dc: List[float], odds_1x2: Optional[List[float]] = None) -> Dict[str, Any]:
    """
    Double Chance (non-exclusif): 1X, X2, 12
    Formule dédiée + contrôle cohérence vs 1X2 si disponible.
    Si écart >7% entre DC théorique et observé → rejet (marché incohérent)
    """
    margin_dc = compute_margin_exclusive(odds_dc)
    coherence_ok = True
    if odds_1x2 and len(odds_1x2) == 3 and margin_dc is not None:
        try:
            p1, px, p2 = [1/o for o in odds_1x2]
            theoretical = [p1+px, px+p2, p1+p2]  # P(1X), P(X2), P(12)
            observed = [1/o for o in odds_dc]
            diffs = [abs(a-b) for a, b in zip(theoretical, observed)]
            if max(diffs) > 0.07:
                coherence_ok = False
        except Exception:
            coherence_ok = False
    return {"margin_percent": margin_dc, "coherence_ok": coherence_ok}

# Taxonomie marchés (réutilisable 1xBet)
MARKET_CATEGORY = {
    "1X2": "exclusive_3",
    "OVER_UNDER": "exclusive_2",
    "BTTS": "exclusive_2",
    "CORNERS_OU": "exclusive_2",
    "DOUBLE_CHANCE": "non_exclusive",
    "HANDICAP": "handicap",
}

def classify_market(market_type: str) -> str:
    return MARKET_CATEGORY.get(market_type.upper(), "reject")

# ---------------------------------------------------------------------------
# Extraction marchés depuis flux MegaPari (LoadList / LoadSingle)
# ---------------------------------------------------------------------------
def extract_markets_from_megapari(raw_event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalise un payload BetB2B brut (LoadSingle v2 / LoadList v1) en marchés
    internes.

    ⚠️ Point critique : le flux BetB2B renvoie une liste PLATE de SÉLECTIONS
    (type / parameter / oddsMarket / display), pas des marchés groupés.
    Le regroupement (1X2 = types 1+2+3, Total = types 9+10, Handicap = 7+8)
    est fait par app.core.betb2b_adapter — source de vérité unique, testée
    sur des payloads réels capturés.

    Sans ce regroupement, chaque sélection est vue comme un marché à une
    seule option → 100 % des marchés réels rejetés (SINGLE_SELECTION_NO_PAIR).
    """
    adapted = adapt_betb2b_event(raw_event)
    if adapted and adapted.get("markets"):
        return adapted["markets"]

    # Repli : payload déjà groupé mais non conforme à l'adaptateur
    mkts = raw_event.get("markets") if isinstance(raw_event, dict) else None
    if isinstance(mkts, list):
        out = []
        for rm in mkts:
            if not isinstance(rm, dict):
                continue
            sels = rm.get("selections") or rm.get("outcomes") or []
            out.append({
                "market_id": str(rm.get("market_id") or rm.get("id") or rm.get("marketId") or "mkt"),
                "market_type": rm.get("market_type") or rm.get("name") or "UNKNOWN",
                "line": rm.get("line"),
                "selections": [{
                    "selection_id": str(s.get("selection_id") or s.get("id") or s.get("name") or idx),
                    "name": str(s.get("name") or s.get("display", "")),
                    "odds": s.get("odds") if s.get("odds") is not None else s.get("price"),
                    "tags": s.get("tags", []),
                } for idx, s in enumerate(sels) if isinstance(s, dict)],
                "is_blocked": bool(rm.get("is_blocked")),
            })
        return out
    return []

# ---------------------------------------------------------------------------
# Service principal — Margin Guard + Redis Cache
# ---------------------------------------------------------------------------
async def process_and_cache_event(
    raw_event: Dict[str, Any],
    provider: str = PROVIDER,
    threshold: float = MARGIN_THRESHOLD,
    cache: bool = True,
) -> Dict[str, Any]:
    """
    Traite 1 event MegaPari:
      1. Extraction marchés
      2. Margin Guard strict (≤5% ou rejet Fail-Closed)
      3. Cache Redis 15min
      4. Retour payload nettoyé SANS cotes (prêt Selection Engine)

    Returns:
      {
        event_id, provider, validated_markets: [{market_id, market_type, margin_percent, selections: [{selection_id, name, tags}]}],
        rejected: [{market_id, reason_code, margin_percent}],
        cached_key, as_of
      }
    """
    event_id = str(raw_event.get("id") or raw_event.get("gameId") or raw_event.get("sportEventId") or "")
    if not event_id:
        return {"error": "MISSING_EVENT_ID", "reason_code": "MISSING_EVENT_ID"}

    # Extraction
    markets = extract_markets_from_megapari(raw_event)
    # Fallback: si raw_event contient déjà des marchés normalisés (tests)
    if not markets and raw_event.get("markets"):
        markets = raw_event["markets"]

    validated = []
    rejected = []

    for m in markets:
        if m.get("is_blocked"):
            rejected.append({"market_id": m["market_id"], "reason_code": "MARKET_BLOCKED"})
            continue
        sels = m.get("selections", [])
        if not sels or len(sels) < 1:
            rejected.append({"market_id": m["market_id"], "reason_code": "INCOMPLETE_MARKET"})
            continue

        # Parsing cotes — toute cote invalide → rejet marché entier (Fail-Closed)
        parsed_odds = []
        valid_sels = []
        for s in sels:
            raw_odds = s.get("odds") if "odds" in s else s.get("odds_internal")
            parsed = parse_odds(raw_odds)
            if parsed is None:
                parsed_odds = None
                break
            parsed_odds.append(parsed)
            valid_sels.append(s)

        if parsed_odds is None:
            rejected.append({"market_id": m["market_id"], "reason_code": "INVALID_ODDS_FORMAT"})
            continue

        # Pour les marchés BetB2B 1-sélection (type 9 seul), on ne peut calculer marge seul
        # → on attend la paire (type 9 + 10) — si seul, on le garde en pending et on le pairera
        # Ici simplifié: si 1 seule cote → on ne peut calculer marge → rejet Fail-Closed sauf si on a la paire
        if len(parsed_odds) == 1:
            # Tentative de paire: chercher l'autre côté dans les marchés voisins (même parameter, type complémentaire)
            # Pour MVP, on rejette les marchés singletons (manque données)
            rejected.append({"market_id": m["market_id"], "reason_code": "SINGLE_SELECTION_NO_PAIR"})
            continue

        # Calcul marge
        mtype = m.get("market_type", "OVER_UNDER")
        category = classify_market(mtype)
        margin = None
        coherence_ok = True

        if category in ("exclusive_2", "exclusive_3", "handicap"):
            margin = compute_margin_exclusive(parsed_odds)
        elif category == "non_exclusive":
            # Double Chance : marché NON exclusif → la formule exclusive donnerait
            # ~100 % et rejetterait tous les marchés DC à tort.
            # On inverse les 3 cotes (P1, Px, P2) pour obtenir la marge réelle.
            res_dc = evaluate_double_chance(valid_sels, m.get("_odds_1x2_ref"))
            margin = res_dc.get("margin_pct")
            coherence_ok = res_dc.get("coherence_ok", True)
            if not coherence_ok:
                rejected.append({
                    "market_id": m["market_id"],
                    "margin_percent": round(margin, 2) if margin is not None else None,
                    "reason_code": res_dc.get("reason_code") or "DOUBLE_CHANCE_INCOHERENT",
                })
                continue
        else:
            rejected.append({"market_id": m["market_id"], "reason_code": "REJECT_CATEGORY"})
            continue

        if margin is None or math.isnan(margin) or math.isinf(margin):
            rejected.append({"market_id": m["market_id"], "reason_code": "MARGIN_NOT_COMPUTABLE"})
            continue

        margin = round(margin, 2)
        if margin <= threshold:
            # Validé — la cote est conservée en INTERNE (_odds) pour le calcul
            # d'EV du Selection Engine ; elle est retirée du payload public.
            validated.append({
                "market_id": m["market_id"],
                "market_type": mtype,
                "line": m.get("line"),
                "margin_percent": margin,
                "selections": [
                    {"selection_id": s["selection_id"], "name": s["name"], "tags": s.get("tags", []), "_odds": odd}
                    for s, odd in zip(valid_sels, parsed_odds)
                ],
                "reason_code": "OK",
            })
        else:
            rejected.append({"market_id": m["market_id"], "margin_percent": margin, "reason_code": "MARGIN_GT_5"})

    # 3. Cache Redis 15min — clé = megapari:event:{event_id}
    #    Le cache est INTERNE : il porte les cotes (`selections[].odds`) car le
    #    Selection Engine a besoin de la valeur pour calculer l'EV.
    #    Le payload PUBLIC retourné est nettoyé (cf. return plus bas).
    as_of = datetime.now(timezone.utc).isoformat()
    cache_markets = [
        {**vm, "selections": [{**s, "odds": s.get("_odds")} for s in vm["selections"]]}
        for vm in validated
    ]
    cache_payload = {
        "event_id": event_id,
        "provider": provider,
        "validated_markets": cache_markets,
        "rejected": rejected,
        "as_of": as_of,
        "model_version": "v0.3.0",
    }

    # On stocke en Redis (TTL 15min) — pour Selection Engine + pré-calcul picks
    cache_ok = False
    redis_key = f"megapari:event:{event_id}"
    if not cache:
        # Mode dry-run / calcul seul : aucun accès Redis.
        redis_key = None
    else:
        try:
            r = await get_redis()
            await r.set(redis_key, json.dumps(cache_payload, ensure_ascii=False), ex=REDIS_TTL_SECONDS)
            cache_ok = True
            # Aussi index par start_time pour requêtes rapides (zset)
            start_time = raw_event.get("start_time") or raw_event.get("startDate")
            if start_time:
                await r.zadd("megapari:events:by_time", {event_id: float(start_time) if isinstance(start_time, (int, float)) else 0})
        except Exception as e:
            # Redis down → Fail-Closed: on log mais on retourne quand même le payload (pas de cache)
            print(f"[MEGAPARI CACHE ERROR] {e} — fallback sans Redis")

    # 4. Payload PUBLIC nettoyé — SANS cotes (règle « ne jamais exposer les cotes »)
    public_markets = [
        {
            **vm,
            "selections": [
                {k: v for k, v in s.items() if k not in ("_odds", "odds")}
                for s in vm["selections"]
            ],
        }
        for vm in validated
    ]

    return {
        "event_id": event_id,
        "provider": provider,
        "validated_markets": public_markets,
        "rejected": rejected,
        # cached_key = None si l'écriture Redis a échoué : ne jamais annoncer
        # un cache qui n'existe pas (sinon l'appelant croit le payload en mémoire).
        "cached_key": redis_key if cache_ok else None,
        "ttl_seconds": REDIS_TTL_SECONDS,
        "as_of": as_of,
    }

# ---------------------------------------------------------------------------
# Helper — purge des cotes (règle « ne jamais exposer les cotes »)
# ---------------------------------------------------------------------------
def strip_odds(payload: Any) -> Any:
    """
    Retourne une copie du payload sans AUCUNE cote.

    Utilisé par les endpoints publics (ingest, cache) : le cache Redis
    interne conserve les cotes (EV), mais rien ne doit sortir vers le client.
    """
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            if k in ("_odds_internal", "odds", "_odds", "oddsMarket", "oddsMarketView"):
                continue
            out[k] = strip_odds(v)
        return out
    if isinstance(payload, list):
        return [strip_odds(v) for v in payload]
    return payload


# ---------------------------------------------------------------------------
# Helper batch — pour endpoint FastAPI POST /megapari/ingest
# ---------------------------------------------------------------------------
async def process_batch_megapari(raw_events: List[Dict[str, Any]], threshold: float = MARGIN_THRESHOLD) -> Dict[str, Any]:
    results = []
    for raw in raw_events:
        res = await process_and_cache_event(raw, threshold=threshold)
        results.append(res)
    return {
        "provider": PROVIDER,
        "processed": len(results),
        "events": results,
        "threshold": threshold,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
