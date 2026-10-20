#!/bin/bash
# ============================================================================
#  Déploiement "pred-app" sur Alwaysdata — WRAPPER LOCAL.
#  Compte : elogededivo05417042
#
#  Usage :
#    bash deploy.sh preflight   # vérifie config, secrets, API, SSH, disque
#    bash deploy.sh all          # push + install + sites + restart
#    bash deploy.sh api|ml|flutter|migrations|etl
#    bash deploy.sh status       # sites + logs
#
#  Secrets : ALWAYSDATA_API_TOKEN (obligatoire),
#            ALWAYSDATA_SSH_PASSWORD ou ALWAYSDATA_SSH_KEY (au moins un).
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$HERE/alwaysdata.py"
TARGET="${1:-all}"

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

run_kit() { python3 "$KIT" "$@"; }

case "$TARGET" in
  preflight)
    run_kit preflight
    ;;
  check)
    run_kit check
    ;;
  status)
    run_kit status
    ;;
  push)
    run_kit push
    ;;
  site)
    run_kit site
    ;;
  restart)
    run_kit restart
    ;;
  api|ml|flutter|migrations|etl)
    log "Déploiement ciblé : $TARGET"
    run_kit push
    log "Installation serveur : $TARGET"
    python3 - <<PY
import json, subprocess, sys
from pathlib import Path
cfg = json.loads(Path("$HERE/config.json").read_text())
ssh = cfg.get("ssh", {})
cmd = ["ssh"]
if ssh.get("key_path"):
    cmd += ["-i", ssh["key_path"]]
cmd += ["-o", "StrictHostKeyChecking=accept-new",
        f'{ssh.get("user") or cfg["account"]}@{ssh.get("host")}',
        f'bash {cfg["remote_dir"]}/deploy/install.sh {sys.argv[1]}']
if ssh.get("password") and not ssh.get("key_path"):
    cmd = ["sshpass", "-p", ssh["password"]] + cmd
sys.exit(subprocess.run(cmd).returncode)
PY
    run_kit restart
    ;;
  all)
    log "Déploiement complet"
    run_kit push
    log "Installation serveur"
    python3 - <<PY
import json, subprocess, sys
from pathlib import Path
cfg = json.loads(Path("$HERE/config.json").read_text())
ssh = cfg.get("ssh", {})
cmd = ["ssh"]
if ssh.get("key_path"):
    cmd += ["-i", ssh["key_path"]]
cmd += ["-o", "StrictHostKeyChecking=accept-new",
        f'{ssh.get("user") or cfg["account"]}@{ssh.get("host")}',
        f'bash {cfg["remote_dir"]}/deploy/install.sh all']
if ssh.get("password") and not ssh.get("key_path"):
    cmd = ["sshpass", "-p", ssh["password"]] + cmd
sys.exit(subprocess.run(cmd).returncode)
PY
    run_kit site
    run_kit restart
    log "Déploiement terminé"
    ;;
  *)
    echo "Usage: bash deploy.sh [all|api|ml|flutter|migrations|etl|preflight|check|status|push|site|restart]"
    exit 1
    ;;
esac
