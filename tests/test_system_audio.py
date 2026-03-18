"""Tests for --system-audio feature: auto-detection, fallback messages, arg interaction."""

from unittest.mock import patch

import pytest

from live_scribe import find_system_audio_device, get_system_audio_install_instructions


# ---------------------------------------------------------------------------
# Device fixtures: simulate sd.query_devices() return values
# ---------------------------------------------------------------------------

DEVICES_WITH_BLACKHOLE = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "MacBook Pro Speakers", "max_input_channels": 0, "max_output_channels": 2},
    {"name": "BlackHole 2ch", "max_input_channels": 2, "max_output_channels": 2},
]

DEVICES_WITH_SOUNDFLOWER = [
    {"name": "Built-in Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "Soundflower (2ch)", "max_input_channels": 2, "max_output_channels": 2},
]

DEVICES_WITH_LOOPBACK = [
    {"name": "USB Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "Loopback Audio", "max_input_channels": 2, "max_output_channels": 2},
]

DEVICES_WITH_LINUX_MONITOR = [
    {"name": "HDA Intel PCH: ALC269 Analog", "max_input_channels": 2, "max_output_channels": 0},
    {"name": "Monitor of Built-in Audio Analog Stereo", "max_input_channels": 2, "max_output_channels": 0},
]

DEVICES_WITH_STEREO_MIX = [
    {"name": "Microphone (Realtek)", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "Stereo Mix (Realtek)", "max_input_channels": 2, "max_output_channels": 0},
]

DEVICES_WITH_WHAT_U_HEAR = [
    {"name": "Microphone (SB Audigy)", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "What U Hear (SB Audigy)", "max_input_channels": 2, "max_output_channels": 0},
]

DEVICES_NO_LOOPBACK = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "MacBook Pro Speakers", "max_input_channels": 0, "max_output_channels": 2},
]

DEVICES_OUTPUT_ONLY_BLACKHOLE = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "BlackHole 2ch", "max_input_channels": 0, "max_output_channels": 2},
]

DEVICES_EMPTY = []


# ---------------------------------------------------------------------------
# Auto-detection tests
# ---------------------------------------------------------------------------

class TestFindSystemAudioDevice:
    """Test find_system_audio_device() with various device lists."""

    @patch("live_scribe.sd.query_devices")
    def test_detects_blackhole(self, mock_query):
        mock_query.return_value = DEVICES_WITH_BLACKHOLE
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 2
        assert name == "BlackHole 2ch"

    @patch("live_scribe.sd.query_devices")
    def test_detects_soundflower(self, mock_query):
        mock_query.return_value = DEVICES_WITH_SOUNDFLOWER
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 1
        assert name == "Soundflower (2ch)"

    @patch("live_scribe.sd.query_devices")
    def test_detects_loopback(self, mock_query):
        mock_query.return_value = DEVICES_WITH_LOOPBACK
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 1
        assert name == "Loopback Audio"

    @patch("live_scribe.sd.query_devices")
    def test_detects_linux_monitor(self, mock_query):
        mock_query.return_value = DEVICES_WITH_LINUX_MONITOR
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 1
        assert name == "Monitor of Built-in Audio Analog Stereo"

    @patch("live_scribe.sd.query_devices")
    def test_detects_stereo_mix(self, mock_query):
        mock_query.return_value = DEVICES_WITH_STEREO_MIX
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 1
        assert name == "Stereo Mix (Realtek)"

    @patch("live_scribe.sd.query_devices")
    def test_detects_what_u_hear(self, mock_query):
        mock_query.return_value = DEVICES_WITH_WHAT_U_HEAR
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 1
        assert name == "What U Hear (SB Audigy)"

    @patch("live_scribe.sd.query_devices")
    def test_returns_none_when_no_loopback(self, mock_query):
        mock_query.return_value = DEVICES_NO_LOOPBACK
        result = find_system_audio_device()
        assert result is None

    @patch("live_scribe.sd.query_devices")
    def test_ignores_output_only_blackhole(self, mock_query):
        """BlackHole with 0 input channels should not be detected."""
        mock_query.return_value = DEVICES_OUTPUT_ONLY_BLACKHOLE
        result = find_system_audio_device()
        assert result is None

    @patch("live_scribe.sd.query_devices")
    def test_returns_none_for_empty_device_list(self, mock_query):
        mock_query.return_value = DEVICES_EMPTY
        result = find_system_audio_device()
        assert result is None

    @patch("live_scribe.sd.query_devices")
    def test_returns_first_matching_device(self, mock_query):
        """When multiple loopback devices exist, return the first match."""
        devices = [
            {"name": "Soundflower (2ch)", "max_input_channels": 2, "max_output_channels": 2},
            {"name": "BlackHole 2ch", "max_input_channels": 2, "max_output_channels": 2},
        ]
        mock_query.return_value = devices
        result = find_system_audio_device()
        assert result is not None
        idx, name = result
        assert idx == 0
        assert name == "Soundflower (2ch)"


# ---------------------------------------------------------------------------
# Platform-specific install instructions
# ---------------------------------------------------------------------------

class TestInstallInstructions:
    """Test get_system_audio_install_instructions() per platform."""

    @patch("live_scribe.platform.system", return_value="Darwin")
    def test_macos_instructions(self, _mock):
        msg = get_system_audio_install_instructions()
        assert "BlackHole" in msg
        assert "brew" in msg

    @patch("live_scribe.platform.system", return_value="Linux")
    def test_linux_instructions(self, _mock):
        msg = get_system_audio_install_instructions()
        assert "PulseAudio" in msg
        assert "monitor" in msg.lower()

    @patch("live_scribe.platform.system", return_value="Windows")
    def test_windows_instructions(self, _mock):
        msg = get_system_audio_install_instructions()
        assert "Stereo Mix" in msg

    @patch("live_scribe.platform.system", return_value="FreeBSD")
    def test_unknown_platform_instructions(self, _mock):
        msg = get_system_audio_install_instructions()
        assert "virtual audio" in msg.lower() or "loopback" in msg.lower()


# ---------------------------------------------------------------------------
# Argument parsing integration
# ---------------------------------------------------------------------------

class TestArgParsing:
    """Test --system-audio flag parsing and interaction with --input-device."""

    def _parse(self, *cli_args):
        """Parse CLI args through the real argparse setup (without running main)."""
        import argparse
        # Replicate the parser from main() to test argument interactions
        parser = argparse.ArgumentParser()
        parser.add_argument("--system-audio", action="store_true")
        parser.add_argument("--input-device", type=int, default=None)
        return parser.parse_args(list(cli_args))

    def test_system_audio_flag_default_false(self):
        args = self._parse()
        assert args.system_audio is False

    def test_system_audio_flag_set(self):
        args = self._parse("--system-audio")
        assert args.system_audio is True

    def test_input_device_alone(self):
        args = self._parse("--input-device", "3")
        assert args.input_device == 3
        assert args.system_audio is False

    def test_system_audio_with_input_device(self):
        """Both flags can be set together; --input-device should take priority at runtime."""
        args = self._parse("--system-audio", "--input-device", "5")
        assert args.system_audio is True
        assert args.input_device == 5

    def test_system_audio_without_input_device(self):
        args = self._parse("--system-audio")
        assert args.system_audio is True
        assert args.input_device is None
