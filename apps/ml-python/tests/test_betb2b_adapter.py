"""
Tests de l'adaptateur BetB2B — sur des PAYLOADS RÉELS capturés en production.

Fixture : tests/fixtures/betb2b_loadsingle_real.json
  → 3 événements réels (LoadSingle v2, GET /datafeed/prematch/api/v2/sportevents)
  → payload BetB2B réel : UEFA Champions League, cotes décimales réelles.

Ces tests verrouillent le point le plus fragile du projet : le flux BetB2B
renvoie une liste PLATE de sélections, pas des marchés groupés.
"""
import json
import sys
from pathlib import Path

sys.path.append("..")

from app.core.betb2b_adapter import (
    MARKET_TYPE_SPEC,
    adapt_betb2b_event,
    group_selections_into_markets,
    extract_flat_selections,
)
from app.core.normalizer import normalize_event
from app.core.margin_guard import scan_markets, evaluate_double_chance

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "betb2b_loadsingle_real.json"


def _load_items():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data["response"]["items"]


def test_taxonomie_couvre_les_types_du_flux_reel():
    """Les types réellement présents dans le flux doivent être tous taxonomisés."""
    items = _load_items()
    types_seen = set()
    for it in items:
        for sel in it.get("oddsLocalization") or []:
            types_seen.add(sel.get("type"))
    inconnus = {t for t in types_seen if t not in MARKET_TYPE_SPEC}
    assert not inconnus, f"types BetB2B non taxonomisés : {inconnus}"


def test_adaptation_event_reel():
    """Métadonnées d'un événement réel (équipes, ligue, heure, cotes)."""
    items = _load_items()
    raw = adapt_betb2b_event(items[0])
    assert raw is not None
    assert raw["id"] == str(items[0]["sportEventId"])
    assert raw["home"] and raw["away"]
    assert raw["league"]
    assert raw["start_time"].startswith("20")


def test_groupement_en_marches():
    """1X2 = types 1+2+3 ; Double Chance = 4+5+6 ; Handicap = 7+8 ; Total = 9+10."""
    items = _load_items()
    raw = adapt_betb2b_event(items[0])
    by_type = {m["market_type"]: m for m in raw["markets"]}

    assert "1X2" in by_type
    assert len(by_type["1X2"]["selections"]) == 3
    assert [s["name"] for s in by_type["1X2"]["selections"]] == ["1", "X", "2"]
    assert {s["tags"][0] for s in by_type["1X2"]["selections"]} == {"HOME", "DRAW", "AWAY"}

    assert "DOUBLE_CHANCE" in by_type
    assert len(by_type["DOUBLE_CHANCE"]["selections"]) == 3

    assert "HANDICAP" in by_type
    assert len(by_type["HANDICAP"]["selections"]) == 2
    assert by_type["HANDICAP"]["line"] is not None

    assert "OVER_UNDER" in by_type
    assert len(by_type["OVER_UNDER"]["selections"]) == 2
    assert {s["tags"][0] for s in by_type["OVER_UNDER"]["selections"]} == {"OVER", "UNDER"}

    # Toutes les cotes doivent être des décimales valides
    for m in raw["markets"]:
        for s in m["selections"]:
            assert isinstance(s["odds"], float)
            assert s["odds"] > 1.0


def test_normalizer_sur_payload_reel():
    """Le normalizer doit produire le schéma interne stable à partir du réel."""
    items = _load_items()
    raw = adapt_betb2b_event(items[0])
    norm, err = normalize_event(raw, provider="MEGAPARI")
    assert err is None, err
    assert norm is not None
    assert norm["event_id"] == raw["id"]
    assert norm["home"] == raw["home"] and norm["away"] == raw["away"]
    assert len(norm["markets"]) >= 4
    types = {m["market_type"] for m in norm["markets"]}
    assert {"1X2", "DOUBLE_CHANCE", "HANDICAP", "OVER_UNDER"} <= types


def test_margin_guard_sur_payload_reel():
    """
    Le Margin Guard doit valider au moins le 1X2 et le Total réels,
    et le Double Chance doit être calculé via l'inversion des probabilités
    (et non la formule exclusive qui donnerait ~100 %).
    """
    items = _load_items()
    raw = adapt_betb2b_event(items[0])
    norm, _ = normalize_event(raw, provider="MEGAPARI")
    res = scan_markets(norm["markets"], threshold_pct=5.0)

    validated_types = {o["market_type"] for o in res["validated_options"]}
    assert "1X2" in validated_types
    assert "OVER_UNDER" in validated_types
    assert "DOUBLE_CHANCE" in validated_types, "le DC doit passer via l'inversion de probabilités"

    # La marge du 1X2 est recalculée à partir des cotes réelles de la fixture
    one_x_two = next(m for m in norm["markets"] if m["market_type"] == "1X2")
    expected = (sum(1.0 / s["odds"] for s in one_x_two["selections"]) - 1.0) * 100.0
    margins = {o["market_type"]: o["margin_pct"] for o in res["validated_options"]}
    assert abs(margins["1X2"] - expected) < 0.01
    assert 0.0 < expected <= 5.0, "la marge du 1X2 réel doit être ≤ 5 %"


def test_double_chance_inversion():
    """Inversion DC : 3 cotes DC → probabilités exclusives → marge réelle."""
    sels = [
        {"name": "1X", "odds": 1.156, "tags": ["HOME", "DRAW"]},
        {"name": "12", "odds": 1.218, "tags": ["HOME", "AWAY"]},
        {"name": "2X", "odds": 2.657, "tags": ["DRAW", "AWAY"]},
    ]
    res = evaluate_double_chance(sels)
    assert res["margin_pct"] is not None
    assert 1.0 < res["margin_pct"] < 6.0, res
    assert res["coherence_ok"] is True

    # DC incomplet → fail-closed
    assert evaluate_double_chance(sels[:2])["margin_pct"] is None


def test_loadlist_shape_details_plus_selections():
    """Payload worker Node : {id, details:{...}, selections:[...]} (liste plate)."""
    items = _load_items()
    it = items[0]
    payload = {
        "id": str(it["sportEventId"]),
        "provider": "MEGAPARI",
        "details": it,
        "selections": it["oddsLocalization"],
    }
    flat = extract_flat_selections(payload)
    assert len(flat) >= 10
    raw = adapt_betb2b_event(payload)
    assert raw is not None
    assert len(raw["markets"]) >= 4
    assert raw["home"] and raw["away"]


def test_fail_closed_types_inconnus_et_marches_incomplets():
    """Un type hors taxonomie est ignoré ; un marché à une seule issue est rejeté."""
    markets = group_selections_into_markets(
        [
            {"type": 1, "parameter": 0.0, "oddsMarket": 1.9, "display": "W1"},
            {"type": 2, "parameter": 0.0, "oddsMarket": 3.5, "display": "X"},
            {"type": 999999, "parameter": 0.0, "oddsMarket": 2.0, "display": "EXOTIQUE"},
            {"type": 9, "parameter": 2.5, "oddsMarket": 1.9, "display": "Over"},  # Over seul
        ],
        "evt_test",
    )
    types = {m["market_type"] for m in markets}
    assert types == {"1X2"}, "seul le 1X2 complet doit être conservé"
    assert all(len(m["selections"]) >= 2 for m in markets)


def test_marche_bloque_signale():
    """Un marché dont une sélection est isBlocked est marqué is_blocked."""
    markets = group_selections_into_markets(
        [
            {"type": 1, "parameter": 0.0, "oddsMarket": 1.9, "isBlocked": True},
            {"type": 2, "parameter": 0.0, "oddsMarket": 3.5},
            {"type": 3, "parameter": 0.0, "oddsMarket": 4.0},
        ],
        "evt_blocked",
    )
    assert len(markets) == 1
    assert markets[0]["is_blocked"] is True


if __name__ == "__main__":
    test_taxonomie_couvre_les_types_du_flux_reel()
    test_adaptation_event_reel()
    test_groupement_en_marches()
    test_normalizer_sur_payload_reel()
    test_margin_guard_sur_payload_reel()
    test_double_chance_inversion()
    test_loadlist_shape_details_plus_selections()
    test_fail_closed_types_inconnus_et_marches_incomplets()
    test_marche_bloque_signale()
    print("Tous les tests adaptateur BetB2B OK (payloads réels)")
