"""Tests for TranscriptionBuffer.take_with_context() and save_transcript()."""

import os
import tempfile
import time
from pathlib import Path

import pytest

from live_scribe import TranscriptionBuffer, save_transcript


# -- take_with_context() with various context_limit values --


class TestTakeWithContext:
    def test_context_limit_zero_returns_all_prior(self):
        """context_limit=0 means unlimited -- return all prior segments."""
        buf = TranscriptionBuffer()
        # Add 5 segments and mark first 3 as sent
        for i in range(5):
            buf.add(f"seg{i}", 1000.0 + i)
        buf.take_unsent()  # mark all 5 as sent

        # Add 2 new segments
        buf.add("new1", 2000.0)
        buf.add("new2", 2001.0)

        prior, new = buf.take_with_context(context_limit=0)
        assert len(prior) == 5
        assert len(new) == 2
        assert prior[0]["text"] == "seg0"
        assert prior[4]["text"] == "seg4"
        assert new[0]["text"] == "new1"
        assert new[1]["text"] == "new2"

    def test_context_limit_truncates_prior(self):
        """context_limit=2 should return only the last 2 prior segments."""
        buf = TranscriptionBuffer()
        for i in range(5):
            buf.add(f"seg{i}", 1000.0 + i)
        buf.take_unsent()  # mark all as sent

        buf.add("new1", 2000.0)

        prior, new = buf.take_with_context(context_limit=2)
        assert len(prior) == 2
        assert prior[0]["text"] == "seg3"
        assert prior[1]["text"] == "seg4"
        assert len(new) == 1
        assert new[0]["text"] == "new1"

    def test_context_limit_larger_than_prior(self):
        """context_limit larger than available prior returns all prior."""
        buf = TranscriptionBuffer()
        buf.add("only_prior", 1000.0)
        buf.take_unsent()

        buf.add("new", 2000.0)

        prior, new = buf.take_with_context(context_limit=100)
        assert len(prior) == 1
        assert prior[0]["text"] == "only_prior"
        assert len(new) == 1

    def test_no_prior_segments(self):
        """When nothing has been sent yet, prior should be empty."""
        buf = TranscriptionBuffer()
        buf.add("first", 1000.0)
        buf.add("second", 1001.0)

        prior, new = buf.take_with_context(context_limit=0)
        assert len(prior) == 0
        assert len(new) == 2

    def test_after_multiple_take_cycles(self):
        """After several take_with_context calls, prior grows correctly."""
        buf = TranscriptionBuffer()

        # Cycle 1
        buf.add("cycle1_a", 1000.0)
        buf.add("cycle1_b", 1001.0)
        prior, new = buf.take_with_context(context_limit=0)
        assert len(prior) == 0
        assert len(new) == 2

        # Cycle 2
        buf.add("cycle2_a", 2000.0)
        prior, new = buf.take_with_context(context_limit=0)
        assert len(prior) == 2  # cycle1_a, cycle1_b
        assert len(new) == 1   # cycle2_a
        assert prior[0]["text"] == "cycle1_a"
        assert prior[1]["text"] == "cycle1_b"

        # Cycle 3
        buf.add("cycle3_a", 3000.0)
        buf.add("cycle3_b", 3001.0)
        prior, new = buf.take_with_context(context_limit=0)
        assert len(prior) == 3  # cycle1_a, cycle1_b, cycle2_a
        assert len(new) == 2
        assert prior[2]["text"] == "cycle2_a"

    def test_after_multiple_take_cycles_with_limit(self):
        """Limit should slice the growing prior correctly."""
        buf = TranscriptionBuffer()

        buf.add("a", 1000.0)
        buf.add("b", 1001.0)
        buf.add("c", 1002.0)
        buf.take_with_context(context_limit=0)  # mark a, b, c as sent

        buf.add("d", 2000.0)
        buf.add("e", 2001.0)
        buf.take_with_context(context_limit=0)  # mark d, e as sent

        buf.add("f", 3000.0)
        prior, new = buf.take_with_context(context_limit=2)
        assert len(prior) == 2
        assert prior[0]["text"] == "d"
        assert prior[1]["text"] == "e"
        assert new[0]["text"] == "f"

    def test_returns_empty_when_nothing_new(self):
        """When there are no unsent segments, new should be empty."""
        buf = TranscriptionBuffer()
        buf.add("sent", 1000.0)
        buf.take_unsent()

        prior, new = buf.take_with_context(context_limit=0)
        assert len(new) == 0
        assert len(prior) == 1


# -- save_transcript() --


class TestSaveTranscript:
    def test_save_transcript_writes_file(self):
        segments = [
            {"text": "Hello", "time": 1000.0, "speaker": None},
            {"text": "World", "time": 1001.0, "speaker": "SPEAKER_00"},
        ]
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = Path(f.name)
        try:
            save_transcript(segments, path)
            content = path.read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2
            assert "Hello" in lines[0]
            assert "[SPEAKER_00]" in lines[1]
            assert "World" in lines[1]
        finally:
            os.unlink(path)

    def test_save_transcript_format(self):
        """Verify timestamp format in saved transcript."""
        segments = [
            {"text": "Test", "time": 1000.0, "speaker": None},
        ]
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = Path(f.name)
        try:
            save_transcript(segments, path)
            content = path.read_text().strip()
            # Should start with [YYYY-MM-DD HH:MM:SS]
            assert content.startswith("[")
            assert "] Test" in content
        finally:
            os.unlink(path)

    def test_save_transcript_empty_segments(self):
        """Saving an empty list should create an empty file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = Path(f.name)
        try:
            save_transcript([], path)
            content = path.read_text()
            assert content == ""
        finally:
            os.unlink(path)
