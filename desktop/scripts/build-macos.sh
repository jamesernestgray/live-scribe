#!/usr/bin/env bash
#
# build-macos.sh — Build Live Scribe desktop app for macOS.
#
# Usage:
#   ./desktop/scripts/build-macos.sh [--debug]
#
# Output:
#   desktop/tauri/target/release/bundle/dmg/Live Scribe_*.dmg
#   desktop/tauri/target/release/bundle/macos/Live Scribe.app
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

echo "=== Live Scribe Desktop — macOS Build ==="
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

# ── Ensure macOS target ──────────────────────────────────────────────

ARCH="$(uname -m)"
echo "Building for architecture: $ARCH"

if [[ "$ARCH" == "arm64" ]]; then
    TARGET="aarch64-apple-darwin"
else
    TARGET="x86_64-apple-darwin"
fi

# Ensure the target is installed
rustup target add "$TARGET" 2>/dev/null || true
echo ""

# ── Build ────────────────────────────────────────────────────────────

echo "Building Live Scribe desktop app..."
echo ""

cd "$TAURI_DIR"
cargo tauri build $DEBUG_FLAG --target "$TARGET"

echo ""
echo "=== Build Complete ==="
echo ""

BUNDLE_DIR="$TAURI_DIR/target/$TARGET/$BUILD_TYPE/bundle"
if [ -d "$BUNDLE_DIR" ]; then
    echo "Output files:"
    if [ -d "$BUNDLE_DIR/dmg" ]; then
        echo "  DMG: $BUNDLE_DIR/dmg/"
        ls -la "$BUNDLE_DIR/dmg/" 2>/dev/null || true
    fi
    if [ -d "$BUNDLE_DIR/macos" ]; then
        echo "  App: $BUNDLE_DIR/macos/"
        ls -la "$BUNDLE_DIR/macos/" 2>/dev/null || true
    fi
else
    echo "Bundle directory: $TAURI_DIR/target/$TARGET/$BUILD_TYPE/bundle/"
fi
