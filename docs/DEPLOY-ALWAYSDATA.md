# Déploiement Alwaysdata — `pred-app`

Compte cible : **`elogededivo05417042`**
Hôte SSH : **`ssh-elogededivo05417042.alwaysdata.net`** (port 22) — l'hôte est en `.net`, pas `.com`.
API : `https://api.alwaysdata.com/v1` (token affiché une seule fois, 2FA obligatoire).

> Le kit de déploiement complet (préflight, upload, création des sites, redémarrage) est dans
> **`/home/user/deploy/`** — voir `deploy/README.md`. Ce document décrit la cible et les contraintes.

---

## 1. Topologie cible

```
┌────────────────────── Alwaysdata (compte elogededivo05417042) ──────────────────────┐
│                                                                                     │
│  /sites/pred-api/                    Site type « Node.js »                            │
│    ├── package.json, dist/, node_modules/                                           │
│    └── commande : node dist/main.js      → écoute $IP / $PORT                       │
│                                                                                     │
│  /sites/pred-ml/                     Site type « Programme utilisateur »             │
│    ├── app/ (FastAPI), .venv/                                                      │
│    └── commande : .venv/bin/uvicorn app.main:app --host :: --port $PORT             │
│                                                                                     │
│  /home/elogededivo05417042/pred-app/   clone git (sources, pipelines/, db/, deploy/) │
│  /home/elogededivo05417042/www/pred-flutter/  site statique Flutter web               │
│  /home/elogededivo05417042/.config/pred-app.env   secrets (chmod 600, hors dépôt)    │
│                                                                                     │
│  PostgreSQL managé : postgresql-elogededivo05417042.alwaysdata.net:5432              │
│  Redis             : 127.0.0.1:6380 (managé) ou service sur 8300-8499               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

Le client Flutter appelle l'API via `--dart-define=API_BASE=https://elogededivo05417042-pred-api.alwaysdata.net/api/v1`.

---

## 2. Contraintes Alwaysdata à ne pas oublier

| Contrainte | Conséquence |
|---|---|
| L'application HTTP doit écouter sur `IP`/`HOST` + `PORT` fournis par la plateforme | `main.ts` lit `process.env.IP \|\| process.env.HOST` et `process.env.PORT` ✔ |
| Python **3.11 / 3.12** | numpy / pandas / scikit-learn n'ont pas de wheels en 3.13 (compilation source = très long) |
| `node` (jamais `nodejs`) comme binaire | `NODEJS_VERSION` permet de forcer une version |
| Offre gratuite : 1 Go de disque, 256 Mo de RAM, ¼ CPU | `npm prune --omit=dev` après le build (~150 Mo gagnés) ; Redis à installer **en service** si le plan ne l'inclut pas |
| Les services occupy les ports **8300-8499** | Redis auto-installé : `redis://127.0.0.1:8380` |
| `max_idle_time` | mis à `0` (pas d'arrêt automatique de l'API) |
| Logs | `/home/<account>/admin/logs/sites/` et `…/admin/logs/http/` |

---

## 3. Variables d'environnement

### 3.1 Sur le serveur — `/home/elogededivo05417042/.config/pred-app.env` (chmod 600)

```bash
export DATABASE_URL=postgresql://<user>:<pass>@postgresql-elogededivo05417042.alwaysdata.net:5432/<db>
export REDIS_URL=redis://127.0.0.1:6380
export JWT_SECRET=<64 caractères aléatoires>

# Bookmaker BetB2B (gateway : https://cpservm.com/gateway/marketing)
export BOOKMAKER_API_BASE=https://cpservm.com/gateway/marketing
export BOOKMAKER_TOKEN_URL=https://cpservm.com/gateway/token
export MEGAPARI_CLIENT_ID=partners-c2b75a07c454fcd96f0453a0f79e1ead
export MEGAPARI_CLIENT_SECRET=<secret BRUT, entities HTML &amp; comprises>
export MEGAPARI_REF=192
export XBET_CLIENT_ID=partners-592d3a39b56e7ca211a846129d6fc5e3
export XBET_CLIENT_SECRET=<secret>
export XBET_REF=1

# Live Football API (rotation de 3 clés ; la clé 1 est inactive)
export LIVE_FOOTBALL_API_KEY=...
export LIVE_FOOTBALL_API_KEY_2=...
export LIVE_FOOTBALL_API_KEY_3=...

# Politique pays (fail-closed)
export ALLOWED_COUNTRIES=CI,CM,FR,BE,MA,SN,TG,BJ,ML,BF,NE,GN,GA,CG,CD,RW,KE,NG,GH,ZA
export ALLOW_COUNTRY_HEADER_FALLBACK=false
```

> ⚠️ **Le secret Méga Pari arrive avec les entités HTML `&amp;`** : collé tel quel dans un `.env` puis
> envoyé au bookmaker → `HTTP 400 {"error":"invalid_client"}`. Le code décode automatiquement
> (`&amp;` → `&`) ; conserver la valeur **brute** dans le fichier d'environnement.

### 3.2 Variables propres aux sites (dans la configuration Alwaysdata / `config.json`)

| Site | Variables |
|---|---|
| `pred-api` (Node.js) | `NODE_ENV=production`, `ML_PYTHON_URL=http://127.0.0.1:8200` |
| `pred-ml` (User program) | `PYTHONUNBUFFERED=1` |

> `ML_PYTHON_URL` pointait par défaut sur `http://ml-python:8000` (réseau Docker) : sans cette variable,
> l'API Node ne joint jamais le service Python. **Corrigé.**

---

## 4. Mise en production

```bash
cd /home/user/deploy
export ALWAYSDATA_API_TOKEN=...
export ALWAYSDATA_SSH_PASSWORD=...       # ou ALWAYSDATA_SSH_KEY=/chemin/cle

bash deploy.sh preflight    # vérifie API, SSH, disque, versions → "✅ Preflight OK"
bash deploy.sh all          # push + install + création/mise à jour des sites + restart
bash deploy.sh status       # sites + logs
```

`install.sh` (exécuté sur le serveur) enchaîne : synchronisation des sources vers les racines de site →
`npm install` + `npm run build` + `npm prune --omit=dev` → `venv` + `pip install -r requirements-prod.txt` →
migrations SQL → ETL bookmaker (contrôle live) → copie du build Flutter.

---

## 5. Pipeline bookmaker en production

```bash
cd /sites/pred-ml
ML_APP_DIR=/sites/pred-ml .venv/bin/python pipelines/etl/ingest_bookmaker_markets.py \
    --provider megapari --limit 50
```

Chaîne : OAuth2 BetB2B → flux LoadSingle v2 (ou LoadList) → adaptateur
(`app/core/betb2b_adapter.py`) → Margin Guard (marge ≤ 5 %, fail-closed) → cache Redis
`megapari:event:{event_id}` (TTL 15 min, cotes **en interne uniquement**).

Cron recommandé :

```cron
*/10 * * * * cd /sites/pred-ml && ML_APP_DIR=/sites/pred-ml .venv/bin/python pipelines/etl/ingest_bookmaker_markets.py --provider megapari --limit 50 >> /home/elogededivo05417042/logs/etl-bookmaker.log 2>&1
```

Limites de débit bookmaker à respecter : **1 requête / 5 s** (live), **1 requête / 20 s** (lignes).

---

## 6. Base de données

```bash
cd /home/elogededivo05417042/pred-app
for f in db/migrations/*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done
```

La base PostgreSQL managée doit être créée au préalable (Panel → Bases de données, ou `POST /v1/database/`).

---

## 7. Flutter web

Le dépôt ne contient que `lib/` + `pubspec.yaml` : les dossiers de plateforme (`web/`, `android/`, `ios/`)
sont **générés par la CI** (`flutter create . --platforms=web,android,ios`) avant `flutter build web`.
Le résultat est copié dans `/home/elogededivo05417042/www/pred-flutter/`.

---

## 8. Rollback

```bash
cd /home/elogededivo05417042/pred-app && git reset --hard <commit-precédent>
bash /home/elogededivo05417042/pred-app/deploy/install.sh all
python3 /home/user/deploy/alwaysdata.py restart
```

---

## 9. Ce qui n'est PAS déployé (volontairement)

- `main.py` et `start.sh` à la racine du dépôt (sonde de test avec des secrets par défaut) — exclus du déploiement.
- `docker-compose.yml` et les `Dockerfile` — Alwaysdata n'exécute pas Docker sur l'offre publique.
- Les secrets — jamais dans le dépôt ; uniquement via `ALWAYSDATA_*` (local) et `.config/pred-app.env` (serveur).
