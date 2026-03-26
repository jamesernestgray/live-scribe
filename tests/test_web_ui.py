"""
Tests for the live-scribe web UI server.

Uses FastAPI's TestClient (which wraps httpx) to test REST endpoints,
static file serving, WebSocket message handling, and status responses.
"""

import json
import time
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
        "input_device": None,
        "compute": "cpu",
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

    def test_start_config_input_device_field(self):
        cfg = web_server.StartConfig(input_device=3)
        assert cfg.input_device == 3
        dumped = cfg.model_dump(exclude_none=True)
        assert dumped["input_device"] == 3

    def test_start_config_compute_field(self):
        cfg = web_server.StartConfig(compute="cuda")
        assert cfg.compute == "cuda"
        dumped = cfg.model_dump(exclude_none=True)
        assert dumped["compute"] == "cuda"

    def test_start_config_input_device_and_compute_together(self):
        cfg = web_server.StartConfig(input_device=2, compute="mps")
        dumped = cfg.model_dump(exclude_none=True)
        assert dumped["input_device"] == 2
        assert dumped["compute"] == "mps"


# ---------- Presets endpoint ----------

class TestPresetsEndpoint:
    @patch("web_server.get_all_presets")
    def test_presets_returns_dict_with_presets_and_default(self, mock_presets, client):
        mock_presets.return_value = {
            "collaborator": "You are a collaborator...",
            "meeting-notes": "You are a note-taker...",
        }
        resp = client.get("/api/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data
        assert "default" in data
        assert isinstance(data["presets"], dict)
        assert isinstance(data["default"], str)

    @patch("web_server.get_all_presets")
    def test_presets_contains_preset_names_and_prompts(self, mock_presets, client):
        mock_presets.return_value = {
            "collaborator": "collab prompt",
            "custom": "custom prompt",
        }
        resp = client.get("/api/presets")
        data = resp.json()
        assert "collaborator" in data["presets"]
        assert data["presets"]["collaborator"] == "collab prompt"
        assert "custom" in data["presets"]

    @patch("web_server.get_all_presets")
    def test_presets_default_is_string(self, mock_presets, client):
        mock_presets.return_value = {"collaborator": "prompt"}
        resp = client.get("/api/presets")
        data = resp.json()
        assert isinstance(data["default"], str)
        assert data["default"] == "collaborator"


# ---------- Devices endpoint ----------

class TestDevicesEndpoint:
    @patch("web_server.sd")
    def test_devices_returns_list(self, mock_sd, client):
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Mic", "max_input_channels": 2},
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "USB Mic", "max_input_channels": 1},
        ]
        mock_sd.default.device = [0, 1]

        resp = client.get("/api/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert "devices" in data
        assert isinstance(data["devices"], list)

    @patch("web_server.sd")
    def test_devices_filters_input_only(self, mock_sd, client):
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Mic", "max_input_channels": 2},
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "USB Mic", "max_input_channels": 1},
        ]
        mock_sd.default.device = [0, 1]

        resp = client.get("/api/devices")
        data = resp.json()
        # Only devices with max_input_channels > 0 should appear
        assert len(data["devices"]) == 2
        names = [d["name"] for d in data["devices"]]
        assert "Built-in Mic" in names
        assert "USB Mic" in names
        assert "Speakers" not in names

    @patch("web_server.sd")
    def test_devices_include_index_and_default(self, mock_sd, client):
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Mic", "max_input_channels": 2},
            {"name": "USB Mic", "max_input_channels": 1},
        ]
        mock_sd.default.device = [0, 1]

        resp = client.get("/api/devices")
        data = resp.json()
        dev0 = data["devices"][0]
        assert "index" in dev0
        assert "name" in dev0
        assert "channels" in dev0
        assert "default" in dev0
        assert dev0["default"] is True
        # Second device should not be default
        assert data["devices"][1]["default"] is False

    @patch("web_server.sd")
    def test_devices_empty_when_no_inputs(self, mock_sd, client):
        mock_sd.query_devices.return_value = [
            {"name": "Speakers", "max_input_channels": 0},
        ]
        mock_sd.default.device = [0, 0]

        resp = client.get("/api/devices")
        data = resp.json()
        assert data["devices"] == []


# ---------- Transcript export endpoint ----------

class TestTranscriptExportEndpoint:
    def _setup_buffer(self):
        """Put some segments in the buffer for export tests."""
        buf = TranscriptionBuffer()
        buf.add("Hello world", 1000.0, speaker="SPEAKER_00")
        buf.add("How are you", 1001.0, speaker="SPEAKER_01")
        web_server._buffer = buf
        return buf

    @patch("web_server.save_transcript")
    def test_export_txt_format(self, mock_save, client):
        self._setup_buffer()
        # Make save_transcript write content to the temp file
        def write_file(segments, path, fmt, **kwargs):
            path.write_text("Hello world\nHow are you\n", encoding="utf-8")
        mock_save.side_effect = write_file

        resp = client.get("/api/transcript/export?format=txt")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert ".txt" in resp.headers["content-disposition"]
        assert "Hello world" in resp.text

    @patch("web_server.save_transcript")
    def test_export_md_format(self, mock_save, client):
        self._setup_buffer()
        def write_file(segments, path, fmt, **kwargs):
            path.write_text("# Transcript\n\n- Hello world\n", encoding="utf-8")
        mock_save.side_effect = write_file

        resp = client.get("/api/transcript/export?format=md")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert ".md" in resp.headers["content-disposition"]

    @patch("web_server.save_transcript")
    def test_export_json_format(self, mock_save, client):
        self._setup_buffer()
        def write_file(segments, path, fmt, **kwargs):
            path.write_text('{"segments": []}', encoding="utf-8")
        mock_save.side_effect = write_file

        resp = client.get("/api/transcript/export?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        assert ".json" in resp.headers["content-disposition"]

    @patch("web_server.save_transcript")
    def test_export_srt_format(self, mock_save, client):
        self._setup_buffer()
        def write_file(segments, path, fmt, **kwargs):
            path.write_text("1\n00:00:00 --> 00:00:01\nHello\n", encoding="utf-8")
        mock_save.side_effect = write_file

        resp = client.get("/api/transcript/export?format=srt")
        assert resp.status_code == 200
        assert "text/srt" in resp.headers["content-type"]
        assert ".srt" in resp.headers["content-disposition"]

    def test_export_invalid_format_returns_error(self, client):
        resp = client.get("/api/transcript/export?format=csv")
        assert resp.status_code == 422  # FastAPI validation error

    @patch("web_server.save_transcript")
    def test_export_empty_buffer(self, mock_save, client):
        # No buffer set -- should still work with empty segments
        def write_file(segments, path, fmt, **kwargs):
            path.write_text("", encoding="utf-8")
        mock_save.side_effect = write_file

        resp = client.get("/api/transcript/export?format=txt")
        assert resp.status_code == 200

    @patch("web_server.save_transcript")
    def test_export_passes_segments_to_save(self, mock_save, client):
        self._setup_buffer()
        def write_file(segments, path, fmt, **kwargs):
            # Verify segments were passed correctly
            assert len(segments) == 2
            assert segments[0]["text"] == "Hello world"
            path.write_text("content", encoding="utf-8")
        mock_save.side_effect = write_file

        resp = client.get("/api/transcript/export?format=txt")
        assert resp.status_code == 200
        mock_save.assert_called_once()


# ---------- Settings endpoint (new fields) ----------

class TestSettingsNewFields:
    def test_update_diarize(self, client):
        resp = client.post("/api/settings", json={"diarize": True})
        assert resp.status_code == 200
        assert resp.json()["settings"]["diarize"] is True
        assert web_server._settings["diarize"] is True

    def test_update_context(self, client):
        resp = client.post("/api/settings", json={"context": True})
        assert resp.status_code == 200
        assert resp.json()["settings"]["context"] is True

    def test_update_stream(self, client):
        resp = client.post("/api/settings", json={"stream": True})
        assert resp.status_code == 200
        assert resp.json()["settings"]["stream"] is True

    def test_update_conversation(self, client):
        resp = client.post("/api/settings", json={"conversation": True})
        assert resp.status_code == 200
        assert resp.json()["settings"]["conversation"] is True

    def test_update_input_device(self, client):
        resp = client.post("/api/settings", json={"input_device": 3})
        assert resp.status_code == 200
        assert resp.json()["settings"]["input_device"] == 3
        assert web_server._settings["input_device"] == 3

    def test_update_compute(self, client):
        resp = client.post("/api/settings", json={"compute": "cuda"})
        assert resp.status_code == 200
        assert resp.json()["settings"]["compute"] == "cuda"
        assert web_server._settings["compute"] == "cuda"

    def test_update_multiple_new_fields(self, client):
        resp = client.post(
            "/api/settings",
            json={
                "diarize": True,
                "context": True,
                "stream": True,
                "conversation": True,
                "input_device": 5,
                "compute": "mps",
            },
        )
        assert resp.status_code == 200
        settings = resp.json()["settings"]
        assert settings["diarize"] is True
        assert settings["context"] is True
        assert settings["stream"] is True
        assert settings["conversation"] is True
        assert settings["input_device"] == 5
        assert settings["compute"] == "mps"


# ---------- Start with new config fields ----------

class TestStartWithNewFields:
    @patch("web_server.sd.query_devices")
    @patch("web_server.AudioTranscriber")
    def test_start_with_input_device(self, mock_transcriber_cls, mock_query_devices, client):
        mock_instance = MagicMock()
        mock_instance.buffer = TranscriptionBuffer()
        mock_transcriber_cls.return_value = mock_instance
        mock_query_devices.return_value = {"name": "Test Mic", "max_input_channels": 2}

        resp = client.post("/api/start", json={"input_device": 2})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert web_server._settings["input_device"] == 2

    @patch("web_server.AudioTranscriber")
    def test_start_with_compute(self, mock_transcriber_cls, client):
        mock_instance = MagicMock()
        mock_instance.buffer = TranscriptionBuffer()
        mock_transcriber_cls.return_value = mock_instance

        resp = client.post("/api/start", json={"compute": "cuda"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert web_server._settings["compute"] == "cuda"

    @patch("web_server.sd.query_devices")
    @patch("web_server.AudioTranscriber")
    def test_start_with_input_device_and_compute(self, mock_transcriber_cls, mock_query_devices, client):
        mock_instance = MagicMock()
        mock_instance.buffer = TranscriptionBuffer()
        mock_transcriber_cls.return_value = mock_instance
        mock_query_devices.return_value = {"name": "Test Mic", "max_input_channels": 2}

        resp = client.post(
            "/api/start",
            json={"input_device": 4, "compute": "mps"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert web_server._settings["input_device"] == 4
        assert web_server._settings["compute"] == "mps"


# ---------- Streaming dispatch ----------

class TestStreamingDispatch:
    def _setup_active_session(self):
        """Set up a mock active session with buffer and dispatcher."""
        buf = TranscriptionBuffer()
        buf.add("Hello world", time.time(), speaker="SPEAKER_00")
        web_server._buffer = buf
        web_server._recording = True

        # Use a fully-mocked dispatcher so all attributes are mockable
        mock_dispatcher = MagicMock()
        mock_dispatcher.context = False
        mock_dispatcher.conversation = False
        mock_dispatcher._dispatch_count = 0
        mock_dispatcher._history = []

        # buffer on the mock dispatcher must also be a mock
        mock_buf = MagicMock()
        mock_buf.take_unsent.return_value = buf.all()
        mock_dispatcher.buffer = mock_buf
        mock_dispatcher._build_prompt.return_value = "test prompt"

        web_server._dispatcher = mock_dispatcher
        web_server._event_loop = None  # Will use get_running_loop fallback
        return mock_dispatcher, buf

    def test_streaming_dispatch_sends_chunks_and_final(self, client):
        """When stream=True, dispatch should produce llm_streaming_chunk messages
        followed by a final llm_response."""
        mock_dispatcher, buf = self._setup_active_session()
        web_server._settings["stream"] = True

        # Mock the provider's send_streaming to yield chunks
        mock_dispatcher.provider.send_streaming.return_value = iter(["Hello ", "world!"])

        with client.websocket_connect("/ws") as ws:
            # Read initial status
            status = ws.receive_json()
            assert status["type"] == "status"
            # Read existing segment
            seg = ws.receive_json()
            assert seg["type"] == "segment"

            # Trigger dispatch via REST
            resp = client.post("/api/dispatch")
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

            # Give the background thread time to complete
            time.sleep(0.5)

            # The messages will have been sent: 2 chunks + 1 final response
            messages = []
            try:
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] == "llm_response":
                        break
            except Exception:
                pass

            chunk_msgs = [m for m in messages if m["type"] == "llm_streaming_chunk"]
            response_msgs = [m for m in messages if m["type"] == "llm_response"]
            assert len(chunk_msgs) == 2
            assert chunk_msgs[0]["chunk"] == "Hello "
            assert chunk_msgs[1]["chunk"] == "world!"
            assert len(response_msgs) == 1
            assert response_msgs[0]["response"] == "Hello world!"

    def test_non_streaming_dispatch_sends_response(self, client):
        """When stream=False, dispatch should produce an llm_response message."""
        mock_dispatcher, buf = self._setup_active_session()
        web_server._settings["stream"] = False

        # Mock dispatch to return a string
        mock_dispatcher.dispatch.return_value = "Here is my analysis."

        with client.websocket_connect("/ws") as ws:
            # Read initial status + existing segment
            ws.receive_json()  # status
            ws.receive_json()  # segment

            resp = client.post("/api/dispatch")
            assert resp.status_code == 200

            # Give the background thread time to complete
            time.sleep(0.5)

            # Should receive an llm_response
            messages = []
            try:
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] == "llm_response":
                        break
            except Exception:
                pass

            response_msgs = [m for m in messages if m["type"] == "llm_response"]
            assert len(response_msgs) == 1
            assert response_msgs[0]["response"] == "Here is my analysis."
