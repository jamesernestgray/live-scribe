"""Tests for core enhancement features: language, streaming write, audio file, session log."""

import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from live_scribe import (
    ClaudeDispatcher,
    TranscriptionBuffer,
    build_parser,
)


# ── Feature 1: --language argument parsing ──


class TestLanguageArgument:
    """Test --language / -l flag argument parsing."""

    def _parse(self, args_list):
        """Parse args using the real build_parser() from live_scribe."""
        parser = build_parser()
        return parser.parse_args(args_list)

    def test_language_default_is_none(self):
        args = self._parse([])
        assert args.language is None

    def test_language_long_flag(self):
        args = self._parse(["--language", "en"])
        assert args.language == "en"

    def test_language_short_flag(self):
        args = self._parse(["-l", "es"])
        assert args.language == "es"

    def test_language_various_codes(self):
        for code in ["en", "es", "fr", "de", "ja", "zh", "ko", "pt"]:
            args = self._parse(["-l", code])
            assert args.language == code


# ── Feature 2: --output streaming file write ──


class TestStreamingFileWrite:
    """Test TranscriptionBuffer streaming output to file."""

    def test_streaming_write_creates_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            buf = TranscriptionBuffer(output_file=path)
            ts = time.time()
            buf.add("Hello world", ts)
            buf.close_output()

            content = Path(path).read_text()
            assert "Hello world" in content
        finally:
            os.unlink(path)

    def test_streaming_write_format_without_speaker(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            buf = TranscriptionBuffer(output_file=path)
            ts = datetime(2025, 6, 15, 11, 30, 45).timestamp()
            buf.add("Test segment", ts)
            buf.close_output()

            content = Path(path).read_text().strip()
            # Format: [YYYY-MM-DD HH:MM:SS] text
            assert re.match(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Test segment", content)
        finally:
            os.unlink(path)

    def test_streaming_write_format_with_speaker(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            buf = TranscriptionBuffer(output_file=path)
            ts = datetime(2025, 6, 15, 11, 30, 45).timestamp()
            buf.add("Hello from speaker", ts, speaker="SPEAKER_00")
            buf.close_output()

            content = Path(path).read_text().strip()
            # Format: [YYYY-MM-DD HH:MM:SS] [SPEAKER] text
            assert "[SPEAKER_00]" in content
            assert "Hello from speaker" in content
        finally:
            os.unlink(path)

    def test_streaming_write_multiple_segments(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            buf = TranscriptionBuffer(output_file=path)
            base_ts = time.time()
            buf.add("First segment", base_ts)
            buf.add("Second segment", base_ts + 5)
            buf.add("Third segment", base_ts + 10)
            buf.close_output()

            lines = Path(path).read_text().strip().split("\n")
            assert len(lines) == 3
            assert "First segment" in lines[0]
            assert "Second segment" in lines[1]
            assert "Third segment" in lines[2]
        finally:
            os.unlink(path)

    def test_streaming_write_flushes_immediately(self):
        """Each add() should be readable from disk immediately."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            buf = TranscriptionBuffer(output_file=path)
            buf.add("First", time.time())

            # Read without closing — content should be there due to flush
            content = Path(path).read_text()
            assert "First" in content

            buf.add("Second", time.time())
            content = Path(path).read_text()
            assert "Second" in content

            buf.close_output()
        finally:
            os.unlink(path)

    def test_no_output_file_no_error(self):
        """Buffer without output_file should work normally."""
        buf = TranscriptionBuffer()
        buf.add("Test", time.time())
        assert len(buf) == 1


# ── Feature 3: --audio-file argument validation ──


class TestAudioFileArgument:
    """Test --audio-file argument parsing and validation."""

    def _parse(self, args_list):
        parser = build_parser()
        return parser.parse_args(args_list)

    def test_audio_file_default_is_none(self):
        args = self._parse([])
        assert args.audio_file is None

    def test_audio_file_accepts_path(self):
        args = self._parse(["--audio-file", "/tmp/test.wav"])
        assert args.audio_file == "/tmp/test.wav"

    def test_audio_file_with_manual_is_valid(self):
        """--audio-file + --manual should be parseable (no conflict)."""
        args = self._parse(["--audio-file", "/tmp/test.wav", "--manual"])
        assert args.audio_file == "/tmp/test.wav"
        assert args.manual is True


# ── Feature 4: --log-session session log formatting ──


class TestSessionLog:
    """Test session log output formatting from ClaudeDispatcher."""

    def test_session_log_format(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = f.name
        try:
            buf = TranscriptionBuffer()
            ts = time.time()
            buf.add("Hello world", ts)
            buf.add("How are you", ts + 5)

            dispatcher = ClaudeDispatcher(
                buffer=buf,
                system_prompt="Test prompt",
                session_log_file=log_path,
            )

            # Mock provider.send to return a known response
            with mock.patch.object(dispatcher.provider, "send", return_value="Analysis: all good"):
                dispatcher.dispatch()

            dispatcher.stop()

            content = Path(log_path).read_text()

            # Verify format
            assert "=== DISPATCH #1 at" in content
            assert "TRANSCRIPT:" in content
            assert "Hello world" in content
            assert "How are you" in content
            assert "LLM RESPONSE:" in content
            assert "Analysis: all good" in content
        finally:
            os.unlink(log_path)

    def test_session_log_multiple_dispatches(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = f.name
        try:
            buf = TranscriptionBuffer()
            dispatcher = ClaudeDispatcher(
                buffer=buf,
                system_prompt="Test prompt",
                session_log_file=log_path,
            )

            with mock.patch.object(dispatcher.provider, "send", return_value="Response 1"):
                buf.add("Segment 1", time.time())
                dispatcher.dispatch()

            with mock.patch.object(dispatcher.provider, "send", return_value="Response 2"):
                buf.add("Segment 2", time.time())
                dispatcher.dispatch()

            dispatcher.stop()

            content = Path(log_path).read_text()
            assert "DISPATCH #1" in content
            assert "DISPATCH #2" in content
            assert "Response 1" in content
            assert "Response 2" in content
        finally:
            os.unlink(log_path)

    def test_session_log_no_response(self):
        """When Claude returns None, log should show (no response)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = f.name
        try:
            buf = TranscriptionBuffer()
            buf.add("Test", time.time())
            dispatcher = ClaudeDispatcher(
                buffer=buf,
                system_prompt="Test prompt",
                session_log_file=log_path,
            )

            with mock.patch.object(dispatcher.provider, "send", return_value=None):
                dispatcher.dispatch()

            dispatcher.stop()

            content = Path(log_path).read_text()
            assert "(no response)" in content
        finally:
            os.unlink(log_path)

    def test_no_session_log_no_error(self):
        """Dispatcher without session_log_file should work normally."""
        buf = TranscriptionBuffer()
        buf.add("Test", time.time())
        dispatcher = ClaudeDispatcher(
            buffer=buf,
            system_prompt="Test prompt",
        )
        with mock.patch.object(dispatcher.provider, "send", return_value="OK"):
            result = dispatcher.dispatch()
        assert result is True
        dispatcher.stop()


# ── TranscriptionBuffer with speaker labels ──


class TestBufferWithSpeakers:
    """Test TranscriptionBuffer behavior with speaker labels."""

    def test_add_with_speaker(self):
        buf = TranscriptionBuffer()
        ts = time.time()
        buf.add("Hello", ts, speaker="SPEAKER_00")
        segments = buf.all()
        assert len(segments) == 1
        assert segments[0]["speaker"] == "SPEAKER_00"
        assert segments[0]["text"] == "Hello"

    def test_add_without_speaker(self):
        buf = TranscriptionBuffer()
        ts = time.time()
        buf.add("Hello", ts)
        segments = buf.all()
        assert segments[0]["speaker"] is None

    def test_mixed_speakers(self):
        buf = TranscriptionBuffer()
        ts = time.time()
        buf.add("Hi", ts, speaker="SPEAKER_00")
        buf.add("Hey", ts + 1, speaker="SPEAKER_01")
        buf.add("No speaker", ts + 2)

        segments = buf.all()
        assert segments[0]["speaker"] == "SPEAKER_00"
        assert segments[1]["speaker"] == "SPEAKER_01"
        assert segments[2]["speaker"] is None

    def test_format_segments_with_speakers(self):
        """ClaudeDispatcher._format_segments should include speaker labels."""
        ts = time.time()
        segments = [
            {"text": "Hello", "time": ts, "speaker": "SPEAKER_00"},
            {"text": "World", "time": ts + 1, "speaker": None},
        ]
        formatted = ClaudeDispatcher._format_segments(segments)
        assert "[SPEAKER_00]" in formatted
        assert "Hello" in formatted
        assert "World" in formatted


# ── Edge cases ──


class TestEdgeCases:
    """Test argument edge cases and combinations."""

    def test_dispatch_with_nothing_returns_false(self):
        buf = TranscriptionBuffer()
        dispatcher = ClaudeDispatcher(buffer=buf, system_prompt="test")
        assert dispatcher.dispatch() is False
        dispatcher.stop()

    def test_buffer_close_output_idempotent(self):
        """Calling close_output multiple times should not raise."""
        buf = TranscriptionBuffer()
        buf.close_output()
        buf.close_output()  # should not error

    def test_buffer_take_unsent_clears(self):
        buf = TranscriptionBuffer()
        buf.add("A", time.time())
        buf.add("B", time.time())
        unsent = buf.take_unsent()
        assert len(unsent) == 2
        # Second call should return empty
        unsent2 = buf.take_unsent()
        assert len(unsent2) == 0
        # But all() still has everything
        assert len(buf.all()) == 2

    def test_streaming_output_with_close(self):
        """After close_output, further adds should not write to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            buf = TranscriptionBuffer(output_file=path)
            buf.add("Before close", time.time())
            buf.close_output()
            buf.add("After close", time.time())

            content = Path(path).read_text()
            assert "Before close" in content
            assert "After close" not in content
            # But segment is still in memory
            assert len(buf.all()) == 2
        finally:
            os.unlink(path)
