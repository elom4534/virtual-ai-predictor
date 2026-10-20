#!/bin/bash
# ============================================================================
#  Démarrage du service NestJS (API interne) sur Alwaysdata.
#  L'edge FastAPI le relance automatiquement s'il ne répond pas (app/edge.py).
# ============================================================================
set -u

APP_DIR="${APP_DIR:-/home/god/pred-app/apps/api-node}"
LOG_DIR="${LOG_DIR:-/home/god/admin/tmp}"
mkdir -p "$LOG_DIR"

cd "$APP_DIR" || exit 1

# Les secrets applicatifs (JWT, bookmaker, Live Football…)
if [ -f /home/god/.config/pred-app.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /home/god/.config/pred-app.env
  set +a
fi

export NODE_ENV="${NODE_ENV:-production}"

# ⚠️ La plateforme injecte PORT=8100 et IP=fd00::7:c7ec dans l'environnement.
#    On les capture AVANT de les neutraliser.
PLATFORM_IP="${IP:-}"
PLATFORM_PORT="${PORT:-8100}"

# L'edge FastAPI n'écoute QUE sur l'IPv6 de la plateforme (--host $IP) :
# NestJS ne peut donc pas l'atteindre via 127.0.0.1:8100 (« ml: down »).
# → URL IPv6 entre crochets, construite dynamiquement depuis IP.
if [ -n "$PLATFORM_IP" ]; then
  export ML_PYTHON_URL="http://[${PLATFORM_IP}]:${PLATFORM_PORT}"
else
  export ML_PYTHON_URL="http://127.0.0.1:${PLATFORM_PORT}"
fi

# Le service Node est INTERNE : on force 127.0.0.1:3000 (variables dédiées),
# sinon NestJS tente de prendre le port public de l'edge
# → « [Errno 98] address already in use » → le site ne démarre plus.
export NODE_API_PORT="3000"
export NODE_API_HOST="127.0.0.1"
unset IP
export HOST="127.0.0.1"
export PORT="3000"

if [ ! -f dist/main.js ]; then
  echo "[launch_node] dist/main.js absent — build manquant" >&2
  exit 1
fi

exec node dist/main.js
