#!/usr/bin/env bash
#
# setup.sh — Install prerequisites for building Live Scribe desktop app.
#
# Usage:
#   ./desktop/scripts/setup.sh
#
set -euo pipefail

echo "=== Live Scribe Desktop — Setup ==="
echo ""

# Detect platform
OS="$(uname -s)"

check_command() {
    if command -v "$1" &>/dev/null; then
        echo "  [OK] $1 found: $(command -v "$1")"
        return 0
    else
        echo "  [MISSING] $1 not found"
        return 1
    fi
}

MISSING=0

echo "Checking common prerequisites..."
check_command "rustc" || MISSING=1
check_command "cargo" || MISSING=1
check_command "python3" || MISSING=1
check_command "node" || MISSING=1
check_command "npm" || MISSING=1

# Check for Tauri CLI
if cargo tauri --version &>/dev/null 2>&1; then
    echo "  [OK] cargo-tauri found: $(cargo tauri --version 2>/dev/null)"
else
    echo "  [MISSING] cargo-tauri not found"
    echo "           Install with: cargo install tauri-cli"
    MISSING=1
fi

echo ""

case "$OS" in
    Darwin)
        echo "Platform: macOS"
        echo ""
        echo "Checking macOS prerequisites..."

        if xcode-select -p &>/dev/null; then
            echo "  [OK] Xcode Command Line Tools installed"
        else
            echo "  [MISSING] Xcode Command Line Tools"
            echo "           Install with: xcode-select --install"
            MISSING=1
        fi

        echo ""
        echo "macOS tips:"
        echo "  - Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        echo "  - Install Node.js: brew install node"
        echo "  - Install Tauri CLI: cargo install tauri-cli"
        ;;

    Linux)
        echo "Platform: Linux"
        echo ""
        echo "Checking Linux prerequisites..."

        DISTRO=""
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO="$ID"
        fi

        case "$DISTRO" in
            ubuntu|debian|pop)
                echo "  Detected: $DISTRO"
                echo ""
                echo "  Required system packages:"
                echo "    sudo apt update"
                echo "    sudo apt install -y \\"
                echo "      libwebkit2gtk-4.1-dev \\"
                echo "      libappindicator3-dev \\"
                echo "      librsvg2-dev \\"
                echo "      patchelf \\"
                echo "      build-essential \\"
                echo "      curl \\"
                echo "      wget \\"
                echo "      file \\"
                echo "      libssl-dev \\"
                echo "      libayatana-appindicator3-dev"
                echo ""

                # Check for key libraries
                for pkg in libwebkit2gtk-4.1-dev libappindicator3-dev; do
                    if dpkg -l "$pkg" &>/dev/null 2>&1; then
                        echo "  [OK] $pkg installed"
                    else
                        echo "  [MISSING] $pkg"
                        MISSING=1
                    fi
                done
                ;;

            fedora|rhel|centos)
                echo "  Detected: $DISTRO"
                echo ""
                echo "  Required system packages:"
                echo "    sudo dnf install -y \\"
                echo "      webkit2gtk4.1-devel \\"
                echo "      libappindicator-gtk3-devel \\"
                echo "      librsvg2-devel \\"
                echo "      openssl-devel"
                ;;

            arch|manjaro)
                echo "  Detected: $DISTRO"
                echo ""
                echo "  Required system packages:"
                echo "    sudo pacman -S --needed \\"
                echo "      webkit2gtk-4.1 \\"
                echo "      libappindicator-gtk3 \\"
                echo "      librsvg \\"
                echo "      base-devel \\"
                echo "      openssl"
                ;;

            *)
                echo "  Unknown distribution. Please install the following:"
                echo "    - WebKit2GTK 4.1 development libraries"
                echo "    - libappindicator3 development libraries"
                echo "    - librsvg2 development libraries"
                echo "    - OpenSSL development libraries"
                ;;
        esac
        ;;

    *)
        echo "Platform: $OS (unsupported by this script)"
        echo "For Windows, use build-windows.ps1 instead."
        ;;
esac

echo ""

# Check Python backend dependencies
echo "Checking Python backend..."
if python3 -c "import faster_whisper" &>/dev/null 2>&1; then
    echo "  [OK] faster-whisper installed"
else
    echo "  [NOTE] faster-whisper not installed in current Python environment"
    echo "         Install with: pip install -r requirements.txt"
fi

echo ""

if [ "$MISSING" -eq 0 ]; then
    echo "=== All prerequisites found! ==="
    echo ""
    echo "Next steps:"
    echo "  1. Generate icons: cd desktop/tauri && cargo tauri icon icons/icon.png"
    echo "  2. Build the app:  ./desktop/scripts/build-macos.sh  (or build-linux.sh)"
else
    echo "=== Some prerequisites are missing. See above for install instructions. ==="
    exit 1
fi
