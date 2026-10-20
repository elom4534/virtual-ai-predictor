#!/bin/bash
# ============================================================================
#  Exécution d'une commande sur Alwaysdata (compte `god`) en SSH.
#  Utilise le mot de passe via SSH_ASKPASS (sshpass n'est pas installé ici).
#
#  Usage : bash ssh.sh "ls -la /home/god"
#          bash ssh.sh 'bash /home/god/pred-app/deploy/install.sh all'
# ============================================================================
set -euo pipefail

SECRETS="${SECRETS:-/home/user/deploy/secrets.env}"
set -a
# shellcheck disable=SC1090
. "$SECRETS"
set +a

ASKPASS="$(dirname "${BASH_SOURCE[0]}")/askpass.sh"

exec env DISPLAY=:0 \
    SSH_ASKPASS="$ASKPASS" \
    SSH_ASKPASS_REQUIRE=force \
    setsid -w ssh \
      -o StrictHostKeyChecking=accept-new \
      -o PreferredAuthentications=password \
      -o PubkeyAuthentication=no \
      -o NumberOfPasswordPrompts=1 \
      "${ALWAYSDATA_SSH_USER:-god}@${ALWAYSDATA_SSH_HOST:-ssh-god.alwaysdata.net}" \
      "$@"
