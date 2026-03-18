#!/usr/bin/env bash
#
# build-linux.sh — Build Live Scribe desktop app for Linux.
#
# Usage:
#   ./desktop/scripts/build-linux.sh [--debug]
#
# Output:
#   desktop/tauri/target/release/bundle/deb/live-scribe_*.deb
#   desktop/tauri/target/release/bundle/appimage/live-scribe_*.AppImage
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TAURI_DIR="$PROJECT_ROOT/desktop/tauri"

DEBUG_FLAG=""
BUILD_TYPE="release"
if [[ "${1:-}" == "--debug" ]]; then
    DEBUG_FLAG="--debug"
    BUILD_TYPE="debug"
fi

echo "=== Live Scribe Desktop — Linux Build ==="
echo ""
echo "  Project root: $PROJECT_ROOT"
echo "  Tauri dir:    $TAURI_DIR"
echo "  Build type:   $BUILD_TYPE"
echo ""

# ── Prerequisites ────────────────────────────────────────────────────

echo "Checking prerequisites..."

if ! command -v rustc &>/dev/null; then
    echo "ERROR: Rust not found. Install from https://rustup.rs"
    exit 1
fi
echo "  Rust: $(rustc --version)"

if ! command -v cargo &>/dev/null; then
    echo "ERROR: Cargo not found."
    exit 1
fi

if ! cargo tauri --version &>/dev/null 2>&1; then
    echo "ERROR: cargo-tauri not found. Install with: cargo install tauri-cli"
    exit 1
fi
echo "  Tauri CLI: $(cargo tauri --version 2>/dev/null)"

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    exit 1
fi
echo "  Python: $(python3 --version)"

echo ""

# ── Check Linux dependencies ────────────────────────────────────────

echo "Checking system libraries..."

MISSING_DEPS=0

check_pkg() {
    if dpkg -l "$1" &>/dev/null 2>&1; then
        echo "  [OK] $1"
    elif rpm -q "$1" &>/dev/null 2>&1; then
        echo "  [OK] $1"
    elif pacman -Qi "$1" &>/dev/null 2>&1; then
        echo "  [OK] $1"
    else
        echo "  [MISSING] $1"
        MISSING_DEPS=1
    fi
}

# These are the Debian/Ubuntu package names; other distros will
# have different names but the check will gracefully skip.
check_pkg "libwebkit2gtk-4.1-dev" 2>/dev/null || true
check_pkg "libappindicator3-dev" 2>/dev/null || true

if [ "$MISSING_DEPS" -eq 1 ]; then
    echo ""
    echo "WARNING: Some system libraries may be missing."
    echo "On Ubuntu/Debian, install with:"
    echo "  sudo apt install -y libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf"
    echo ""
    echo "Continuing anyway (the build will fail if libraries are truly missing)..."
fi

echo ""

# ── Build ────────────────────────────────────────────────────────────

echo "Building Live Scribe desktop app..."
echo ""

cd "$TAURI_DIR"
cargo tauri build $DEBUG_FLAG

echo ""
echo "=== Build Complete ==="
echo ""

BUNDLE_DIR="$TAURI_DIR/target/release/bundle"
if [ -d "$BUNDLE_DIR" ]; then
    echo "Output files:"
    if [ -d "$BUNDLE_DIR/deb" ]; then
        echo "  DEB: $BUNDLE_DIR/deb/"
        ls -la "$BUNDLE_DIR/deb/" 2>/dev/null || true
    fi
    if [ -d "$BUNDLE_DIR/appimage" ]; then
        echo "  AppImage: $BUNDLE_DIR/appimage/"
        ls -la "$BUNDLE_DIR/appimage/" 2>/dev/null || true
    fi
else
    echo "Bundle directory: $BUNDLE_DIR/"
fi
