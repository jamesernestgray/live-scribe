"""Tests for the --stream flag and provider-based streaming in LLMDispatcher."""

import time
from unittest import mock

import pytest

from live_scribe import ClaudeDispatcher, LLMDispatcher, TranscriptionBuffer, build_parser


# ── Helpers ──────────────────────────────────────────────────────────


def _make_dispatcher(stream: bool = False, timeout: int = 120) -> LLMDispatcher:
    buf = TranscriptionBuffer()
    buf.add("Hello world", time.time())
    return LLMDispatcher(
        buffer=buf,
        system_prompt="Test prompt",
        stream=stream,
        timeout=timeout,
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestProviderStreaming:
    """Test that dispatch() uses provider.send_streaming() when stream=True."""

    def test_dispatch_uses_streaming_when_enabled(self, capsys):
        """With stream=True, dispatch() should call provider.send_streaming."""
        d = _make_dispatcher(stream=True)

        with mock.patch.object(d.provider, "send_streaming", return_value=iter(["Hello ", "world!"])) as mock_stream:
            with mock.patch.object(d.provider, "send") as mock_regular:
                d.dispatch()

        mock_stream.assert_called_once()
        mock_regular.assert_not_called()

    def test_dispatch_uses_regular_when_disabled(self, capsys):
        """With stream=False, dispatch() should call provider.send."""
        d = _make_dispatcher(stream=False)

        with mock.patch.object(d.provider, "send", return_value="regular!") as mock_regular:
            with mock.patch.object(d.provider, "send_streaming") as mock_stream:
                d.dispatch()

        mock_regular.assert_called_once()
        mock_stream.assert_not_called()

    def test_streaming_captures_full_response(self, capsys):
        """Streaming should print each chunk AND track the full response."""
        d = _make_dispatcher(stream=True)
        d.conversation = True  # enable to check response is captured

        chunks = ["Hello", " from", " streaming!"]
        with mock.patch.object(d.provider, "send_streaming", return_value=iter(chunks)):
            d.dispatch()

        # Verify response was captured in conversation history
        assert len(d._history) == 1
        assert d._history[0]["response"] == "Hello from streaming!"

        # Verify output was printed
        captured = capsys.readouterr()
        assert "Hello from streaming!" in captured.out

    def test_streaming_empty_response(self):
        """Empty streaming response should result in no conversation history entry."""
        d = _make_dispatcher(stream=True)
        d.conversation = True

        with mock.patch.object(d.provider, "send_streaming", return_value=iter([])):
            d.dispatch()

        assert len(d._history) == 0

    def test_streaming_whitespace_only_response(self):
        """Whitespace-only streaming response should be treated as None."""
        d = _make_dispatcher(stream=True)
        d.conversation = True

        with mock.patch.object(d.provider, "send_streaming", return_value=iter(["  ", "\n"])):
            d.dispatch()

        assert len(d._history) == 0

    def test_dispatch_returns_true_with_data(self):
        """dispatch() should return True when there are segments to send."""
        d = _make_dispatcher(stream=True)

        with mock.patch.object(d.provider, "send_streaming", return_value=iter(["ok"])):
            result = d.dispatch()

        assert result is True

    def test_dispatch_returns_false_when_empty(self):
        """dispatch() should return False when buffer is empty."""
        buf = TranscriptionBuffer()  # empty
        d = LLMDispatcher(buffer=buf, system_prompt="test", stream=True)
        result = d.dispatch()
        assert result is False


class TestStreamArgParsing:
    """Test that --stream is correctly parsed in argument handling."""

    def test_stream_flag_default_off(self):
        """--stream should default to False."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.stream is False

    def test_stream_flag_enabled(self):
        """--stream should set stream=True."""
        parser = build_parser()
        args = parser.parse_args(["--stream"])
        assert args.stream is True


class TestStreamInitParam:
    """Test that LLMDispatcher stores the stream parameter."""

    def test_stream_defaults_false(self):
        buf = TranscriptionBuffer()
        d = LLMDispatcher(buffer=buf, system_prompt="test")
        assert d.stream is False

    def test_stream_set_true(self):
        buf = TranscriptionBuffer()
        d = LLMDispatcher(buffer=buf, system_prompt="test", stream=True)
        assert d.stream is True

    def test_claude_dispatcher_alias_works(self):
        """ClaudeDispatcher should be an alias for LLMDispatcher."""
        assert ClaudeDispatcher is LLMDispatcher
        buf = TranscriptionBuffer()
        d = ClaudeDispatcher(buffer=buf, system_prompt="test", stream=True)
        assert d.stream is True
        assert isinstance(d, LLMDispatcher)
