"""Integration tests for combined CLI flags and end-to-end dispatch flows."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from live_scribe import (
    LLMDispatcher,
    TranscriptionBuffer,
    build_parser,
)


# -- Combined flag parsing --


class TestCombinedFlags:
    """Test that --stream + --conversation + --log-session parse together."""

    def test_stream_conversation_log_session_together(self):
        parser = build_parser()
        args = parser.parse_args([
            "--stream",
            "--conversation",
            "--log-session", "/tmp/test.log",
        ])
        assert args.stream is True
        assert args.conversation is True
        assert args.log_session == "/tmp/test.log"

    def test_stream_conversation_log_session_with_limits(self):
        parser = build_parser()
        args = parser.parse_args([
            "--stream",
            "--conversation",
            "--conversation-limit", "5",
            "--log-session", "/tmp/test.log",
            "--context",
            "--context-limit", "10",
        ])
        assert args.stream is True
        assert args.conversation is True
        assert args.conversation_limit == 5
        assert args.log_session == "/tmp/test.log"
        assert args.context is True
        assert args.context_limit == 10


# -- Context + conversation prompt building --


class TestContextConversationPrompt:
    """Test --context + --conversation prompt building end-to-end."""

    def test_context_and_conversation_prompt_structure(self):
        """Prompt should have CONVERSATION HISTORY, PRIOR CONTEXT, then NEW TRANSCRIPT."""
        buf = TranscriptionBuffer()
        d = LLMDispatcher(
            buffer=buf,
            system_prompt="Test prompt.",
            conversation=True,
            context=True,
            context_limit=0,
        )
        # Simulate a prior dispatch cycle
        d._history.append({
            "transcript": "[10:00:00] Earlier",
            "response": "Got it",
        })

        prior = [{"text": "context seg", "time": 1000.0, "speaker": None}]
        new = [{"text": "new seg", "time": 2000.0, "speaker": None}]

        prompt = d._build_prompt(prior, new)

        assert "--- CONVERSATION HISTORY ---" in prompt
        assert "--- PRIOR CONTEXT ---" in prompt
        assert "--- NEW TRANSCRIPT ---" in prompt

        idx_history = prompt.index("--- CONVERSATION HISTORY ---")
        idx_context = prompt.index("--- PRIOR CONTEXT ---")
        idx_new = prompt.index("--- NEW TRANSCRIPT ---")
        assert idx_history < idx_context < idx_new

        assert "YOUR RESPONSE: Got it" in prompt
        assert "context seg" in prompt
        assert "new seg" in prompt

    def test_context_without_conversation(self):
        """With context but no conversation, no history section."""
        buf = TranscriptionBuffer()
        d = LLMDispatcher(
            buffer=buf,
            system_prompt="Test prompt.",
            conversation=False,
            context=True,
        )

        prior = [{"text": "prior", "time": 1000.0, "speaker": None}]
        new = [{"text": "new", "time": 2000.0, "speaker": None}]
        prompt = d._build_prompt(prior, new)

        assert "--- CONVERSATION HISTORY ---" not in prompt
        assert "--- PRIOR CONTEXT ---" in prompt
        assert "--- NEW TRANSCRIPT ---" in prompt


# -- End-to-end dispatch with context --


class TestDispatchWithContextEndToEnd:
    """Test dispatch() with context=True end-to-end using a mock provider."""

    def test_dispatch_with_context_sends_prior_and_new(self):
        buf = TranscriptionBuffer()
        d = LLMDispatcher(
            buffer=buf,
            system_prompt="Analyze this.",
            context=True,
            context_limit=0,
        )

        # First dispatch -- adds to buffer and dispatches
        buf.add("segment one", 1000.0)
        buf.add("segment two", 1001.0)

        prompts_sent = []

        def capture(prompt):
            prompts_sent.append(prompt)
            return "Response 1"

        with patch.object(d.provider, "send", side_effect=capture):
            result = d.dispatch()
        assert result is not None

        # First dispatch has no prior context
        assert "--- PRIOR CONTEXT ---" not in prompts_sent[0]
        assert "segment one" in prompts_sent[0]
        assert "segment two" in prompts_sent[0]

        # Second dispatch should include prior context
        buf.add("segment three", 2000.0)

        def capture2(prompt):
            prompts_sent.append(prompt)
            return "Response 2"

        with patch.object(d.provider, "send", side_effect=capture2):
            result = d.dispatch()
        assert result is not None

        assert "--- PRIOR CONTEXT ---" in prompts_sent[1]
        assert "segment one" in prompts_sent[1]
        assert "segment two" in prompts_sent[1]
        assert "segment three" in prompts_sent[1]

    def test_dispatch_with_context_limit(self):
        """context_limit should restrict prior segments in dispatch."""
        buf = TranscriptionBuffer()
        d = LLMDispatcher(
            buffer=buf,
            system_prompt="Analyze.",
            context=True,
            context_limit=1,
        )

        buf.add("seg_a", 1000.0)
        buf.add("seg_b", 1001.0)
        buf.add("seg_c", 1002.0)

        with patch.object(d.provider, "send", return_value="OK"):
            d.dispatch()  # send a, b, c

        buf.add("seg_d", 2000.0)

        prompts = []

        def capture(prompt):
            prompts.append(prompt)
            return "OK"

        with patch.object(d.provider, "send", side_effect=capture):
            d.dispatch()

        # Only the last 1 prior segment (seg_c) should be in context
        assert "seg_a" not in prompts[0]
        assert "seg_b" not in prompts[0]
        assert "seg_c" in prompts[0]
        assert "seg_d" in prompts[0]

    def test_stream_conversation_log_session_end_to_end(self):
        """Combined --stream + --conversation + --log-session end-to-end."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        try:
            buf = TranscriptionBuffer()
            d = LLMDispatcher(
                buffer=buf,
                system_prompt="Test.",
                stream=True,
                conversation=True,
                session_log_file=log_path,
            )

            buf.add("hello stream", 1000.0)

            with patch.object(d.provider, "send_streaming", return_value=iter(["Stream ", "response"])):
                result = d.dispatch()

            assert result is not None
            assert len(d._history) == 1
            assert d._history[0]["response"] == "Stream response"

            # Log file should have been written
            d.stop()
            content = Path(log_path).read_text()
            assert "DISPATCH #1" in content
            assert "hello stream" in content
            assert "Stream response" in content
        finally:
            os.unlink(log_path)
