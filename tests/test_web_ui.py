"""
Tests for the live-scribe web UI server.

Uses FastAPI's TestClient (which wraps httpx) to test REST endpoints,
static file serving, WebSocket message handling, and status responses.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# We need to mock heavy audio/ML dependencies before importing web_server,
# since live_scribe imports sounddevice, numpy, faster_whisper at module level.

# Create mock modules for audio/ML deps
_mock_sd = MagicMock()
_mock_whisper = MagicMock()

sys.modules.setdefault("sounddevice", _mock_sd)
sys.modules.setdefault("faster_whisper", _mock_whisper)

# Mock WhisperModel so AudioTranscriber.__init__ won't actually load a model
_mock_whisper.WhisperModel = MagicMock()

import web_server  # noqa: E402
from live_scribe import TranscriptionBuffer  # noqa: E402


@pytest.fixture(autouse=True)
def reset_server_state():
    """Reset global server state between tests."""
    web_server._transcriber = None
    web_server._dispatcher = None
    web_server._buffer = None
    web_server._recording = False
    web_server._dispatch_responses.clear()
    web_server._dispatch_id = 0
    web_server._last_segment_count = 0
    web_server._settings.update({
        "model": "base",
        "language": None,
        "prompt": web_server._settings["prompt"],  # keep default
        "interval": 60,
        "context": False,
        "context_limit": 0,
        "claude_model": None,
    })
    yield


@pytest.fixture
def client():
    """FastAPI TestClient."""
    return TestClient(web_server.app)


# ---------- App creation ----------

class TestAppCreation:
    def test_create_app_returns_fastapi_instance(self):
        app = web_server.create_app()
        assert app is web_server.app

    def test_create_app_with_settings(self):
        web_server.create_app(model="small", interval=30)
        assert web_server._settings["model"] == "small"
        assert web_server._settings["interval"] == 30


# ---------- Static file serving ----------

class TestStaticServing:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "live-scribe" in resp.text

    def test_css_served(self, client):
        resp = client.get("/css/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]

    def test_js_app_served(self, client):
        resp = client.get("/js/app.js")
        assert resp.status_code == 200
        # application/javascript or text/javascript
        assert "javascript" in resp.headers["content-type"]

    def test_js_websocket_served(self, client):
        resp = client.get("/js/websocket.js")
        assert resp.status_code == 200

    def test_js_ui_served(self, client):
        resp = client.get("/js/ui.js")
        assert resp.status_code == 200


# ---------- REST endpoints ----------

class TestStatusEndpoint:
    def test_status_default(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recording"] is False
        assert data["model"] == "base"
        assert data["segments"] == 0

    def test_status_format(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "recording" in data
        assert "model" in data
        assert "segments" in data
        assert isinstance(data["recording"], bool)
        assert isinstance(data["segments"], int)


class TestTranscriptEndpoint:
    def test_transcript_empty(self, client):
        resp = client.get("/api/transcript")
        assert resp.status_code == 200
        data = resp.json()
        assert data["segments"] == []

    def test_transcript_with_data(self, client):
        import time
        buf = TranscriptionBuffer()
        buf.add("Hello world", time.time(), speaker="SPEAKER_00")
        web_server._buffer = buf

        resp = client.get("/api/transcript")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["segments"]) == 1
        seg = data["segments"][0]
        assert seg["text"] == "Hello world"
        assert seg["speaker"] == "SPEAKER_00"
        assert "time" in seg


class TestSettingsEndpoint:
    def test_update_settings(self, client):
        resp = client.post(
            "/api/settings",
            json={"model": "small", "interval": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["settings"]["model"] == "small"
        assert data["settings"]["interval"] == 30

    def test_update_ignores_unknown_keys(self, client):
        resp = client.post(
            "/api/settings",
            json={"model": "tiny", "unknown_key": "value"},
        )
        assert resp.status_code == 200
        assert "unknown_key" not in resp.json()["settings"]


class TestStartStopEndpoints:
    @patch("web_server.AudioTranscriber")
    def test_start_recording(self, mock_transcriber_cls, client):
        mock_instance = MagicMock()
        mock_instance.buffer = TranscriptionBuffer()
        mock_transcriber_cls.return_value = mock_instance

        resp = client.post("/api/start")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert web_server._recording is True

    @patch("web_server.AudioTranscriber")
    def test_start_when_already_recording(self, mock_transcriber_cls, client):
        web_server._recording = True
        resp = client.post("/api/start")
        assert resp.status_code == 409
        assert "Already recording" in resp.json()["error"]

    def test_stop_when_not_recording(self, client):
        resp = client.post("/api/stop")
        assert resp.status_code == 409
        assert "Not recording" in resp.json()["error"]

    @patch("web_server.AudioTranscriber")
    def test_stop_recording(self, mock_transcriber_cls, client):
        mock_instance = MagicMock()
        mock_instance.buffer = TranscriptionBuffer()
        mock_transcriber_cls.return_value = mock_instance

        # Start first
        client.post("/api/start")
        assert web_server._recording is True

        # Then stop
        resp = client.post("/api/stop")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert web_server._recording is False


class TestDispatchEndpoint:
    def test_dispatch_without_session(self, client):
        resp = client.post("/api/dispatch")
        assert resp.status_code == 400
        assert "No active session" in resp.json()["error"]


# ---------- WebSocket ----------

class TestWebSocket:
    def test_ws_connect_receives_status(self, client):
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "status"
            assert "recording" in data
            assert "model" in data

    def test_ws_connect_receives_existing_segments(self, client):
        import time
        buf = TranscriptionBuffer()
        buf.add("existing segment", time.time(), speaker="SPK")
        web_server._buffer = buf

        with client.websocket_connect("/ws") as ws:
            # First message is status
            status = ws.receive_json()
            assert status["type"] == "status"
            # Second message should be the existing segment
            seg = ws.receive_json()
            assert seg["type"] == "segment"
            assert seg["text"] == "existing segment"

    def test_ws_send_stop_when_not_recording(self, client):
        with client.websocket_connect("/ws") as ws:
            # Read initial status
            ws.receive_json()
            # Send stop
            ws.send_json({"type": "stop"})
            # Should get status back (from api_stop error path, but no crash)

    def test_ws_invalid_json_ignored(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_text("not valid json")
            # Should not crash — connection stays open


# ---------- WebSocket message parsing ----------

class TestMessageParsing:
    def test_segment_to_dict(self):
        import time
        now = time.time()
        seg = {"text": "hello", "time": now, "speaker": "SPEAKER_01"}
        result = web_server._segment_to_dict(seg)
        assert result["type"] == "segment"
        assert result["text"] == "hello"
        assert result["speaker"] == "SPEAKER_01"
        assert ":" in result["time"]  # HH:MM:SS format

    def test_segment_to_dict_no_speaker(self):
        import time
        seg = {"text": "hello", "time": time.time()}
        result = web_server._segment_to_dict(seg)
        assert result["speaker"] is None

    def test_status_dict_defaults(self):
        result = web_server._status_dict()
        assert result["recording"] is False
        assert result["model"] == "base"
        assert result["segments"] == 0

    def test_status_dict_with_buffer(self):
        import time
        buf = TranscriptionBuffer()
        buf.add("seg1", time.time())
        buf.add("seg2", time.time())
        web_server._buffer = buf
        web_server._recording = True

        result = web_server._status_dict()
        assert result["recording"] is True
        assert result["segments"] == 2
