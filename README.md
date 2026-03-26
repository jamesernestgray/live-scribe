# live-scribe

Real-time audio transcription with periodic LLM analysis.

Captures microphone audio, transcribes it locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper), and sends the transcript to an LLM for analysis — either automatically on a timer or manually. Optionally identifies distinct speakers via [pyannote](https://github.com/pyannote/pyannote-audio) diarization.

Three ways to use it:

| Interface | Launch | Best for |
|-----------|--------|----------|
| **CLI** | `python live_scribe.py` | Headless / scripting |
| **Web UI** | `python web_server.py` then open `http://localhost:8765` | Browser-based with full settings panel |
| **Desktop App** | Build from `desktop/` with Tauri | Native app with system tray and global shortcuts |

## Prerequisites

- **Python 3.11+**
- **Claude Code CLI** (`claude`) installed and authenticated — [install guide](https://docs.anthropic.com/en/docs/claude-code/getting-started) *(required only for the default Claude CLI provider)*
- **Microphone access** (macOS will prompt for permission on first run)
- **HF_TOKEN** environment variable *(only if using `--diarize`)* — see [Speaker Diarization](#speaker-diarization)
- **Rust 1.70+ and Node.js 18+** *(only if building the [Desktop App](#desktop-app-tauri))*

## Setup

```bash
cd ~/projects/live-scribe
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: install diarization support
pip install pyannote.audio torch
```

## Quick Start

```bash
source .venv/bin/activate

# Default: auto-dispatch every 60s, new segments only
python live_scribe.py

# Recommended: manual dispatch with full conversation context
python live_scribe.py --manual --context

# With speaker identification
python live_scribe.py --manual --context --diarize
```

Press **Ctrl+C** to stop. The full session transcript is printed on exit.

## Web UI

The web UI provides a browser-based interface with real-time transcript display, settings panel, and LLM response streaming.

```bash
source .venv/bin/activate
python web_server.py          # → http://localhost:8765
```

### Features

| Feature | Description |
|---------|-------------|
| **LLM response streaming** | Enable "Stream Responses" in settings to see output appear token-by-token |
| **Prompt presets** | Dropdown to switch between built-in presets (meeting notes, code review, lecture, interview, etc.) |
| **Export formats** | Save transcript as TXT, Markdown, JSON, or SRT |
| **Audio device selection** | Choose input microphone and compute device (CPU/CUDA/auto) |
| **Speaker diarization** | Toggle on/off in settings |
| **Context mode** | Send full transcript history with dispatches |
| **Conversation mode** | Maintain multi-turn LLM history across dispatches |
| **LLM provider selection** | Choose between Claude CLI, Anthropic API, OpenAI, Codex CLI, Gemini, Gemini CLI, Ollama, or LiteLLM |

### Web Server Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Recording and backend status |
| `GET` | `/api/transcript` | Current transcript segments |
| `GET` | `/api/transcript/export?format=` | Export transcript (`txt`, `md`, `json`, `srt`) |
| `GET` | `/api/devices` | List audio input devices |
| `GET` | `/api/presets` | List prompt presets |
| `POST` | `/api/start` | Start recording (accepts config JSON) |
| `POST` | `/api/stop` | Stop recording |
| `POST` | `/api/dispatch` | Send transcript to LLM |
| `POST` | `/api/settings` | Update runtime settings |
| `WS` | `/ws` | Real-time transcript and LLM response updates |

## Desktop App (Tauri)

A native desktop wrapper built with [Tauri 2.0](https://v2.tauri.app/). The app auto-starts the Python backend, loads the web UI in a native window, and adds OS-level integrations.

### Quick Start

```bash
# Prerequisites: Rust 1.70+, Node.js 18+, Python 3.11+
cargo install tauri-cli

# Build
./desktop/scripts/build-macos.sh      # macOS — produces .app and .dmg
./desktop/scripts/build-linux.sh       # Linux — produces .deb and AppImage
.\desktop\scripts\build-windows.ps1    # Windows — produces .msi and .exe
```

### System Tray

Right-click the tray icon for:
- **Toggle Recording** — start/stop audio capture
- **Dispatch to Claude** — send current transcript for analysis
- **Save Transcript** — export the session
- **Quit** — close the app and clean up the backend

### Global Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+Shift+R` (macOS) / `Ctrl+Shift+R` | Toggle recording |
| `Cmd+Shift+D` (macOS) / `Ctrl+Shift+D` | Dispatch transcript to LLM |

### How It Works

1. Tauri launches and starts `web_server.py` via the project's Python venv
2. The native WebView loads the web UI from `http://localhost:8765`
3. System tray and global shortcuts provide native OS integration
4. On quit, Tauri cleans up the Python process

See [`desktop/README.md`](desktop/README.md) for build options, bundling, troubleshooting, and platform-specific prerequisites.

## Usage

```
python live_scribe.py [OPTIONS]
```

### Dispatch Modes

| Flag | Behavior |
|------|----------|
| *(default)* | Automatically sends transcript to Claude every `--interval` seconds |
| `--manual` | Waits for you to press **Enter** to send transcript to Claude |

### Context Modes

| Flag | Behavior |
|------|----------|
| *(default)* | Only sends new (unsent) segments each dispatch |
| `--context` | Sends full transcript history each dispatch, with new segments marked separately |
| `--context --context-limit N` | Sends the last *N* prior segments as context plus new segments |

With `--context`, Claude receives a prompt structured like:

```
--- PRIOR CONTEXT ---
[11:46:46] Earlier part of the conversation...
[11:46:52] More earlier discussion...

--- NEW TRANSCRIPT ---
[11:47:03] The latest things said...
--- END ---
```

With `--diarize --context`, speaker labels are included:

```
--- PRIOR CONTEXT ---
[11:46:46] [SPEAKER_00] Earlier part of the conversation...
[11:46:52] [SPEAKER_01] A different person responding...

--- NEW TRANSCRIPT ---
[11:47:03] [SPEAKER_00] The latest things said...
--- END ---
```

## Parameters

### Whisper (transcription)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--model`, `-m` | `base` | Whisper model size. Choices: `tiny`, `base`, `small`, `medium`, `large-v3`. Larger = more accurate but slower. |
| `--chunk` | `5` | Seconds of audio to buffer before each transcription pass. |
| `--compute` | `cpu` | Compute device. Choices: `cpu`, `cuda`, `auto`. |
| `--input-device` | *(system default)* | Audio input device index. Use `--list-devices` to see options. |
| `--list-devices` | | Print available audio devices and exit. |

### Speaker Diarization

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--diarize` | off | Enable speaker diarization via pyannote. Requires `HF_TOKEN` env var and `pyannote.audio` installed. Automatically raises chunk size to 30s. |

**Setup for diarization:**

1. Install dependencies: `pip install pyannote.audio torch`
2. Accept the model terms at [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) on Hugging Face
3. Set your token: `export HF_TOKEN="hf_your_token_here"`
4. First run downloads the model (~100MB)

**Tradeoff:** Diarization needs ~30s of audio to reliably distinguish voices, so transcript output is delayed by 30s compared to the default 5s. Each chunk also takes longer to process (diarization + transcription).

### Claude (LLM dispatch)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--interval`, `-i` | `60` | Seconds between automatic Claude dispatches. Ignored with `--manual`. |
| `--manual` | off | Manual mode — press Enter to dispatch instead of using a timer. |
| `--prompt` | *(see below)* | System prompt sent to Claude with each transcript batch. |
| `--context` | off | Include full prior transcript history with each dispatch. |
| `--context-limit` | `0` | Max number of prior segments to include as context. `0` = unlimited. |
| `--claude-model` | *(CLI default)* | Model override passed to `claude` CLI (e.g. `sonnet`, `opus`, `haiku`). |

### Output

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--save` | *(none)* | File path to save the full transcript on exit. |

### Default Prompt

When no `--prompt` is provided, Claude acts as an active collaborator:

> You are a real-time AI collaborator listening to a live audio transcription. Engage with what's being said: answer questions, provide analysis, offer relevant expertise, and surface useful context. If the speaker asks something, answer it directly. If they're discussing a design or problem, contribute meaningfully. Be concise and direct.

Override with `--prompt` for different behaviors:

```bash
# Passive meeting notes
python live_scribe.py --manual --context \
  --prompt "Summarize the discussion. List action items and decisions."

# Technical review
python live_scribe.py --manual --context \
  --prompt "You are a senior architect. Critique the technical ideas being discussed. Flag risks and suggest alternatives."

# Language practice
python live_scribe.py --manual \
  --prompt "I'm practicing Spanish. Correct any grammar mistakes in what I said and suggest more natural phrasing."
```

## Examples

```bash
# Defaults: base model, auto every 60s, new segments only
python live_scribe.py

# Manual dispatch with full conversation history
python live_scribe.py --manual --context

# With speaker diarization
python live_scribe.py --manual --context --diarize

# Better accuracy, auto every 30s, save transcript
python live_scribe.py --model small -i 30 --save meeting.txt

# Rolling window of last 20 segments for context
python live_scribe.py --context --context-limit 20

# Use a specific mic and Claude model
python live_scribe.py --input-device 2 --claude-model opus

# List available microphones
python live_scribe.py --list-devices
```

## Runtime Controls

| Key | Action |
|-----|--------|
| **Enter** | Send transcript to Claude *(manual mode only)* |
| **Ctrl+C** | Stop recording, print full transcript, and exit |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Desktop App (Tauri, optional)                   │
│  System Tray · Global Shortcuts · Auto-start Backend            │
└────────────────────────────┬────────────────────────────────────┘
                             │ loads
┌────────────────────────────▼────────────────────────────────────┐
│                    Web UI  (localhost:8765)                      │
│  Settings Panel · Transcript View · LLM Response Streaming      │
└────────────────────────────┬────────────────────────────────────┘
                   HTTP / WebSocket │
┌──────────────────────────────────▼──────────────────────────────┐
│                    web_server.py  (FastAPI)                      │
│  REST API · WebSocket · Export · Preset Management              │
└────────────────────────────┬────────────────────────────────────┘
                             │ uses
┌────────────────────────────▼────────────────────────────────────┐
│                  live_scribe.py  (core engine)                   │
│                                                                  │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │  Microphone  │─▶│  AudioTranscriber │─▶│ TranscriptionBuf │   │
│  │  (sounddev)  │  │  (faster-whisper) │  │  (thread-safe)   │   │
│  └─────────────┘  └────────┬─────────┘  └────────┬─────────┘   │
│                    ┌───────▼────────┐             │              │
│                    │ SpeakerDiarizer│             │              │
│                    │(pyannote, opt.)│             │              │
│                    └────────────────┘             ▼              │
│                              ┌─────────────────────┐            │
│                              │    LLMDispatcher     │            │
│                              │  (timer / manual)    │            │
│                              └──────────┬──────────┘            │
└─────────────────────────────────────────┼───────────────────────┘
                                          ▼
                              ┌──────────────────────┐
                              │    LLM Provider       │
                              │  Claude CLI · OpenAI  │
                              │  Anthropic · Gemini   │
                              │  Ollama · LiteLLM     │
                              └──────────────────────┘
```

- **Audio thread**: `sounddevice` callback captures raw PCM into a buffer
- **Transcription thread**: Every `--chunk` seconds, drains the audio buffer, runs Whisper with VAD filtering, and optionally runs pyannote diarization to label speakers
- **Dispatch**: Timer thread (auto mode) or main thread on Enter (manual mode) sends accumulated text to the configured LLM provider
- **Web server**: FastAPI app exposes REST/WebSocket endpoints and serves the browser UI
- **Desktop shell**: Tauri wraps the web UI in a native window with system tray and keyboard shortcuts
- All shared state is protected by threading locks

## Model Sizing Guide

| Model | Size | Relative Speed | Best For |
|-------|------|---------------|----------|
| `tiny` | 39M | Fastest | Quick testing, clear audio |
| `base` | 74M | Fast | General use (default) |
| `small` | 244M | Moderate | Better accuracy |
| `medium` | 769M | Slow | High accuracy |
| `large-v3` | 1.5G | Slowest | Maximum accuracy |

First run will download the selected model from Hugging Face (~30s for `base`).
