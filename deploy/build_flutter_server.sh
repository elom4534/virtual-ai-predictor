#!/bin/bash
# ============================================================================
#  Build Flutter Web (web) — exécuté SUR LE SERVEUR Alwaysdata (compte `god`).
#
#  Pourquoi sur le serveur ? Le SDK Flutter (~1,5 Go) + la compilation Dart
#  demandent ~2 Go de RAM : l'environnement de build local n'a pas la place.
#  Le build produit est ensuite copié dans /home/god/www/web (servi par l'edge).
#
#  Usage : bash build_flutter_server.sh [version_stable]
#  Exemple : bash build_flutter_server.sh 3.47.7
# ============================================================================
set -euo pipefail

ACCOUNT="${ACCOUNT:-god}"
HOME_DIR="${HOME_DIR:-/home/$ACCOUNT}"
CACHE_DIR="${CACHE_DIR:-$HOME_DIR/.cache}"
FLUTTER_VERSION="${1:-3.24.0}"
SDK_DIR="$CACHE_DIR/flutter-$FLUTTER_VERSION"   # un SDK par version (pas de collision)
BUILD_DIR="$CACHE_DIR/client-build"
WEB_DIR="${WEB_DIR:-$HOME_DIR/www/web}"
REPO_DIR="${REPO_DIR:-$HOME_DIR/pred-app}"

log() { echo "[flutter $(date -u +%H:%M:%S)] $*"; }

mkdir -p "$CACHE_DIR" "$BUILD_DIR"

# ------------------------------------------------------------------ SDK -----
if [ ! -x "$SDK_DIR/bin/flutter" ]; then
  log "Téléchargement du SDK Flutter $FLUTTER_VERSION (~1,5 Go)"
  cd "$CACHE_DIR"
  URL="https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz"
  curl -fL --retry 3 -o flutter.tar.xz "$URL"
  rm -rf "$SDK_DIR"
  mkdir -p "$SDK_DIR"
  tar xf flutter.tar.xz -C "$SDK_DIR" --strip-components=1
  rm -f flutter.tar.xz
fi
export PATH="$SDK_DIR/bin:$PATH"
export PUB_CACHE="$CACHE_DIR/pub"
git config --global --add safe.directory "$SDK_DIR" || true
git config --global --add safe.directory "$HOME_DIR" || true
flutter config --no-analytics >/dev/null 2>&1 || true
log "flutter : $(flutter --version 2>&1 | head -1)"

# --------------------------------------------------------------- sources ----
log "Copie des sources client"
rm -rf "${BUILD_DIR:?}"/*
cp -r "$REPO_DIR/apps/client-flutter/." "$BUILD_DIR/"
cd "$BUILD_DIR"

# Le dépôt ne contient pas les dossiers de plateforme : on les regénère
# (comme le fait le workflow GitHub Actions : `flutter create .`).
if [ ! -d web ]; then
  log "Génération du dossier web (flutter create --no-pub)"
  # pubspec.yaml est sauvegardé : `flutter create` peut le retoucher.
  cp -f pubspec.yaml pubspec.yaml.bak
  flutter create --platforms=web --no-pub --project-name pred_client .
  mv -f pubspec.yaml.bak pubspec.yaml
fi

log "flutter pub get"
flutter pub get

log "flutter build web --release"
flutter build web --release

if [ ! -f build/web/index.html ]; then
  log "✗ build absent (build/web/index.html introuvable)"
  exit 1
fi

log "Publication vers $WEB_DIR"
mkdir -p "$WEB_DIR"
rm -rf "${WEB_DIR:?}"/* 2>/dev/null || true
cp -r "$BUILD_DIR/build/web/." "$WEB_DIR/"

log "✓ build Flutter web publié ($(du -sh "$WEB_DIR" | cut -f1))"
