#!/bin/bash
# Script auxiliaire OpenSSH : retourne le mot de passe depuis l'environnement.
# (Le mot de passe n'est jamais écrit sur disque.)
printf '%s\n' "$ALWAYSDATA_SSH_PASSWORD"
