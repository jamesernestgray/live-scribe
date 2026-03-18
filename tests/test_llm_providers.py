"""Tests for the multi-LLM provider system."""

import io
import json
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure project root is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from llm_providers import (
    PROVIDERS,
    AnthropicAPIProvider,
    ClaudeCLIProvider,
    CodexCLIProvider,
    GeminiAPIProvider,
    GeminiCLIProvider,
    LiteLLMProvider,
    OllamaProvider,
    OpenAIAPIProvider,
    create_provider,
)


# ── Factory / registry tests ──────────────────────────────────────────────


class TestProviderFactory(unittest.TestCase):
    """Tests for create_provider and the PROVIDERS registry."""

    def test_all_provider_names_registered(self):
        expected = {
            "claude-cli",
            "anthropic",
            "openai",
            "codex-cli",
            "gemini",
            "gemini-cli",
            "ollama",
            "litellm",
        }
        self.assertEqual(set(PROVIDERS.keys()), expected)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_provider("does-not-exist")
        self.assertIn("Unknown provider", str(ctx.exception))
        self.assertIn("does-not-exist", str(ctx.exception))

    def test_factory_creates_claude_cli(self):
        provider = create_provider("claude-cli")
        self.assertIsInstance(provider, ClaudeCLIProvider)

    def test_factory_creates_ollama(self):
        provider = create_provider("ollama", model="mistral")
        self.assertIsInstance(provider, OllamaProvider)
        self.assertEqual(provider.model, "mistral")

    def test_factory_creates_codex_cli(self):
        provider = create_provider("codex-cli")
        self.assertIsInstance(provider, CodexCLIProvider)

    def test_factory_creates_gemini_cli(self):
        provider = create_provider("gemini-cli")
        self.assertIsInstance(provider, GeminiCLIProvider)


# ── ClaudeCLIProvider tests ───────────────────────────────────────────────


class TestClaudeCLIProvider(unittest.TestCase):
    def test_name_without_model(self):
        p = ClaudeCLIProvider()
        self.assertEqual(p.name, "Claude CLI")

    def test_name_with_model(self):
        p = ClaudeCLIProvider(model="opus")
        self.assertEqual(p.name, "Claude CLI (opus)")

    @patch("llm_providers.subprocess.Popen")
    def test_send_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("  Hello world  ", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider()
        result = p.send("hi")
        self.assertEqual(result, "Hello world")
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd, ["claude", "-p", "-"])
        mock_proc.communicate.assert_called_once_with(input="hi", timeout=120)

    @patch("llm_providers.subprocess.Popen")
    def test_send_with_model(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("ok", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider(model="sonnet")
        p.send("hi")
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd, ["claude", "-p", "-", "--model", "sonnet"])

    @patch("llm_providers.subprocess.Popen")
    def test_send_failure_returns_none(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "error msg")
        mock_proc.returncode = 1
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider()
        result = p.send("hi")
        self.assertIsNone(result)

    @patch("llm_providers.subprocess.Popen", side_effect=FileNotFoundError)
    def test_send_missing_binary(self, mock_popen):
        p = ClaudeCLIProvider()
        result = p.send("hi")
        self.assertIsNone(result)

    @patch("llm_providers.subprocess.Popen")
    def test_send_timeout(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = __import__("subprocess").TimeoutExpired(cmd="claude", timeout=10)
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider(timeout=10)
        result = p.send("hi")
        self.assertIsNone(result)
        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called_once()


# ── CodexCLIProvider tests ────────────────────────────────────────────────


class TestCodexCLIProvider(unittest.TestCase):
    @patch("llm_providers.subprocess.Popen")
    def test_send_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("codex output", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = CodexCLIProvider()
        result = p.send("hi")
        self.assertEqual(result, "codex output")
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd, ["codex", "--quiet", "-"])

    def test_name(self):
        p = CodexCLIProvider(model="o3")
        self.assertEqual(p.name, "Codex CLI (o3)")


# ── GeminiCLIProvider tests ───────────────────────────────────────────────


class TestGeminiCLIProvider(unittest.TestCase):
    @patch("llm_providers.subprocess.Popen")
    def test_send_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("gemini output", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = GeminiCLIProvider()
        result = p.send("hi")
        self.assertEqual(result, "gemini output")
        cmd = mock_popen.call_args[0][0]
        self.assertEqual(cmd, ["gemini", "-p", "-"])

    def test_name(self):
        p = GeminiCLIProvider(model="2.5-pro")
        self.assertEqual(p.name, "Gemini CLI (2.5-pro)")


# ── AnthropicAPIProvider tests ────────────────────────────────────────────


class TestAnthropicAPIProvider(unittest.TestCase):
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"anthropic": None}):
            with self.assertRaises(ImportError) as ctx:
                AnthropicAPIProvider()
            self.assertIn("pip install anthropic", str(ctx.exception))

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_missing_api_key(self):
        # Provide a real-ish module mock so the import succeeds
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_mod}):
            with self.assertRaises(ValueError) as ctx:
                AnthropicAPIProvider()
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False)
    def test_send_success(self):
        mock_mod = MagicMock()
        mock_client = MagicMock()
        mock_mod.Anthropic.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Hello from Claude")]
        mock_client.messages.create.return_value = mock_message

        with patch.dict("sys.modules", {"anthropic": mock_mod}):
            p = AnthropicAPIProvider(model="claude-sonnet-4-20250514")
            result = p.send("hi")

        self.assertEqual(result, "Hello from Claude")
        mock_client.messages.create.assert_called_once()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False)
    def test_name(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_mod}):
            p = AnthropicAPIProvider(model="claude-opus-4-20250514")
        self.assertEqual(p.name, "Anthropic API (claude-opus-4-20250514)")


# ── OpenAIAPIProvider tests ──────────────────────────────────────────────


class TestOpenAIAPIProvider(unittest.TestCase):
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"openai": None}):
            with self.assertRaises(ImportError) as ctx:
                OpenAIAPIProvider()
            self.assertIn("pip install openai", str(ctx.exception))

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
    def test_missing_api_key(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_mod}):
            with self.assertRaises(ValueError) as ctx:
                OpenAIAPIProvider()
            self.assertIn("OPENAI_API_KEY", str(ctx.exception))

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_send_success(self):
        mock_mod = MagicMock()
        mock_client = MagicMock()
        mock_mod.OpenAI.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Hello from OpenAI"
        mock_client.chat.completions.create.return_value = mock_resp

        with patch.dict("sys.modules", {"openai": mock_mod}):
            p = OpenAIAPIProvider(model="gpt-4o")
            result = p.send("hi")

        self.assertEqual(result, "Hello from OpenAI")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_name(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_mod}):
            p = OpenAIAPIProvider()
        self.assertEqual(p.name, "OpenAI API (gpt-4o)")


# ── GeminiAPIProvider tests ──────────────────────────────────────────────


class TestGeminiAPIProvider(unittest.TestCase):
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"google": None, "google.generativeai": None}):
            with self.assertRaises(ImportError) as ctx:
                GeminiAPIProvider()
            self.assertIn("pip install google-generativeai", str(ctx.exception))

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False)
    def test_missing_api_key(self):
        mock_google = MagicMock()
        mock_genai = MagicMock()
        with patch.dict("sys.modules", {
            "google": mock_google,
            "google.generativeai": mock_genai,
        }):
            with self.assertRaises(ValueError) as ctx:
                GeminiAPIProvider()
            self.assertIn("GEMINI_API_KEY", str(ctx.exception))


# ── LiteLLMProvider tests ────────────────────────────────────────────────


class TestLiteLLMProvider(unittest.TestCase):
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"litellm": None}):
            with self.assertRaises(ImportError) as ctx:
                LiteLLMProvider()
            self.assertIn("pip install litellm", str(ctx.exception))

    def test_send_success(self):
        mock_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Hello from LiteLLM"
        mock_mod.completion.return_value = mock_resp

        with patch.dict("sys.modules", {"litellm": mock_mod}):
            p = LiteLLMProvider(model="gpt-4o")
            result = p.send("hi")

        self.assertEqual(result, "Hello from LiteLLM")

    def test_name(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"litellm": mock_mod}):
            p = LiteLLMProvider(model="claude-3-opus")
        self.assertEqual(p.name, "LiteLLM (claude-3-opus)")


# ── OllamaProvider tests ─────────────────────────────────────────────────


class TestOllamaProvider(unittest.TestCase):
    def test_name(self):
        p = OllamaProvider(model="codellama")
        self.assertEqual(p.name, "Ollama (codellama)")

    def test_default_model(self):
        p = OllamaProvider()
        self.assertEqual(p.model, "llama3")

    @patch("llm_providers.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        body = json.dumps({"response": "Hello from Ollama"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        p = OllamaProvider(model="llama3")
        result = p.send("hi")

        self.assertEqual(result, "Hello from Ollama")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/api/generate", req.full_url)
        sent_data = json.loads(req.data.decode())
        self.assertEqual(sent_data["model"], "llama3")
        self.assertFalse(sent_data["stream"])

    @patch("llm_providers.urllib.request.urlopen")
    def test_send_streaming(self, mock_urlopen):
        lines = [
            json.dumps({"response": "Hello"}).encode() + b"\n",
            json.dumps({"response": " world"}).encode() + b"\n",
            json.dumps({"response": "", "done": True}).encode() + b"\n",
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = lambda s: iter(lines)
        mock_urlopen.return_value = mock_resp

        p = OllamaProvider(model="llama3")
        chunks = list(p.send_streaming("hi"))

        self.assertEqual(chunks, ["Hello", " world"])

    @patch("llm_providers.urllib.request.urlopen", side_effect=__import__("urllib.error", fromlist=["URLError"]).URLError("Connection refused"))
    def test_send_connection_error(self, mock_urlopen):
        p = OllamaProvider()
        result = p.send("hi")
        self.assertIsNone(result)


# ── CLI argument tests ───────────────────────────────────────────────────


class TestCLIArgs(unittest.TestCase):
    """Test --llm, --llm-model, and --claude-model backward compat in arg parsing."""

    def _parse(self, *cli_args):
        """Build the arg parser from main() and parse given args."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--llm", default="claude-cli", choices=list(PROVIDERS.keys()))
        parser.add_argument("--llm-model", default=None)
        parser.add_argument("--claude-model", default=None)
        return parser.parse_args(list(cli_args))

    def test_default_llm(self):
        args = self._parse()
        self.assertEqual(args.llm, "claude-cli")
        self.assertIsNone(args.llm_model)

    def test_llm_openai(self):
        args = self._parse("--llm", "openai", "--llm-model", "gpt-4o")
        self.assertEqual(args.llm, "openai")
        self.assertEqual(args.llm_model, "gpt-4o")

    def test_llm_ollama(self):
        args = self._parse("--llm", "ollama", "--llm-model", "mistral")
        self.assertEqual(args.llm, "ollama")
        self.assertEqual(args.llm_model, "mistral")

    def test_claude_model_backward_compat(self):
        args = self._parse("--claude-model", "opus")
        self.assertEqual(args.claude_model, "opus")
        # In main(), claude_model falls back to llm_model when llm_model is None
        self.assertIsNone(args.llm_model)

    def test_invalid_llm_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("--llm", "not-a-provider")

    def test_all_provider_choices_accepted(self):
        for name in PROVIDERS:
            args = self._parse("--llm", name)
            self.assertEqual(args.llm, name)


# ── Stdin-based CLI provider tests ────────────────────────────────────────


class TestCLIProvidersUseStdin(unittest.TestCase):
    """Verify all CLI providers pipe prompt via stdin, not as a CLI argument."""

    @patch("llm_providers.subprocess.Popen")
    def test_claude_cli_sends_prompt_via_stdin(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("response", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        p = ClaudeCLIProvider()
        p.send("long prompt here")

        # Prompt should NOT be in the command list
        cmd = mock_popen.call_args[0][0]
        self.assertNotIn("long prompt here", cmd)
        # Prompt should be passed via stdin
        mock_proc.communicate.assert_called_once_with(input="long prompt here", timeout=120)

    @patch("llm_providers.subprocess.Popen")
    def test_codex_cli_sends_prompt_via_stdin(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("response", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        p = CodexCLIProvider()
        p.send("long prompt here")

        cmd = mock_popen.call_args[0][0]
        self.assertNotIn("long prompt here", cmd)
        mock_proc.communicate.assert_called_once_with(input="long prompt here", timeout=120)

    @patch("llm_providers.subprocess.Popen")
    def test_gemini_cli_sends_prompt_via_stdin(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("response", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        p = GeminiCLIProvider()
        p.send("long prompt here")

        cmd = mock_popen.call_args[0][0]
        self.assertNotIn("long prompt here", cmd)
        mock_proc.communicate.assert_called_once_with(input="long prompt here", timeout=120)


class TestCLIStreamingCleanup(unittest.TestCase):
    """Verify streaming generators clean up subprocesses properly."""

    @patch("llm_providers.subprocess.Popen")
    def test_claude_streaming_cleanup_on_abandon(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        p = ClaudeCLIProvider()
        gen = p.send_streaming("test prompt")
        next(gen)  # consume first line
        gen.close()  # abandon the generator

        # Process should be killed
        mock_proc.kill.assert_called()

    @patch("llm_providers.subprocess.Popen")
    def test_codex_streaming_cleanup_on_abandon(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        p = CodexCLIProvider()
        gen = p.send_streaming("test prompt")
        next(gen)
        gen.close()

        mock_proc.kill.assert_called()

    @patch("llm_providers.subprocess.Popen")
    def test_gemini_streaming_cleanup_on_abandon(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        p = GeminiCLIProvider()
        gen = p.send_streaming("test prompt")
        next(gen)
        gen.close()

        mock_proc.kill.assert_called()

    @patch("llm_providers.subprocess.Popen")
    def test_streaming_no_kill_when_process_exited(self, mock_popen):
        """If process already exited, kill should not be called."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = iter(["line1\n"])
        mock_proc.poll.return_value = 0  # already exited
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        p = ClaudeCLIProvider()
        list(p.send_streaming("test"))  # fully consume

        mock_proc.kill.assert_not_called()


class TestOllamaTimeout(unittest.TestCase):
    """Verify Ollama urlopen calls include a timeout."""

    @patch("llm_providers.urllib.request.urlopen")
    def test_send_includes_timeout(self, mock_urlopen):
        body = json.dumps({"response": "ok"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        p = OllamaProvider()
        p.send("hi")

        # urlopen should be called with timeout=60
        call_kwargs = mock_urlopen.call_args
        self.assertEqual(call_kwargs.kwargs.get("timeout"), 60)

    @patch("llm_providers.urllib.request.urlopen")
    def test_send_streaming_includes_timeout(self, mock_urlopen):
        lines = [json.dumps({"response": "ok"}).encode() + b"\n"]
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = lambda s: iter(lines)
        mock_urlopen.return_value = mock_resp

        p = OllamaProvider()
        list(p.send_streaming("hi"))

        call_kwargs = mock_urlopen.call_args
        self.assertEqual(call_kwargs.kwargs.get("timeout"), 60)


class TestGeminiDefaultModel(unittest.TestCase):
    """Verify Gemini API uses updated default model."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False)
    def test_default_model_is_gemini_2_flash(self):
        mock_google = MagicMock()
        mock_genai = MagicMock()
        with patch.dict("sys.modules", {
            "google": mock_google,
            "google.generativeai": mock_genai,
        }):
            p = GeminiAPIProvider()
        self.assertEqual(p.model, "gemini-2.0-flash")


class TestDispatchLock(unittest.TestCase):
    """Verify LLMDispatcher has a dispatch lock."""

    def test_dispatch_lock_exists(self):
        import sys
        import time
        sys.modules["numpy"] = MagicMock()
        sys.modules["sounddevice"] = MagicMock()
        sys.modules["faster_whisper"] = MagicMock()
        from live_scribe import LLMDispatcher, TranscriptionBuffer
        import threading

        buf = TranscriptionBuffer()
        d = LLMDispatcher(buffer=buf, system_prompt="test")
        self.assertIsInstance(d._dispatch_lock, threading.Lock)


if __name__ == "__main__":
    unittest.main()
