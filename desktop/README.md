# Live Scribe Desktop App

Native desktop application wrapper for Live Scribe, built with [Tauri 2.0](https://v2.tauri.app/).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Tauri 2.0 Shell                       │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Native Window (WebView)              │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │              Web UI (HTML/JS)               │  │  │
│  │  │         (from web-ui feature branch)        │  │  │
│  │  │                                             │  │  │
│  │  │   ┌──────────┐  ┌──────────┐  ┌─────────┐  │  │  │
│  │  │   │ Controls │  │Transcript│  │ Claude  │  │  │  │
│  │  │   │  Panel   │  │  View    │  │Response │  │  │  │
│  │  │   └──────────┘  └──────────┘  └─────────┘  │  │  │
│  │  └──────────────────────┬──────────────────────┘  │  │
│  └─────────────────────────┼─────────────────────────┘  │
│                            │ HTTP / WebSocket            │
│  ┌─────────────────────────┼─────────────────────────┐  │
│  │     System Tray    Global Shortcuts   Window Mgmt │  │
│  └─────────────────────────┼─────────────────────────┘  │
└────────────────────────────┼────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Python Backend  │
                    │  (web_server.py) │
                    │  localhost:8765   │
                    ├──────────────────┤
                    │  live_scribe.py  │
                    │  (core engine)   │
                    └──────────────────┘
```

The desktop app works as follows:

1. **Tauri** launches and starts the Python backend (`web_server.py`) as a child process
2. The **WebView** window loads the web UI served by the Python backend on `http://localhost:8765`
3. The web UI communicates with the Python backend via HTTP and WebSocket
4. **System tray** and **global shortcuts** provide native OS integration
5. On quit, Tauri cleans up the Python process

## Prerequisites

### All Platforms

- **Rust** (1.70+) — [Install](https://rustup.rs)
- **Tauri CLI** — `cargo install tauri-cli`
- **Python 3.11+** — with `pip install -r requirements.txt`
- **Node.js 18+** (for Tauri build tooling)

### macOS

- **Xcode Command Line Tools** — `xcode-select --install`
- macOS 10.15 (Catalina) or later
- No additional system libraries needed (WebView is built into macOS)

### Linux

System libraries required (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y \
  libwebkit2gtk-4.1-dev \
  libappindicator3-dev \
  librsvg2-dev \
  patchelf \
  build-essential \
  curl \
  wget \
  file \
  libssl-dev \
  libayatana-appindicator3-dev
```

Fedora/RHEL:

```bash
sudo dnf install -y \
  webkit2gtk4.1-devel \
  libappindicator-gtk3-devel \
  librsvg2-devel \
  openssl-devel
```

Arch/Manjaro:

```bash
sudo pacman -S --needed \
  webkit2gtk-4.1 \
  libappindicator-gtk3 \
  librsvg \
  base-devel \
  openssl
```

### Windows

- **Visual Studio Build Tools** with "Desktop development with C++" workload
- **WebView2 Runtime** (bundled with Windows 10 1803+ and Windows 11)
  - [Manual download](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) for older systems

## Setup

1. **Check prerequisites:**

   ```bash
   ./desktop/scripts/setup.sh
   ```

2. **Generate icons** (requires a 1024x1024 PNG source):

   ```bash
   cd desktop/tauri
   cargo tauri icon path/to/your-icon.png
   ```

   See `desktop/tauri/icons/README.md` for details.

## Python Backend Bundling

The desktop app needs the Python backend files to be available at runtime.
The `tauri.conf.json` is configured to bundle `live_scribe.py` and
`requirements.txt` as resources.

For a fully self-contained distribution, you have two options:

### Option A: Require system Python

Users install Python and dependencies separately. The app finds `python3`
on the system PATH.

### Option B: Bundle Python with PyInstaller

```bash
# Create a standalone Python executable
pip install pyinstaller
pyinstaller --onefile web_server.py

# Copy the executable to desktop/tauri/binaries/
mkdir -p desktop/tauri/binaries
cp dist/web_server desktop/tauri/binaries/web_server-$(uname -m)
```

Then update `tauri.conf.json` to use an external binary sidecar instead
of spawning `python3`.

## Build

### macOS

```bash
./desktop/scripts/build-macos.sh
```

Output:
- `desktop/tauri/target/<arch>-apple-darwin/release/bundle/dmg/` — DMG installer
- `desktop/tauri/target/<arch>-apple-darwin/release/bundle/macos/` — .app bundle

### Linux

```bash
./desktop/scripts/build-linux.sh
```

Output:
- `desktop/tauri/target/release/bundle/deb/` — Debian package
- `desktop/tauri/target/release/bundle/appimage/` — AppImage

### Windows

```powershell
.\desktop\scripts\build-windows.ps1
```

Output:
- `desktop\tauri\target\release\bundle\msi\` — MSI installer
- `desktop\tauri\target\release\bundle\nsis\` — NSIS installer (EXE)

### Debug Builds

All build scripts accept a `--debug` flag (or `-Debug` on Windows) for
faster builds without optimizations:

```bash
./desktop/scripts/build-macos.sh --debug
```

## Features

### System Tray

Right-click the tray icon for:
- **Start Recording** — begin audio capture
- **Stop Recording** — stop audio capture
- **Dispatch to Claude** — send current transcript for analysis
- **Quit** — close the app and clean up

### Global Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+Shift+D (macOS) / Ctrl+Shift+D | Dispatch transcript to Claude |

### Tauri Commands

The Rust backend exposes these commands to the web frontend:

| Command | Description |
|---------|-------------|
| `start_recording` | Start audio capture |
| `stop_recording` | Stop audio capture |
| `dispatch` | Send transcript to Claude |
| `get_status` | Get recording and backend status |

## Troubleshooting

### "Could not find web_server.py"

The app looks for `web_server.py` in several locations:
1. Current working directory
2. Two directories up from `desktop/tauri/`
3. Next to the executable (bundled builds)
4. Inside the macOS `.app` Resources directory

Ensure the web server script is in one of these locations, or that the
web-ui feature branch has been merged.

### WebView shows "Connecting to backend..."

The Python backend hasn't started yet or isn't reachable. Check:
1. Python 3 is on your PATH
2. `requirements.txt` dependencies are installed
3. Port 8765 is not in use by another process
4. Check the terminal/console for Python error messages

### Linux: "libwebkit2gtk-4.1 not found"

Install the development package:
```bash
# Ubuntu/Debian
sudo apt install libwebkit2gtk-4.1-dev

# Fedora
sudo dnf install webkit2gtk4.1-devel

# Arch
sudo pacman -S webkit2gtk-4.1
```

### macOS: "App can't be opened because it is from an unidentified developer"

The app needs to be code-signed for distribution. For local testing:
```bash
# Remove the quarantine flag
xattr -cr "/Applications/Live Scribe.app"
```

### Windows: WebView2 errors

Ensure WebView2 Runtime is installed:
- Windows 10 (1803+) and Windows 11 include it by default
- Download manually from [Microsoft](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

### Build fails with "tauri-cli not found"

```bash
cargo install tauri-cli
```

### Port 8765 already in use

Kill the existing process:
```bash
# macOS/Linux
lsof -ti:8765 | xargs kill -9

# Windows
netstat -ano | findstr :8765
taskkill /PID <pid> /F
```

## Development

### Project Structure

```
desktop/
├── README.md               # This file
├── tauri/
│   ├── Cargo.toml           # Rust dependencies
│   ├── Cargo.lock           # Dependency lock file
│   ├── tauri.conf.json      # Tauri app configuration
│   ├── build.rs             # Tauri build script
│   ├── capabilities/
│   │   └── default.json     # Security permissions
│   ├── src/
│   │   ├── main.rs          # App entry point, tray, shortcuts
│   │   └── lib.rs           # Commands, backend management
│   └── icons/
│       └── README.md        # Icon generation instructions
├── src/
│   └── index.html           # Frontend placeholder
├── scripts/
│   ├── setup.sh             # Install prerequisites
│   ├── build-macos.sh       # macOS build script
│   ├── build-linux.sh       # Linux build script
│   └── build-windows.ps1    # Windows build script
└── tests/
    └── test_config.py       # Configuration validation tests
```
