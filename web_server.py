"""
Web server for live-scribe: FastAPI + WebSocket + uvicorn.

Wraps the existing AudioTranscriber, TranscriptionBuffer, and LLMDispatcher
classes and exposes them via REST endpoints and a WebSocket for real-time updates.
"""

import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from live_scribe import AudioTranscriber, LLMDispatcher, TranscriptionBuffer

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
_dispatcher: LLMDispatcher | None = None
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
    "llm": "claude-cli",
    "llm_model": None,
    "stream": False,
    "conversation": False,
    "diarize": False,
}

# Connected WebSocket clients
_ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()

# Track dispatch responses
_dispatch_responses: list[dict] = []
_dispatch_id: int = 0

# Event loop reference for thread-safe coroutine scheduling
_event_loop: asyncio.AbstractEventLoop | None = None

# ---------------------------------------------------------------------------
# Pydantic model for /api/start request body
# ---------------------------------------------------------------------------


class StartConfig(BaseModel):
    model: str | None = None
    language: str | None = None
    prompt: str | None = None
    interval: int | None = None
    context: bool | None = None
    context_limit: int | None = None
    llm: str | None = None
    llm_model: str | None = None
    stream: bool | None = None
    conversation: bool | None = None
    diarize: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _broadcast(message: str | dict):
    """Send a JSON message to all connected WebSocket clients.

    Accepts either a pre-serialised JSON string or a dict (which will be
    serialised).
    """
    if isinstance(message, dict):
        data = json.dumps(message)
    else:
        data = message
    dead: list[WebSocket] = []
    async with _ws_lock:
        clients = list(_ws_clients)
    for ws in clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    if dead:
        async with _ws_lock:
            for ws in dead:
                _ws_clients.discard(ws)


async def _broadcast_response(dispatch_id: int, response: dict):
    """Broadcast an LLM dispatch response to all WebSocket clients."""
    msg = json.dumps({
        "type": "llm_response",
        "id": dispatch_id,
        "time": response.get("time", ""),
        "response": response.get("response", ""),
    })
    await _broadcast(msg)


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
    global _last_segment_count, _event_loop
    _event_loop = asyncio.get_running_loop()
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
async def api_start(config: StartConfig | None = None):
    global _transcriber, _dispatcher, _buffer, _recording, _last_segment_count

    if _recording:
        return JSONResponse({"error": "Already recording"}, status_code=409)

    if config:
        config_dict = config.model_dump(exclude_none=True)
        _settings.update({k: v for k, v in config_dict.items() if k in _settings})

    _buffer = TranscriptionBuffer()
    _last_segment_count = 0

    try:
        _transcriber = AudioTranscriber(
            model_size=_settings["model"],
            device="cpu",
            chunk_sec=5,
            diarize=_settings.get("diarize", False),
            language=_settings.get("language"),
        )
        # Share the buffer
        _transcriber.buffer = _buffer
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    _dispatcher = LLMDispatcher(
        buffer=_buffer,
        system_prompt=_settings["prompt"],
        provider_name=_settings.get("llm", "claude-cli"),
        model=_settings.get("llm_model"),
        interval=_settings["interval"],
        context=_settings.get("context", False),
        context_limit=_settings.get("context_limit", 0),
        stream=_settings.get("stream", False),
        conversation=_settings.get("conversation", False),
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

    loop = _event_loop or asyncio.get_running_loop()

    def _run():
        response_text = _dispatcher.dispatch()
        resp = {
            "id": did,
            "time": datetime.now().strftime("%H:%M:%S"),
            "response": response_text or "(No response from LLM)",
        }
        _dispatch_responses.append(resp)
        asyncio.run_coroutine_threadsafe(_broadcast_response(did, resp), loop)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return JSONResponse({"ok": True, "dispatch_id": did})


@app.post("/api/settings")
async def api_settings(request: Request):
    body = await request.json()
    _settings.update({k: v for k, v in body.items() if k in _settings})
    return JSONResponse({"ok": True, "settings": _settings})


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    async with _ws_lock:
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
                cfg_data = msg.get("config")
                cfg = StartConfig(**cfg_data) if cfg_data else None
                await api_start(cfg)
            elif msg_type == "stop":
                await api_stop()

    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            _ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def create_app(**kwargs) -> FastAPI:
    """Create and return the FastAPI app with optional initial settings."""
    if kwargs:
        _settings.update({k: v for k, v in kwargs.items() if k in _settings})
    return app


def start_web_server(host: str = "127.0.0.1", port: int = 8765, **kwargs):
    """Start the uvicorn server (blocking)."""
    import uvicorn

    create_app(**kwargs)
    print(f"\n  Web UI available at http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="live-scribe web server")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Port to listen on (default: 8765)",
    )
    args = parser.parse_args()
    start_web_server(host=args.host, port=args.port)
