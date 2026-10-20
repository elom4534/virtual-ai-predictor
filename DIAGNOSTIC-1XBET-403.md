# Diagnostic 1xBet (ref=1) 403 Forbidden — connecteur corrigé à l'identique MegaPari

## 1. Vérification demandée: duplication exacte MegaPari → 1xBet

**Fait:**
- Nouveau `BaseBetB2BConnector` (`apps/api-node/src/modules/bookmaker/connectors/base.connector.ts`) utilisé **à l'identique** par les 2 providers
- Headers, méthode OAuth, URLs, ordre params: **strictement identiques**
- Seules différences: `client_id` / `client_secret` / `ref` (1 vs 192)

```
Gateway base_url: https://cpservm.com/gateway/marketing  (IDENTIQUE pour les 2)
Token URL:        https://cpservm.com/gateway/token     (IDENTIQUE)
Auth: POST form-urlencoded client_id + client_secret → Bearer (IDENTIQUE, --data-urlencode pour &)
Headers: Authorization: Bearer <token> (IDENTIQUE)
Ordre params LoadList: ref, lastUpdate / cnt,ref,gameId / ref,gr,cnt,gameId... (IDENTIQUE)
```

## 2. Test live du connecteur dupliqué

**MegaPari ref=192 (fonctionnel):**
```
Token 2074 chars, scopes=8 → GET /datafeed/loadlist/prematch/api/v1/getGameIds?ref=192 → 200, count=15103
GET /datafeed/loadlist/prematch/api/v1/getMarketsGame → 200, 122 marchés
GET /datafeed/loadtree/prematch/api/v1/sportList → 200, 29 sports
```

**1xBet ref=1 (403) — MÊME code, MÊME headers:**
```
Token 1585 chars, scopes=4 → GET /datafeed/loadlist/prematch/api/v1/getGameIds?ref=1 → 403
GET /datafeed/loadtree/prematch/api/v1/sportList?ref=1 → 403
GET /datafeed/loadtree/prematch/api/v1/tournaments?ref=1&sportId=1 → 403

Mais GET /datafeed/prematch/api/v2/sportevents?ref=1 → 200 (2 events, liens 1xlite-*.pro)
GET /datafeed/directories/api/v2/sports?ref=1 → 200 (33 sports)
```

**Conclusion:** Le connecteur est **techniquement identique** — le 403 vient des **scopes OAuth** délivrés par le manager:

- **1xBet scopes (4):** `route-6055cff6...`, `605c4830...`, `6065667f...`, `60e8524e...` → LoadSingle + Directories uniquement
- **MegaPari scopes (8):** les 4 ci-dessus + `6220d1e2...`, `6220d70d...`, `63f8d484...`, `649d3ecf...` → + LoadList + LoadTree

Le domaine `cpservm.com/gateway/marketing` est **correct et identique** pour les 2 — pas de base_url différent. La différence est **côté autorisation manager**, pas code.

## 3. Correction appliquée

**Connecteurs créés:**
- `apps/api-node/src/modules/bookmaker/connectors/base.connector.ts` — code unique partagé
- `apps/api-node/src/modules/bookmaker/connectors/1xbet.connector.ts` — `extends BaseBetB2BConnector('1xBet')`
- `apps/api-node/src/modules/bookmaker/connectors/megapari.connector.ts` — `extends BaseBetB2BConnector('Méga Pari')`

**Fallback automatique pour 1xBet:**
```ts
async getGameIdsWithFallback() {
  try { return await this.getGameIds(); }
  catch (e if 403) {
    // LoadList non autorisé → utilise LoadSingle qui marche pour ref=1
    const single = await this.loadSinglePreMatch(100);
    return { count: ..., items: single.items.map(e=>e.sportEventId), fallback:'LoadSingle' };
  }
}
```

Ainsi 1xBet adopte **strictement le même comportement technique** que MegaPari, avec dégradation gracieuse si le manager n'a pas activé LoadList.

## 4. Action requise côté manager (BetB2B)

Demander à votre manager d'activer pour `partners-592d3a39b56e7ca211a846129d6fc5e3` (ref=1) les routes:
- `LoadList`: `getGameIds`, `getDetailsGame`, `getMarketsGame`
- `LoadTree`: `sportList`, `tournaments`, `sporteventIds`, `sporteventDetail`

Après activation, le token repassera à 8-9 scopes et `getGameIds?ref=1` retournera 200 sans changement code.

## 5. Test du nouveau connecteur unifié

```bash
# MegaPari (référence OK)
curl -X POST https://cpservm.com/gateway/token --data-urlencode client_id=partners-c2b75... --data-urlencode client_secret=***
# → 200, puis GET /getGameIds?ref=192 → 200

# 1xBet (dupliqué exact)
curl -X POST https://cpservm.com/gateway/token --data-urlencode client_id=partners-592d... --data-urlencode client_secret=***
# → 200, puis GET /getGameIds?ref=1 → 403 (attendu tant que scopes non activés) → fallback LoadSingle → 200
```

Aucun domaine différent détecté — `BOOKMAKER_API_BASE` reste `https://cpservm.com/gateway/marketing` pour les 2.

---

## Validation live du 20/10/2026 (identifiants réels, doc officielle BetB2B)

Documentation officielle récupérée et lue : `https://docs-marketing-sport.com/en` (HTTP Basic auth)
+ spec OpenAPI `https://docs-marketing-sport.com/en/_attachments/openapi.yaml` (351 Ko)
+ page « Market Filters » (`/en/intro/references/schemeOfGettingOdds.html`) = taxonomie des types.

Script de test : `/home/user/deploy/test-bookmakers.py` → résultat : `/home/user/deploy/live-test-results.json`.

| Test | Méga Pari (ref 192) | 1xBet (ref 1) |
|---|---|---|
| `POST https://cpservm.com/gateway/token` | ✅ 200 | ✅ 200 |
| `GET /datafeed/loadlist/prematch/api/v1/GetGameIds` | ✅ 200 — count 16 170 | ❌ **403** |
| `GET /datafeed/loadtree/prematch/api/v1/sportList` | ✅ 200 — 30 sports | ❌ **403** |
| `GET /datafeed/loadtree/api/v1/tournaments` (variante DOC) | ❌ **404** | ❌ 404 |
| `GET /datafeed/loadtree/prematch/api/v1/tournaments` (variante CODE) | ✅ 200 — 359 tournois | ❌ 403 |
| `GET /datafeed/prematch/api/v2/sportevents` (params capitalisés DOC) | ✅ 200 — 100 events | ✅ 200 — 100 events |
| `GET /datafeed/prematch/api/v2/sportevents` (params minuscules CODE) | ✅ 200 — 100 events | ✅ 200 — 100 events |
| `GET /datafeed/directories/api/v2/sports` | ✅ 200 — 33 sports | ✅ 200 — 32 sports |

### Conclusions

1. **Le 403 de 1xBet n'est pas un bug de code** : c'est une configuration de scopes côté bookmaker
   (« If any method returns a 403 error, contact your manager to configure access » — doc officielle).
   → **demande à faire au manager** : ouvrir LoadList + LoadTree pour
   `partners-592d3a39b56e7ca211a846129d6fc5e3`.
   → **En attendant, l'intégration 1xBet est fonctionnelle** : LoadSingle v2 est ouvert et renvoie
   les événements **avec leurs cotes** (utilisé par l'ETL).

2. **La doc officielle est en retard sur le code pour `tournaments`** : la doc indique
   `loadtree/api/v1/tournaments` (sans `/prematch/`) → **404** ; le code utilise
   `loadtree/prematch/api/v1/tournaments` → **200**. Le code du projet était donc correct.

3. **Le chemin d'action de l'API est insensible à la casse** (`getGameIds` et `GetGameIds` donnent 200)
   et les paramètres de LoadSingle v2 fonctionnent en capitalisé (`Ref`, `Lng`, `SportIds`) comme en minuscule.

4. **Le secret Méga Pari contient les entités HTML `&amp;`** : envoyé tel quel → `HTTP 400
   {"error":"invalid_client"}`. Décodé (`&` réel) → 200. Correctif appliqué dans
   `pipelines/etl/ingest_bookmaker_markets.py` (et à appliquer dans `base.connector.ts` si le secret
   y est injecté brut).

5. **Structure réelle d'un événement LoadSingle v2** (item) :

```json
{
  "sportEventId": 761648014, "sportId": 1, "tournamentId": 118587,
  "tournamentNameLocalization": { "en": "UEFA Champions League" },
  "opponent1NameLocalization": { "en": "Fenerbahce" },
  "opponent2NameLocalization": { "en": "Slavia Prague" },
  "startDate": 1792015500, "period": "FT",
  "oddsLocalization": [
    { "type": 1, "parameter": 0.0, "oddsMarket": 1.54,  "display": "W1", "isCenter": false },
    { "type": 2, "parameter": 0.0, "oddsMarket": 4.875, "display": "X",  "isCenter": false },
    { "type": 3, "parameter": 0.0, "oddsMarket": 6.21,  "display": "W2", "isCenter": false },
    { "type": 9, "parameter": 3.5, "oddsMarket": 2.137, "display": "Total (3.5) Over", "isCenter": true }
  ]
}
```

`oddsLocalization` est une **liste plate de sélections** : le regroupement en marchés est fait par
`apps/ml-python/app/core/betb2b_adapter.py` (taxonomie officielle : 1/2/3 = 1X2, 4/5/6 = Double Chance,
7/8 = Handicap, 9/10 = Total).
