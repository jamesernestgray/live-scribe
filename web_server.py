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

import sounddevice as sd
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from live_scribe import (
    AudioTranscriber,
    DEFAULT_PRESET,
    LLMDispatcher,
    TranscriptionBuffer,
    get_all_presets,
    save_transcript,
)

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
    "input_device": None,
    "compute": "cpu",
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
    input_device: int | None = None
    compute: str | None = None


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


@app.get("/api/transcript/export")
async def api_transcript_export(format: str = Query("txt", pattern="^(txt|md|json|srt)$")):
    """Export transcript in the specified format as a file download."""
    import tempfile

    segments = _buffer.all() if _buffer else []

    # Content-type and file extension mapping
    content_types = {
        "txt": "text/plain",
        "md": "text/markdown",
        "json": "application/json",
        "srt": "text/srt",
    }

    # Write to a temporary file using the existing save_transcript logic
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"transcript-{timestamp}.{format}"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f".{format}", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        save_transcript(
            segments, tmp_path, fmt=format,
            dispatches=_dispatch_responses or None,
            model=_settings.get("model", "base"),
            language=_settings.get("language"),
            provider=_settings.get("llm", "claude-cli"),
        )
        content = tmp_path.read_text(encoding="utf-8")
    finally:
        tmp_path.unlink(missing_ok=True)

    return Response(
        content=content,
        media_type=content_types.get(format, "text/plain"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.get("/api/devices")
async def api_devices():
    """List available audio input devices."""
    devices = sd.query_devices()
    input_devices = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            input_devices.append({
                "index": i,
                "name": dev["name"],
                "channels": dev["max_input_channels"],
                "default": i == sd.default.device[0],
            })
    return JSONResponse({"devices": input_devices})


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

    # Set audio input device if specified
    input_device = _settings.get("input_device")
    if input_device is not None:
        sd.default.device[0] = input_device

    compute = _settings.get("compute", "cpu")

    try:
        _transcriber = AudioTranscriber(
            model_size=_settings["model"],
            device=compute,
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
        if _settings.get("stream"):
            _run_streaming(did, loop)
        else:
            result = _dispatcher.dispatch()
            if result:
                resp = {
                    "id": did,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "response": result if isinstance(result, str) else "(Dispatch completed)",
                }
                _dispatch_responses.append(resp)
                asyncio.run_coroutine_threadsafe(
                    _broadcast_response(did, resp), loop
                )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return JSONResponse({"ok": True, "dispatch_id": did})


def _run_streaming(did: int, loop: asyncio.AbstractEventLoop):
    """Execute a streaming dispatch, broadcasting chunks over WebSocket."""
    d = _dispatcher
    with d._dispatch_lock:
        # Build the prompt (mirrors _dispatch_unlocked prompt logic)
        if d.context:
            prior, new = d.buffer.take_with_context(d.context_limit)
        else:
            prior = []
            new = d.buffer.take_unsent()

        if not new:
            resp = {
                "id": did,
                "time": datetime.now().strftime("%H:%M:%S"),
                "response": "(No new transcript to send)",
            }
            _dispatch_responses.append(resp)
            asyncio.run_coroutine_threadsafe(
                _broadcast_response(did, resp), loop
            )
            return

        prompt = d._build_prompt(prior, new)
        d._dispatch_count += 1

    # Stream chunks outside the lock so the provider can take its time
    full_response = []
    for chunk in d.provider.send_streaming(prompt):
        full_response.append(chunk)
        asyncio.run_coroutine_threadsafe(
            _broadcast(
                {
                    "type": "llm_streaming_chunk",
                    "id": did,
                    "chunk": chunk,
                }
            ),
            loop,
        )

    response_text = "".join(full_response).strip() or None

    # Track conversation history if enabled
    if d.conversation and response_text:
        d._history.append(
            {
                "transcript": d._format_segments(new),
                "response": response_text,
            }
        )

    # Send the final complete response
    resp = {
        "id": did,
        "time": datetime.now().strftime("%H:%M:%S"),
        "response": response_text or "(No response from LLM)",
    }
    _dispatch_responses.append(resp)
    asyncio.run_coroutine_threadsafe(_broadcast_response(did, resp), loop)


@app.post("/api/settings")
async def api_settings(request: Request):
    body = await request.json()
    _settings.update({k: v for k, v in body.items() if k in _settings})
    return JSONResponse({"ok": True, "settings": _settings})


@app.get("/api/presets")
async def api_presets():
    """Return all available prompt presets (built-in + custom)."""
    presets = get_all_presets()
    return JSONResponse({
        "presets": presets,
        "default": DEFAULT_PRESET,
    })


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
