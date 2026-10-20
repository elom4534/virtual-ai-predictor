# Kit de déploiement Alwaysdata — `elogededivo05417042`

Déploiement reproductible du monorepo `pred-app` (NestJS + FastAPI + Flutter web)
sur l'hébergement Alwaysdata du compte **`elogededivo05417042`**.

---

## 1. Ce que fait le kit

| Commande | Effet |
|---|---|
| `bash deploy.sh preflight` | Vérifie **tout avant de toucher au serveur** : config, secrets, API Alwaysdata, SSH, versions, disque. Sort en code 1 avec la liste des bloqueurs. |
| `bash deploy.sh check` | Teste l'API Alwaysdata (token + compte) et liste les sites. |
| `bash deploy.sh push` | Envoie le code en SSH (archive `tar` + `ssh`, aucun `rsync` requis côté poste local). |
| `bash deploy.sh api` / `ml` / `flutter` / `migrations` / `etl` | Déploiement ciblé. |
| `bash deploy.sh all` | `push` → installation serveur → création/mise à jour des sites → redémarrage. |
| `bash deploy.sh status` | État des sites + dernières lignes des logs serveur. |

Sous-commandes équivalentes du kit Python : `python3 alwaysdata.py preflight|check|push|install|site|restart|deploy|status`.

---

## 2. Secrets (jamais dans le dépôt)

Trois éléments manquent pour déployer ; ils sont lus depuis l'environnement :

```bash
export ALWAYSDATA_API_TOKEN=...      # Panel > Profile > Tokens (affiché UNE seule fois, 2FA requis)
export ALWAYSDATA_SSH_PASSWORD=...   # ou ALWAYSDATA_SSH_KEY=/chemin/vers/cle
```

Sur le serveur, les secrets applicatifs vivent dans un fichier **hors dépôt** :

```bash
# /home/elogededivo05417042/.config/pred-app.env   (chmod 600)
export DATABASE_URL=postgresql://...
export REDIS_URL=redis://127.0.0.1:6380
export JWT_SECRET=...
export MEGAPARI_CLIENT_ID=...
export MEGAPARI_CLIENT_SECRET=...
export XBET_CLIENT_ID=...
export XBET_CLIENT_SECRET=...
export LIVE_FOOTBALL_API_KEY=...
```

> ⚠️ Le secret Méga Pari arrive avec les entités HTML `&amp;`. Envoyé tel quel → `{"error":"invalid_client"}`.
> Le code le décode automatiquement (`&amp;` → `&`) : coller la valeur **brute** dans le fichier.

---

## 3. Disposition cible sur le serveur

```
/home/elogededivo05417042/pred-app/     clone git (sources, pipelines/, db/, deploy/)
/sites/pred-api/                        site Node.js      → NestJS   (node dist/main.js)
/sites/pred-ml/                         site User program → FastAPI  (uvicorn … --port $PORT)
/home/elogededivo05417042/www/pred-flutter/   site statique Flutter web
/home/elogededivo05417042/.config/pred-app.env   secrets (chmod 600)
```

Points d'attention Alwaysdata :

- L'hôte SSH est en **`.net`** : `ssh-elogededivo05417042.alwaysdata.net` (port 22).
- PostgreSQL managé : `postgresql-elogededivo05417042.alwaysdata.net:5432`.
- Redis managé : `127.0.0.1:6380` (si le plan l'inclut) — sinon installer Redis en **service**
  (ports 8300‑8499, ex. `REDIS_URL=redis://127.0.0.1:8380`).
- Une application HTTP doit écouter sur `IP`/`HOST` + `PORT` fournis par la plateforme
  (`main.ts` lit `process.env.IP || process.env.HOST` et `process.env.PORT`).
- Python **3.11 ou 3.12** obligatoire (numpy/pandas/scikit-learn n'ont pas de wheels en 3.13).
- L'offre gratuite (1 Go / 256 Mo / ¼ CPU) est serrée : `npm prune --omit=dev` est appliqué
  après le build pour économiser ~150 Mo.

---

## 4. Première mise en production

```bash
cd /home/user/deploy
export ALWAYSDATA_API_TOKEN=...
export ALWAYSDATA_SSH_PASSWORD=...

bash deploy.sh preflight      # → doit finir par "✅ Preflight OK"
bash deploy.sh push           # upload du code
bash deploy.sh all            # install + création des sites + redémarrage
bash deploy.sh status         # vérification
```

Après la première création de site, `alwaysdata.py site` affiche les identifiants :
renseigner `"id"` dans `config.json` (section `sites`) pour que les redémarrages ciblent
les bons sites.

---

## 5. Intégrations bookmaker (validées en ligne)

| Provider | Client ID | Ref | Accès constaté |
|---|---|---|---|
| Méga Pari | `partners-c2b75a07c454fcd96f0453a0f79e1ead` | 192 | LoadList + LoadTree + LoadSingle ✔ |
| 1xBet | `partners-592d3a39b56e7ca211a846129d6fc5e3` | 1 | LoadSingle ✔ — LoadList/LoadTree en **403** (scopes à ouvrir côté manager) |

Gateway : `https://cpservm.com/gateway/marketing` — token : `POST https://cpservm.com/gateway/token`.

Le pipeline réel est `pipelines/etl/ingest_bookmaker_markets.py` :

```bash
cd /sites/pred-ml
ML_APP_DIR=/sites/pred-ml .venv/bin/python pipelines/etl/ingest_bookmaker_markets.py \
    --provider megapari --limit 25
```

Il enchaîne : OAuth2 → flux BetB2B → adaptateur (`app/core/betb2b_adapter.py`) →
Margin Guard (marge ≤ 5 %, fail-closed) → cache Redis (`megapari:event:{id}`, TTL 15 min).

---

## 6. Cron recommandé (côté serveur)

```cron
*/10 * * * * cd /sites/pred-ml && ML_APP_DIR=/sites/pred-ml .venv/bin/python pipelines/etl/ingest_bookmaker_markets.py --provider megapari --limit 50 >> /home/elogededivo05417042/logs/etl-bookmaker.log 2>&1
```

---

## 7. Fichiers

| Fichier | Rôle |
|---|---|
| `alwaysdata.py` | Kit Python : API Alwaysdata + SSH (upload tar, install, sites, restart, preflight). |
| `deploy.sh` | Wrapper local : orchestre le kit et les étapes ciblées. |
| `install.sh` | Script **serveur** : synchronisation des sources vers les racines de site, builds, migrations, ETL. |
| `config.json` | Cible (compte, hôtes, sites, commandes). Aucun secret. |
| `config.example.json` | Modèle de configuration. |
| `secrets.env` | Secrets locaux (**hors dépôt**, chmod 600). |
| `test-bookmakers.py` | Test live des deux bookmakers (token, LoadList/LoadTree/LoadSingle, répertoires). |
| `capture-fixtures.py` / `capture-loadsingle.py` | Capture de payloads réels → fixtures de test. |
| `live-test-results.json` | Résultat du test live du 20/10/2026. |
