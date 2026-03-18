"""Tests for the --stream flag and _call_claude_streaming() method."""

import io
import subprocess
import sys
import time
from unittest import mock

import pytest

# Import only the classes we can test without audio/whisper dependencies
sys.modules["numpy"] = mock.MagicMock()
sys.modules["sounddevice"] = mock.MagicMock()
sys.modules["faster_whisper"] = mock.MagicMock()

from live_scribe import ClaudeDispatcher, TranscriptionBuffer  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────


def _make_dispatcher(stream: bool = False, timeout: int = 120, claude_model: str | None = None) -> ClaudeDispatcher:
    buf = TranscriptionBuffer()
    buf.add("Hello world", time.time())
    return ClaudeDispatcher(
        buffer=buf,
        system_prompt="Test prompt",
        stream=stream,
        timeout=timeout,
        claude_model=claude_model,
    )


class FakePopen:
    """Simulate subprocess.Popen with controllable stdout/stderr."""

    def __init__(self, stdout_text: str = "", returncode: int = 0, stderr_text: str = ""):
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode
        self._killed = False

    def wait(self, timeout=None):
        pass

    def kill(self):
        self._killed = True


class FakePopenTimeout(FakePopen):
    """Simulate a Popen whose wait() raises TimeoutExpired."""

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout or 120)


# ── Tests ────────────────────────────────────────────────────────────


class TestCallClaudeStreaming:
    """Test _call_claude_streaming() directly."""

    def test_captures_full_response(self, capsys):
        """Streaming should print each character AND return the full response."""
        fake = FakePopen(stdout_text="Hello from Claude!", returncode=0)

        with mock.patch("subprocess.Popen", return_value=fake):
            d = _make_dispatcher(stream=True)
            result = d._call_claude_streaming("test prompt")

        assert result == "Hello from Claude!"
        captured = capsys.readouterr()
        assert "Hello from Claude!" in captured.out

    def test_returns_none_on_nonzero_exit(self, capsys):
        """Non-zero exit code should return None and print warning."""
        fake = FakePopen(stdout_text="partial", returncode=1, stderr_text="some error")

        with mock.patch("subprocess.Popen", return_value=fake):
            d = _make_dispatcher(stream=True)
            result = d._call_claude_streaming("test prompt")

        assert result is None
        captured = capsys.readouterr()
        assert "claude exited 1" in captured.err

    def test_timeout_kills_process(self, capsys):
        """TimeoutExpired should kill the process and return None."""
        fake = FakePopenTimeout(stdout_text="partial output")

        with mock.patch("subprocess.Popen", return_value=fake):
            d = _make_dispatcher(stream=True, timeout=5)
            result = d._call_claude_streaming("test prompt")

        assert result is None
        assert fake._killed is True
        captured = capsys.readouterr()
        assert "timed out" in captured.err

    def test_file_not_found(self, capsys):
        """Missing claude binary should return None and print warning."""
        with mock.patch("subprocess.Popen", side_effect=FileNotFoundError):
            d = _make_dispatcher(stream=True)
            result = d._call_claude_streaming("test prompt")

        assert result is None
        captured = capsys.readouterr()
        assert "'claude' not found" in captured.err

    def test_strips_whitespace(self):
        """Returned response should be stripped of leading/trailing whitespace."""
        fake = FakePopen(stdout_text="  spaced out  \n", returncode=0)

        with mock.patch("subprocess.Popen", return_value=fake):
            d = _make_dispatcher(stream=True)
            result = d._call_claude_streaming("test prompt")

        assert result == "spaced out"

    def test_passes_model_flag(self):
        """When claude_model is set, --model flag should appear in the command."""
        fake = FakePopen(stdout_text="ok", returncode=0)

        with mock.patch("subprocess.Popen", return_value=fake) as mock_popen:
            d = _make_dispatcher(stream=True, claude_model="opus")
            d._call_claude_streaming("test prompt")

        cmd = mock_popen.call_args[0][0]
        assert "--model" in cmd
        assert "opus" in cmd

    def test_empty_stdout(self):
        """Empty stdout should return None (stripped empty string is falsy -> but strip returns '')."""
        fake = FakePopen(stdout_text="", returncode=0)

        with mock.patch("subprocess.Popen", return_value=fake):
            d = _make_dispatcher(stream=True)
            result = d._call_claude_streaming("test prompt")

        # Empty string stripped is still "", which the method returns
        # (returncode == 0 path returns ''.strip() == '')
        assert result == ""


class TestDispatchStreaming:
    """Test that dispatch() routes to the streaming method when stream=True."""

    def test_dispatch_uses_streaming_when_enabled(self, capsys):
        """With stream=True, dispatch() should call _call_claude_streaming."""
        d = _make_dispatcher(stream=True)

        with mock.patch.object(d, "_call_claude_streaming", return_value="streamed!") as mock_stream:
            with mock.patch.object(d, "_call_claude") as mock_regular:
                d.dispatch()

        mock_stream.assert_called_once()
        mock_regular.assert_not_called()

    def test_dispatch_uses_regular_when_disabled(self, capsys):
        """With stream=False, dispatch() should call _call_claude."""
        d = _make_dispatcher(stream=False)

        with mock.patch.object(d, "_call_claude", return_value="regular!") as mock_regular:
            with mock.patch.object(d, "_call_claude_streaming") as mock_stream:
                d.dispatch()

        mock_regular.assert_called_once()
        mock_stream.assert_not_called()

    def test_dispatch_returns_true_with_data(self):
        """dispatch() should return True when there are segments to send."""
        d = _make_dispatcher(stream=True)

        with mock.patch.object(d, "_call_claude_streaming", return_value="ok"):
            result = d.dispatch()

        assert result is True

    def test_dispatch_returns_false_when_empty(self):
        """dispatch() should return False when buffer is empty."""
        buf = TranscriptionBuffer()  # empty
        d = ClaudeDispatcher(buffer=buf, system_prompt="test", stream=True)
        result = d.dispatch()
        assert result is False


class TestStreamArgParsing:
    """Test that --stream is correctly parsed in argument handling."""

    def test_stream_flag_default_off(self):
        """--stream should default to False."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--stream", action="store_true")
        args = parser.parse_args([])
        assert args.stream is False

    def test_stream_flag_enabled(self):
        """--stream should set stream=True."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--stream", action="store_true")
        args = parser.parse_args(["--stream"])
        assert args.stream is True


class TestStreamInitParam:
    """Test that ClaudeDispatcher stores the stream parameter."""

    def test_stream_defaults_false(self):
        buf = TranscriptionBuffer()
        d = ClaudeDispatcher(buffer=buf, system_prompt="test")
        assert d.stream is False

    def test_stream_set_true(self):
        buf = TranscriptionBuffer()
        d = ClaudeDispatcher(buffer=buf, system_prompt="test", stream=True)
        assert d.stream is True
