#!/bin/bash
# ============================================================================
#  Installation Alwaysdata — exécuté SUR LE SERVEUR (compte `god`).
#
#  Disposition cible :
#    /home/god/                      racine du site « Programme utilisateur »
#      ├── main.py                   point d'entrée (`uvicorn main:app`)
#      ├── app/                      package FastAPI (edge + routers ML)
#      ├── .venv/                    Python 3.12 + dépendances de production
#      ├── .local/bin/uvicorn        wrapper (le site appelle `uvicorn` nu)
#      ├── launch_node.sh            démarrage du service NestJS interne
#      ├── www/web/                  build Flutter web (statique)
#      └── .config/pred-app.env      secrets (chmod 600, hors dépôt)
#    /home/god/pred-app/             clone git (sources, pipelines/, db/, deploy/)
#
#  Usage : bash install.sh [all|api|ml|migrations|etl|flutter]
# ============================================================================
set -euo pipefail

ACCOUNT="${ACCOUNT:-god}"
HOME_DIR="${HOME_DIR:-/home/$ACCOUNT}"
REPO_DIR="${REPO_DIR:-$HOME_DIR/pred-app}"
SITE_DIR="${SITE_DIR:-$HOME_DIR}"
ML_DIR="${ML_DIR:-$SITE_DIR}"
API_DIR="${API_DIR:-$REPO_DIR/apps/api-node}"
WEB_DIR="${WEB_DIR:-$HOME_DIR/www/web}"
ENV_FILE="${ENV_FILE:-$HOME_DIR/.config/pred-app.env}"
TARGET="${1:-all}"

log() { echo "[install $(date -u +%H:%M:%S)] $*"; }

if [ -f "$ENV_FILE" ]; then
  log "Chargement de $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  log "⚠️  $ENV_FILE absent — les secrets applicatifs ne seront pas définis"
fi

# --------------------------------------------------------------- synchronisation --
sync_sources() {
  log "Synchronisation des sources"
  mkdir -p "$SITE_DIR" "$API_DIR" "$HOME_DIR/.local/bin" "$HOME_DIR/admin/tmp"

  # --- API FastAPI : le site lance `uvicorn main:app` depuis $SITE_DIR ---
  rsync -a --delete \
    --exclude .venv --exclude __pycache__ --exclude .env --exclude .git \
    "$REPO_DIR/apps/ml-python/app/" "$SITE_DIR/app/"
  cp -f "$REPO_DIR/apps/ml-python/requirements-prod.txt" "$SITE_DIR/requirements-prod.txt"
  cp -f "$REPO_DIR/apps/ml-python/requirements.txt" "$SITE_DIR/requirements.txt"

  # --- Point d'entrée + utilitaires du site ---
  cp -f "$REPO_DIR/deploy/server/main.py" "$SITE_DIR/main.py"
  cp -f "$REPO_DIR/deploy/server/launch_node.sh" "$SITE_DIR/launch_node.sh"
  chmod +x "$SITE_DIR/launch_node.sh"
  cat > "$HOME_DIR/.local/bin/uvicorn" <<'WRAPPER'
#!/bin/bash
# Wrapper : le site appelle `uvicorn` (sans chemin) — on pointe vers le venv.
exec /home/god/.venv/bin/uvicorn "$@"
WRAPPER
  chmod +x "$HOME_DIR/.local/bin/uvicorn"

  # --- API NestJS (interne, 127.0.0.1:3000) ---
  rsync -a --delete \
    --exclude node_modules --exclude dist --exclude .env --exclude .git \
    "$REPO_DIR/apps/api-node/" "$API_DIR/"

  # --- Pipelines + migrations accessibles depuis le site ---
  mkdir -p "$SITE_DIR/pipelines"
  rsync -a "$REPO_DIR/pipelines/" "$SITE_DIR/pipelines/"
  log "  ✓ sources synchronisées"
}

# ------------------------------------------------------------------ API Node --
deploy_api() {
  log "API Node : dépendances + build"
  cd "$API_DIR"
  # ⚠️ Avec NODE_ENV=production, `npm install` OMET les devDependencies
  #    (typescript, @nestjs/cli) → le build échoue avec « nest: not found ».
  #    On installe donc explicitement les dev deps, on build, puis on purge.
  NODE_ENV=development npm install --include=dev --no-audit --no-fund
  NODE_ENV=development npm run build
  npm prune --omit=dev --no-audit --no-fund || true
  log "  ✓ build dist/main.js : $(du -h dist/main.js 2>/dev/null | cut -f1)"
}

# ------------------------------------------------------------------ API Python --
deploy_ml() {
  log "API Python : venv + dépendances de production"
  cd "$SITE_DIR"
  # Python 3.11/3.12 requis (numpy/pandas/scikit-learn n'ont pas de wheels en 3.13)
  PY_BIN="${PY_BIN:-python3}"
  if ! "$PY_BIN" -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)'; then
    for candidate in python3.12 python3.11 python3.10; do
      if command -v "$candidate" >/dev/null 2>&1; then PY_BIN="$candidate"; break; fi
    done
  fi
  log "  python : $("$PY_BIN" --version 2>&1)"
  [ -d .venv ] || "$PY_BIN" -m venv .venv
  .venv/bin/pip install --upgrade pip --quiet
  .venv/bin/pip install -r requirements-prod.txt --quiet
  .venv/bin/python -c "import fastapi, uvicorn, numpy, pandas, sklearn, redis; print('  ✓ imports OK')"
}

# ------------------------------------------------------------------ Migrations --
run_migrations() {
  if [ -z "${DATABASE_URL:-}" ]; then
    log "DATABASE_URL absent — migrations ignorées"
    return 0
  fi
  log "Postgres : migrations"
  cd "$REPO_DIR"
  for f in db/migrations/*.sql; do
    [ -e "$f" ] || continue
    log "  -> $f"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f" || log "  ! $f a échoué (ignoré)"
  done
}

# ------------------------------------------------------------------ ETL bookmaker --
run_etl() {
  if [ ! -f "$SITE_DIR/pipelines/etl/ingest_bookmaker_markets.py" ]; then
    log "ETL bookmaker : script absent — ignoré"
    return 0
  fi
  log "ETL bookmaker : contrôle live (dry-run, 2 événements)"
  cd "$SITE_DIR"
  ML_APP_DIR="$SITE_DIR" .venv/bin/python \
    pipelines/etl/ingest_bookmaker_markets.py \
    --provider "${ETL_PROVIDER:-megapari}" --limit 2 --dry-run \
    || log "  ! ETL bookmaker en échec (non bloquant)"
}

# ------------------------------------------------------------------ Flutter Web --
deploy_flutter() {
  if [ ! -d "$REPO_DIR/apps/client-flutter/build/web" ]; then
    log "Flutter Web : build absent (à produire par GitHub Actions) — ignoré"
    return 0
  fi
  log "Flutter Web : copie vers $WEB_DIR"
  mkdir -p "$WEB_DIR"
  rm -rf "${WEB_DIR:?}"/* 2>/dev/null || true
  cp -r "$REPO_DIR/apps/client-flutter/build/web/." "$WEB_DIR/"
}

# ------------------------------------------------------------------ Dispatch --
case "$TARGET" in
  api)        sync_sources; deploy_api ;;
  ml)         sync_sources; deploy_ml ;;
  flutter)    deploy_flutter ;;
  migrations) run_migrations ;;
  etl)        run_etl ;;
  all)
    sync_sources
    deploy_ml
    deploy_api
    run_migrations
    run_etl
    deploy_flutter
    ;;
  *) echo "Usage: bash install.sh [all|api|ml|flutter|migrations|etl]"; exit 1 ;;
esac

log "Étape '$TARGET' terminée"
df -h /home | tail -1
