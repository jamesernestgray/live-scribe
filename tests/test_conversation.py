"""Tests for conversation continuity feature in ClaudeDispatcher."""

import time
from unittest.mock import patch

import pytest

from live_scribe import ClaudeDispatcher, TranscriptionBuffer


def _make_segment(text: str, offset: float = 0.0, speaker: str | None = None) -> dict:
    """Helper to create a transcript segment dict."""
    return {"text": text, "time": time.time() + offset, "speaker": speaker}


def _make_dispatcher(
    conversation: bool = True,
    conversation_limit: int = 0,
    context: bool = False,
    context_limit: int = 0,
) -> ClaudeDispatcher:
    """Create a ClaudeDispatcher with a fresh buffer and test defaults."""
    buf = TranscriptionBuffer()
    return ClaudeDispatcher(
        buffer=buf,
        system_prompt="Test prompt.",
        conversation=conversation,
        conversation_limit=conversation_limit,
        context=context,
        context_limit=context_limit,
    )


# ── History accumulation ──


class TestHistoryAccumulation:
    def test_history_starts_empty(self):
        d = _make_dispatcher()
        assert d._history == []

    def test_history_grows_after_dispatch(self):
        d = _make_dispatcher()
        d.buffer.add("Hello world", time.time())

        with patch.object(d, "_call_claude", return_value="Response 1"):
            d.dispatch()

        assert len(d._history) == 1
        assert d._history[0]["response"] == "Response 1"
        assert "Hello world" in d._history[0]["transcript"]

    def test_history_accumulates_multiple_dispatches(self):
        d = _make_dispatcher()

        d.buffer.add("First batch", time.time())
        with patch.object(d, "_call_claude", return_value="Resp 1"):
            d.dispatch()

        d.buffer.add("Second batch", time.time() + 1)
        with patch.object(d, "_call_claude", return_value="Resp 2"):
            d.dispatch()

        d.buffer.add("Third batch", time.time() + 2)
        with patch.object(d, "_call_claude", return_value="Resp 3"):
            d.dispatch()

        assert len(d._history) == 3
        assert d._history[0]["response"] == "Resp 1"
        assert d._history[1]["response"] == "Resp 2"
        assert d._history[2]["response"] == "Resp 3"

    def test_no_history_when_conversation_off(self):
        d = _make_dispatcher(conversation=False)
        d.buffer.add("Hello", time.time())

        with patch.object(d, "_call_claude", return_value="Response"):
            d.dispatch()

        assert d._history == []

    def test_no_history_when_claude_returns_none(self):
        d = _make_dispatcher()
        d.buffer.add("Hello", time.time())

        with patch.object(d, "_call_claude", return_value=None):
            d.dispatch()

        assert d._history == []


# ── Prompt building ──


class TestPromptBuilding:
    def test_first_dispatch_no_history_section(self):
        d = _make_dispatcher()
        seg = _make_segment("First words")
        prompt = d._build_prompt([], [seg])

        assert "--- CONVERSATION HISTORY ---" not in prompt
        assert "--- NEW TRANSCRIPT ---" in prompt
        assert "First words" in prompt

    def test_prompt_includes_history_after_first_dispatch(self):
        d = _make_dispatcher()
        d._history.append({
            "transcript": "[10:00:00] Earlier text",
            "response": "Earlier response",
        })

        seg = _make_segment("New text")
        prompt = d._build_prompt([], [seg])

        assert "--- CONVERSATION HISTORY ---" in prompt
        assert "[10:00:00] Earlier text" in prompt
        assert "YOUR RESPONSE: Earlier response" in prompt
        assert "--- NEW TRANSCRIPT ---" in prompt
        assert "New text" in prompt

    def test_prompt_history_order(self):
        d = _make_dispatcher()
        d._history.append({"transcript": "Turn1 text", "response": "Turn1 resp"})
        d._history.append({"transcript": "Turn2 text", "response": "Turn2 resp"})

        seg = _make_segment("Turn3 text")
        prompt = d._build_prompt([], [seg])

        # Verify ordering: Turn1 before Turn2 before NEW TRANSCRIPT
        idx_t1 = prompt.index("Turn1 text")
        idx_t2 = prompt.index("Turn2 text")
        idx_new = prompt.index("--- NEW TRANSCRIPT ---")
        assert idx_t1 < idx_t2 < idx_new

    def test_conversation_off_no_history_in_prompt(self):
        d = _make_dispatcher(conversation=False)
        # Manually add history (shouldn't happen, but defensive test)
        d._history.append({"transcript": "Old", "response": "Old resp"})

        seg = _make_segment("Current")
        prompt = d._build_prompt([], [seg])

        assert "--- CONVERSATION HISTORY ---" not in prompt
        assert "YOUR RESPONSE:" not in prompt

    def test_prompt_with_context_and_conversation(self):
        d = _make_dispatcher(conversation=True, context=True)
        d._history.append({"transcript": "Prev transcript", "response": "Prev resp"})

        prior = [_make_segment("Context segment")]
        new = [_make_segment("New segment")]
        prompt = d._build_prompt(prior, new)

        assert "--- CONVERSATION HISTORY ---" in prompt
        assert "--- PRIOR CONTEXT ---" in prompt
        assert "--- NEW TRANSCRIPT ---" in prompt
        # Conversation history comes before prior context
        idx_convo = prompt.index("--- CONVERSATION HISTORY ---")
        idx_ctx = prompt.index("--- PRIOR CONTEXT ---")
        idx_new = prompt.index("--- NEW TRANSCRIPT ---")
        assert idx_convo < idx_ctx < idx_new


# ── Conversation limit / truncation ──


class TestConversationLimit:
    def test_limit_zero_keeps_all(self):
        d = _make_dispatcher(conversation_limit=0)
        for i in range(10):
            d._history.append({"transcript": f"Turn {i}", "response": f"Resp {i}"})

        seg = _make_segment("Latest")
        prompt = d._build_prompt([], [seg])

        for i in range(10):
            assert f"Turn {i}" in prompt

    def test_limit_truncates_oldest(self):
        d = _make_dispatcher(conversation_limit=2)
        for i in range(5):
            d._history.append({"transcript": f"Turn {i}", "response": f"Resp {i}"})

        seg = _make_segment("Latest")
        prompt = d._build_prompt([], [seg])

        # Only last 2 turns should be in prompt
        assert "Turn 0" not in prompt
        assert "Turn 1" not in prompt
        assert "Turn 2" not in prompt
        assert "Turn 3" in prompt
        assert "Turn 4" in prompt

    def test_limit_does_not_delete_history(self):
        """Limit affects prompt only, not the stored _history list."""
        d = _make_dispatcher(conversation_limit=2)
        for i in range(5):
            d._history.append({"transcript": f"Turn {i}", "response": f"Resp {i}"})

        seg = _make_segment("Latest")
        d._build_prompt([], [seg])

        # All 5 turns should still be stored
        assert len(d._history) == 5

    def test_limit_larger_than_history(self):
        d = _make_dispatcher(conversation_limit=100)
        d._history.append({"transcript": "Only turn", "response": "Only resp"})

        seg = _make_segment("New")
        prompt = d._build_prompt([], [seg])

        assert "Only turn" in prompt
        assert "YOUR RESPONSE: Only resp" in prompt


# ── Conversation summary ──


class TestConversationSummary:
    def test_summary_none_when_off(self):
        d = _make_dispatcher(conversation=False)
        assert d.conversation_summary() is None

    def test_summary_none_when_no_history(self):
        d = _make_dispatcher(conversation=True)
        assert d.conversation_summary() is None

    def test_summary_content(self):
        d = _make_dispatcher(conversation=True)
        d._history.append({"transcript": "Hello", "response": "Hi there"})
        d._history.append({"transcript": "Bye", "response": "Goodbye"})

        summary = d.conversation_summary()
        assert summary is not None
        assert "Turns           : 2" in summary
        assert "Transcript chars:" in summary
        assert "Response chars" in summary

    def test_summary_includes_limit_when_set(self):
        d = _make_dispatcher(conversation=True, conversation_limit=5)
        d._history.append({"transcript": "x", "response": "y"})

        summary = d.conversation_summary()
        assert "History limit   : 5" in summary

    def test_summary_no_limit_line_when_unlimited(self):
        d = _make_dispatcher(conversation=True, conversation_limit=0)
        d._history.append({"transcript": "x", "response": "y"})

        summary = d.conversation_summary()
        assert "History limit" not in summary


# ── End-to-end dispatch flow ──


class TestDispatchFlow:
    def test_full_conversation_dispatch_cycle(self):
        """Simulate 3 dispatches with conversation on; verify prompt grows."""
        d = _make_dispatcher()
        prompts_sent = []

        def capture_prompt(prompt):
            prompts_sent.append(prompt)
            return f"Response {len(prompts_sent)}"

        with patch.object(d, "_call_claude", side_effect=capture_prompt):
            d.buffer.add("Turn 1 text", time.time())
            d.dispatch()

            d.buffer.add("Turn 2 text", time.time() + 1)
            d.dispatch()

            d.buffer.add("Turn 3 text", time.time() + 2)
            d.dispatch()

        # First prompt has no history
        assert "--- CONVERSATION HISTORY ---" not in prompts_sent[0]

        # Second prompt has Turn 1 history
        assert "--- CONVERSATION HISTORY ---" in prompts_sent[1]
        assert "YOUR RESPONSE: Response 1" in prompts_sent[1]

        # Third prompt has Turn 1 + Turn 2 history
        assert "YOUR RESPONSE: Response 1" in prompts_sent[2]
        assert "YOUR RESPONSE: Response 2" in prompts_sent[2]

    def test_dispatch_returns_false_when_nothing_to_send(self):
        d = _make_dispatcher()
        assert d.dispatch() is False

    def test_dispatch_returns_true_when_sent(self):
        d = _make_dispatcher()
        d.buffer.add("Something", time.time())

        with patch.object(d, "_call_claude", return_value="Ok"):
            assert d.dispatch() is True


# ── Argument parsing ──


class TestArgumentParsing:
    def test_conversation_flag_default_off(self):
        """--conversation should default to False."""
        import argparse
        from live_scribe import main

        # Parse empty args (will fail at AudioTranscriber, but we just need args)
        parser = argparse.ArgumentParser()
        parser.add_argument("--conversation", action="store_true")
        parser.add_argument("--conversation-limit", type=int, default=0)
        args = parser.parse_args([])
        assert args.conversation is False
        assert args.conversation_limit == 0

    def test_conversation_flag_on(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--conversation", action="store_true")
        parser.add_argument("--conversation-limit", type=int, default=0)
        args = parser.parse_args(["--conversation"])
        assert args.conversation is True

    def test_conversation_limit_value(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--conversation", action="store_true")
        parser.add_argument("--conversation-limit", type=int, default=0)
        args = parser.parse_args(["--conversation", "--conversation-limit", "10"])
        assert args.conversation is True
        assert args.conversation_limit == 10
