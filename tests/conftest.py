"""Shared pytest fixtures and module-level mocking for test suite."""

import sys
from unittest.mock import MagicMock

# Mock audio/ML dependencies before any test imports live_scribe.
# These modules require native libraries that are not available in CI.
_mock_sd = MagicMock()
_mock_np = MagicMock()
_mock_whisper = MagicMock()

sys.modules.setdefault("sounddevice", _mock_sd)
sys.modules.setdefault("numpy", _mock_np)
sys.modules.setdefault("faster_whisper", _mock_whisper)

import pytest  # noqa: E402


@pytest.fixture
def buffer():
    """Return a fresh, empty TranscriptionBuffer."""
    from live_scribe import TranscriptionBuffer
    return TranscriptionBuffer()


@pytest.fixture
def buffer_with_segments():
    """Return a TranscriptionBuffer pre-loaded with two segments."""
    from live_scribe import TranscriptionBuffer
    buf = TranscriptionBuffer()
    buf.add("hello", 1000.0)
    buf.add("world", 1001.0, speaker="SPEAKER_00")
    return buf
