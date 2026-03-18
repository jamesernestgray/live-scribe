"""
Web server for live-scribe: FastAPI + WebSocket + uvicorn.

Wraps the existing AudioTranscriber, TranscriptionBuffer, and ClaudeDispatcher
classes and exposes them via REST endpoints and a WebSocket for real-time updates.
"""

import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from live_scribe import AudioTranscriber, ClaudeDispatcher, TranscriptionBuffer

# ---------------------------------------------------------------------------
# App globals (populated by start_web_server or create_app)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown lifecycle for the FastAPI app."""
    global _segment_watch_task
    _segment_watch_task = asyncio.create_task(_watch_segments())
    yield
    if _segment_watch_task:
        _segment_watch_task.cancel()
        try:
            await _segment_watch_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="live-scribe Web UI", lifespan=lifespan)

WEB_DIR = Path(__file__).resolve().parent / "web"

# Shared state ----------------------------------------------------------

_transcriber: AudioTranscriber | None = None
_dispatcher: ClaudeDispatcher | None = None
_buffer: TranscriptionBuffer | None = None
_recording: bool = False
_settings: dict = {
    "model": "base",
    "language": None,
    "prompt": (
        "You are a real-time AI collaborator listening to a live audio transcription. "
        "Engage with what's being said: answer questions, provide analysis, "
        "offer relevant expertise, and surface useful context. "
        "If the speaker asks something, answer it directly. "
        "If they're discussing a design or problem, contribute meaningfully. "
        "Be concise and direct."
    ),
    "interval": 60,
    "context": False,
    "context_limit": 0,
    "claude_model": None,
}

# Connected WebSocket clients
_ws_clients: set[WebSocket] = set()
_ws_lock = threading.Lock()

# Track dispatch responses
_dispatch_responses: list[dict] = []
_dispatch_id: int = 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _broadcast(message: dict):
    """Send a JSON message to all connected WebSocket clients."""
    data = json.dumps(message)
    dead: list[WebSocket] = []
    with _ws_lock:
        clients = list(_ws_clients)
    for ws in clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    if dead:
        with _ws_lock:
            for ws in dead:
                _ws_clients.discard(ws)


def _segment_to_dict(seg: dict) -> dict:
    """Convert an internal segment dict to the WebSocket protocol format."""
    return {
        "type": "segment",
        "time": datetime.fromtimestamp(seg["time"]).strftime("%H:%M:%S"),
        "speaker": seg.get("speaker"),
        "text": seg["text"],
    }


def _status_dict() -> dict:
    return {
        "recording": _recording,
        "model": _settings["model"],
        "segments": len(_buffer) if _buffer else 0,
    }


# ---------------------------------------------------------------------------
# Background segment watcher
# ---------------------------------------------------------------------------

_segment_watch_task: asyncio.Task | None = None
_last_segment_count: int = 0


async def _watch_segments():
    """Poll the buffer for new segments and broadcast them."""
    global _last_segment_count
    while True:
        await asyncio.sleep(0.3)
        if _buffer is None:
            continue
        all_segs = _buffer.all()
        if len(all_segs) > _last_segment_count:
            new_segs = all_segs[_last_segment_count:]
            _last_segment_count = len(all_segs)
            for seg in new_segs:
                await _broadcast(_segment_to_dict(seg))
            await _broadcast({"type": "status", **_status_dict()})


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


# Mount static assets *after* defining explicit routes so "/" is not shadowed.
app.mount("/css", StaticFiles(directory=WEB_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=WEB_DIR / "js"), name="js")

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def api_status():
    return JSONResponse(_status_dict())


@app.get("/api/transcript")
async def api_transcript():
    if _buffer is None:
        return JSONResponse({"segments": []})
    segs = _buffer.all()
    return JSONResponse({
        "segments": [
            {
                "time": datetime.fromtimestamp(s["time"]).strftime("%H:%M:%S"),
                "speaker": s.get("speaker"),
                "text": s["text"],
            }
            for s in segs
        ]
    })


@app.post("/api/start")
async def api_start(config: dict | None = None):
    global _transcriber, _dispatcher, _buffer, _recording, _last_segment_count

    if _recording:
        return JSONResponse({"error": "Already recording"}, status_code=409)

    if config:
        _settings.update({k: v for k, v in config.items() if k in _settings})

    _buffer = TranscriptionBuffer()
    _last_segment_count = 0

    try:
        _transcriber = AudioTranscriber(
            model_size=_settings["model"],
            device="cpu",
            chunk_sec=5,
        )
        # Share the buffer
        _transcriber.buffer = _buffer
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    _dispatcher = ClaudeDispatcher(
        buffer=_buffer,
        system_prompt=_settings["prompt"],
        interval=_settings["interval"],
        claude_model=_settings.get("claude_model"),
        context=_settings.get("context", False),
        context_limit=_settings.get("context_limit", 0),
    )

    _transcriber.start()
    _dispatcher.start_timer()
    _recording = True

    await _broadcast({"type": "status", **_status_dict()})
    return JSONResponse({"ok": True})


@app.post("/api/stop")
async def api_stop():
    global _recording
    if not _recording:
        return JSONResponse({"error": "Not recording"}, status_code=409)

    if _dispatcher:
        _dispatcher.stop()
    if _transcriber:
        _transcriber.stop()
    _recording = False

    await _broadcast({"type": "status", **_status_dict()})
    return JSONResponse({"ok": True})


@app.post("/api/dispatch")
async def api_dispatch():
    global _dispatch_id
    if _dispatcher is None or _buffer is None:
        return JSONResponse({"error": "No active session"}, status_code=400)

    _dispatch_id += 1
    did = _dispatch_id

    def _run():
        result = _dispatcher.dispatch()
        if result:
            # Read the last response from claude — we can't easily capture it
            # from the subprocess in the current architecture, so we note dispatch.
            resp = {
                "id": did,
                "time": datetime.now().strftime("%H:%M:%S"),
                "response": "(Dispatch sent to Claude CLI — see terminal for output)",
            }
            _dispatch_responses.append(resp)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return JSONResponse({"ok": True, "dispatch_id": did})


@app.post("/api/settings")
async def api_settings(body: dict):
    _settings.update({k: v for k, v in body.items() if k in _settings})
    return JSONResponse({"ok": True, "settings": _settings})


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with _ws_lock:
        _ws_clients.add(ws)
    try:
        # Send current state on connect
        await ws.send_text(json.dumps({"type": "status", **_status_dict()}))
        # Send existing segments
        if _buffer:
            for seg in _buffer.all():
                await ws.send_text(json.dumps(_segment_to_dict(seg)))

        # Listen for client messages
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "dispatch":
                # Trigger dispatch in background
                await api_dispatch()
            elif msg_type == "start":
                cfg = msg.get("config")
                await api_start(cfg)
            elif msg_type == "stop":
                await api_stop()

    except WebSocketDisconnect:
        pass
    finally:
        with _ws_lock:
            _ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def create_app(**kwargs) -> FastAPI:
    """Create and return the FastAPI app with optional initial settings."""
    if kwargs:
        _settings.update({k: v for k, v in kwargs.items() if k in _settings})
    return app


def start_web_server(port: int = 8765, **kwargs):
    """Start the uvicorn server (blocking)."""
    import uvicorn

    create_app(**kwargs)
    print(f"\n  Web UI available at http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
