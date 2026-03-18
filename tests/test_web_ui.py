"""
Tests for the live-scribe web UI server.

Uses FastAPI's TestClient (which wraps httpx) to test REST endpoints,
static file serving, WebSocket message handling, and status responses.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import web_server
from live_scribe import TranscriptionBuffer


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
        "llm": "claude-cli",
        "llm_model": None,
        "stream": False,
        "conversation": False,
        "diarize": False,
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

    @patch("web_server.AudioTranscriber")
    def test_start_with_config(self, mock_transcriber_cls, client):
        mock_instance = MagicMock()
        mock_instance.buffer = TranscriptionBuffer()
        mock_transcriber_cls.return_value = mock_instance

        resp = client.post("/api/start", json={"model": "small", "language": "en"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert web_server._settings["model"] == "small"
        assert web_server._settings["language"] == "en"


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
            status = ws.receive_json()
            assert status["type"] == "status"
            assert status["recording"] is False
            # Send stop (should not crash even when not recording)
            ws.send_json({"type": "stop"})
            # Connection should remain open -- send a ping-like message
            ws.send_json({"type": "unknown"})

    def test_ws_invalid_json_ignored(self, client):
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_text("not valid json")
            # Connection should stay open -- verify by sending a valid message after
            ws.send_json({"type": "unknown"})
            # If we got here without exception, the connection is still open
            assert True


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


# ---------- Security / binding ----------

class TestSecurity:
    def test_default_host_is_localhost(self):
        """start_web_server should default to 127.0.0.1, not 0.0.0.0."""
        import inspect
        sig = inspect.signature(web_server.start_web_server)
        assert sig.parameters["host"].default == "127.0.0.1"

    def test_ws_lock_is_asyncio(self):
        """_ws_lock should be an asyncio.Lock, not threading.Lock."""
        import asyncio
        assert isinstance(web_server._ws_lock, asyncio.Lock)


# ---------- LLM naming ----------

class TestLLMNaming:
    def test_uses_llm_dispatcher(self):
        """web_server should import LLMDispatcher, not ClaudeDispatcher."""
        assert hasattr(web_server, 'LLMDispatcher')

    def test_settings_has_llm_keys(self):
        """Settings should have llm/llm_model keys, not claude_model."""
        assert "llm" in web_server._settings
        assert "llm_model" in web_server._settings

    def test_web_ui_no_claude_hardcoding(self):
        """index.html should not reference 'Claude' in buttons/labels."""
        html_path = web_server.WEB_DIR / "index.html"
        html = html_path.read_text()
        assert "Dispatch to Claude" not in html
        assert "Dispatch to LLM" in html
        assert "Responses from Claude" not in html


# ---------- Standalone entry point ----------

class TestStandaloneEntryPoint:
    def test_has_main_block(self):
        """web_server.py should be launchable standalone with argparse."""
        source = Path(web_server.__file__).read_text()
        assert 'if __name__ == "__main__":' in source
        assert "argparse" in source


# ---------- StartConfig model ----------

class TestStartConfig:
    def test_start_config_fields(self):
        cfg = web_server.StartConfig(model="small", language="en", stream=True)
        assert cfg.model == "small"
        assert cfg.language == "en"
        assert cfg.stream is True

    def test_start_config_defaults_to_none(self):
        cfg = web_server.StartConfig()
        assert cfg.model is None
        assert cfg.language is None
        assert cfg.llm is None

    def test_start_config_exclude_none(self):
        cfg = web_server.StartConfig(model="small")
        dumped = cfg.model_dump(exclude_none=True)
        assert "model" in dumped
        assert "language" not in dumped
