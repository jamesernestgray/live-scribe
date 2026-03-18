"""Tests for export format support: txt, md, json, srt."""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from live_scribe import save_transcript


# ── Helpers ──

def _make_segments(count=3, start_time=None, with_speakers=True):
    """Create a list of test transcript segments."""
    if start_time is None:
        start_time = datetime(2025, 3, 18, 11, 46, 46).timestamp()
    segments = []
    for i in range(count):
        seg = {
            "time": start_time + i * 6,
            "text": f"Segment number {i}",
            "speaker": f"SPEAKER_{i:02d}" if with_speakers else None,
        }
        segments.append(seg)
    return segments


def _make_dispatches():
    """Create sample dispatch history."""
    return [
        {"time": "11:47:30", "response": "Here is my analysis.", "segments_count": 5},
        {"time": "11:48:15", "response": "The discussion moved on.", "segments_count": 3},
    ]


def _save_and_read(segments, fmt, **kwargs):
    """Save segments to a temp file and return the content as a string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=f".{fmt}", delete=False) as f:
        path = f.name
    try:
        save_transcript(segments, Path(path), fmt=fmt, **kwargs)
        return Path(path).read_text(encoding="utf-8")
    finally:
        os.unlink(path)


# ── TXT format tests ──


class TestTxtFormat:
    """Test plain-text export format (default)."""

    def test_txt_basic_output(self):
        segments = _make_segments()
        content = _save_and_read(segments, "txt")
        lines = content.strip().split("\n")
        assert len(lines) == 3

    def test_txt_timestamp_format(self):
        segments = _make_segments(count=1)
        content = _save_and_read(segments, "txt")
        # Should contain [YYYY-MM-DD HH:MM:SS]
        assert "[2025-03-18 11:46:46]" in content

    def test_txt_speaker_label(self):
        segments = _make_segments(count=1, with_speakers=True)
        content = _save_and_read(segments, "txt")
        assert "[SPEAKER_00]" in content

    def test_txt_no_speaker(self):
        segments = _make_segments(count=1, with_speakers=False)
        content = _save_and_read(segments, "txt")
        assert "SPEAKER" not in content

    def test_txt_segment_text(self):
        segments = _make_segments(count=1)
        content = _save_and_read(segments, "txt")
        assert "Segment number 0" in content


# ── MD format tests ──


class TestMdFormat:
    """Test Markdown export format."""

    def test_md_has_title(self):
        segments = _make_segments()
        content = _save_and_read(segments, "md")
        assert "# Live Scribe Session - 2025-03-18" in content

    def test_md_has_transcript_header(self):
        segments = _make_segments()
        content = _save_and_read(segments, "md")
        assert "## Transcript" in content

    def test_md_segment_formatting(self):
        segments = _make_segments(count=1)
        content = _save_and_read(segments, "md")
        assert "**11:46:46 - SPEAKER_00:**" in content
        assert "Segment number 0" in content

    def test_md_without_dispatches(self):
        segments = _make_segments()
        content = _save_and_read(segments, "md")
        assert "## LLM Analysis" not in content

    def test_md_with_dispatches(self):
        segments = _make_segments()
        dispatches = _make_dispatches()
        content = _save_and_read(segments, "md", dispatches=dispatches)
        assert "## LLM Analysis" in content
        assert "### Dispatch #1 (11:47:30)" in content
        assert "### Dispatch #2 (11:48:15)" in content
        assert "Here is my analysis." in content

    def test_md_has_separator_before_analysis(self):
        segments = _make_segments()
        dispatches = _make_dispatches()
        content = _save_and_read(segments, "md", dispatches=dispatches)
        assert "---" in content

    def test_md_no_speaker_shows_unknown(self):
        segments = _make_segments(count=1, with_speakers=False)
        content = _save_and_read(segments, "md")
        assert "UNKNOWN" in content


# ── JSON format tests ──


class TestJsonFormat:
    """Test JSON export format."""

    def test_json_is_valid(self):
        segments = _make_segments()
        content = _save_and_read(segments, "json")
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_json_has_session_metadata(self):
        segments = _make_segments()
        content = _save_and_read(segments, "json", model="small", language="en", provider="openai")
        data = json.loads(content)
        session = data["session"]
        assert session["model"] == "small"
        assert session["language"] == "en"
        assert session["provider"] == "openai"

    def test_json_session_timestamps(self):
        segments = _make_segments()
        content = _save_and_read(segments, "json")
        data = json.loads(content)
        assert data["session"]["start"] == "2025-03-18T11:46:46"
        # end = start + 2*6s = 11:46:58
        assert data["session"]["end"] == "2025-03-18T11:46:58"

    def test_json_segments_count(self):
        segments = _make_segments(count=5)
        content = _save_and_read(segments, "json")
        data = json.loads(content)
        assert len(data["segments"]) == 5

    def test_json_segment_structure(self):
        segments = _make_segments(count=1)
        content = _save_and_read(segments, "json")
        data = json.loads(content)
        seg = data["segments"][0]
        assert "time" in seg
        assert "speaker" in seg
        assert "text" in seg
        assert seg["time"] == "11:46:46"
        assert seg["speaker"] == "SPEAKER_00"
        assert seg["text"] == "Segment number 0"

    def test_json_dispatches_empty_by_default(self):
        segments = _make_segments()
        content = _save_and_read(segments, "json")
        data = json.loads(content)
        assert data["dispatches"] == []

    def test_json_dispatches_included(self):
        segments = _make_segments()
        dispatches = _make_dispatches()
        content = _save_and_read(segments, "json", dispatches=dispatches)
        data = json.loads(content)
        assert len(data["dispatches"]) == 2
        assert data["dispatches"][0]["id"] == 1
        assert data["dispatches"][0]["response"] == "Here is my analysis."

    def test_json_default_metadata(self):
        """With no explicit metadata, defaults should be used."""
        segments = _make_segments()
        content = _save_and_read(segments, "json")
        data = json.loads(content)
        assert data["session"]["model"] == "base"
        assert data["session"]["language"] == "auto"
        assert data["session"]["provider"] == "claude-cli"


# ── SRT format tests ──


class TestSrtFormat:
    """Test SRT subtitle export format."""

    def test_srt_sequence_numbers(self):
        segments = _make_segments(count=3)
        content = _save_and_read(segments, "srt")
        lines = content.strip().split("\n")
        # First non-blank line should be "1"
        assert lines[0] == "1"

    def test_srt_timestamp_format(self):
        segments = _make_segments(count=1)
        content = _save_and_read(segments, "srt")
        # First segment starts at 00:00:00,000
        assert "00:00:00,000 -->" in content

    def test_srt_relative_timestamps(self):
        """Timestamps should be relative to session start."""
        start = datetime(2025, 3, 18, 11, 46, 46).timestamp()
        segments = [
            {"time": start, "text": "First", "speaker": "SPEAKER_00"},
            {"time": start + 6, "text": "Second", "speaker": "SPEAKER_01"},
            {"time": start + 12, "text": "Third", "speaker": "SPEAKER_00"},
        ]
        content = _save_and_read(segments, "srt")
        # First: 0s -> 6s
        assert "00:00:00,000 --> 00:00:06,000" in content
        # Second: 6s -> 12s
        assert "00:00:06,000 --> 00:00:12,000" in content
        # Third: 12s -> 18s (last segment gets +6s default)
        assert "00:00:12,000 --> 00:00:18,000" in content

    def test_srt_speaker_in_text(self):
        segments = _make_segments(count=1, with_speakers=True)
        content = _save_and_read(segments, "srt")
        assert "[SPEAKER_00]" in content

    def test_srt_no_speaker(self):
        segments = _make_segments(count=1, with_speakers=False)
        content = _save_and_read(segments, "srt")
        assert "SPEAKER" not in content
        assert "Segment number 0" in content

    def test_srt_block_count(self):
        """Each segment should produce one SRT block (number, timestamps, text, blank)."""
        segments = _make_segments(count=4)
        content = _save_and_read(segments, "srt")
        # Count sequence numbers
        blocks = content.strip().split("\n\n")
        assert len(blocks) == 4

    def test_srt_long_session_timestamps(self):
        """Test SRT timestamp formatting for sessions over 1 hour."""
        start = datetime(2025, 3, 18, 10, 0, 0).timestamp()
        segments = [
            {"time": start, "text": "Start", "speaker": None},
            {"time": start + 3661.5, "text": "Over an hour later", "speaker": None},
        ]
        content = _save_and_read(segments, "srt")
        # Second segment starts at 1h 1m 1.5s
        assert "01:01:01,500" in content


# ── Edge cases ──


class TestEdgeCases:
    """Test edge cases for export formats."""

    def test_empty_transcript(self):
        """All formats should handle empty segment list gracefully."""
        for fmt in ["txt", "md", "json", "srt"]:
            with tempfile.NamedTemporaryFile(mode="w", suffix=f".{fmt}", delete=False) as f:
                path = f.name
            try:
                save_transcript([], Path(path), fmt=fmt)
                content = Path(path).read_text()
                if fmt == "json":
                    data = json.loads(content)
                    assert data["segments"] == []
                else:
                    assert content == ""  # empty output for empty input
            finally:
                os.unlink(path)

    def test_single_segment(self):
        """All formats should handle a single segment."""
        segments = _make_segments(count=1)
        for fmt in ["txt", "md", "json", "srt"]:
            content = _save_and_read(segments, fmt)
            assert len(content) > 0

    def test_unknown_format_falls_back_to_txt(self):
        """An unrecognized format string should fall back to txt behavior."""
        segments = _make_segments(count=1)
        content = _save_and_read(segments, "unknown_format")
        assert "[2025-03-18 11:46:46]" in content

    def test_save_transcript_default_format(self):
        """Calling save_transcript without fmt should default to txt."""
        segments = _make_segments(count=1)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            save_transcript(segments, Path(path))
            content = Path(path).read_text()
            assert "[2025-03-18 11:46:46]" in content
        finally:
            os.unlink(path)


# ── Argument parsing ──


class TestFormatArgument:
    """Test --format argument parsing."""

    def test_format_choices(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--format", dest="save_format", default="txt",
                            choices=["txt", "md", "json", "srt"])

        args = parser.parse_args([])
        assert args.save_format == "txt"

        args = parser.parse_args(["--format", "md"])
        assert args.save_format == "md"

        args = parser.parse_args(["--format", "json"])
        assert args.save_format == "json"

        args = parser.parse_args(["--format", "srt"])
        assert args.save_format == "srt"

    def test_format_invalid_choice(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--format", dest="save_format", default="txt",
                            choices=["txt", "md", "json", "srt"])
        with pytest.raises(SystemExit):
            parser.parse_args(["--format", "csv"])
