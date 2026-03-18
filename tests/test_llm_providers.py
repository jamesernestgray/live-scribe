"""Tests for the multi-LLM provider system."""

import json
from unittest.mock import MagicMock, patch

import pytest

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
from live_scribe import build_parser


# -- Factory / registry tests --


class TestProviderFactory:
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
        assert set(PROVIDERS.keys()) == expected

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider("does-not-exist")

    def test_factory_creates_claude_cli(self):
        provider = create_provider("claude-cli")
        assert isinstance(provider, ClaudeCLIProvider)

    def test_factory_creates_ollama(self):
        provider = create_provider("ollama", model="mistral")
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "mistral"

    def test_factory_creates_codex_cli(self):
        provider = create_provider("codex-cli")
        assert isinstance(provider, CodexCLIProvider)

    def test_factory_creates_gemini_cli(self):
        provider = create_provider("gemini-cli")
        assert isinstance(provider, GeminiCLIProvider)


# -- ClaudeCLIProvider tests --


class TestClaudeCLIProvider:
    def test_name_without_model(self):
        p = ClaudeCLIProvider()
        assert p.name == "Claude CLI"

    def test_name_with_model(self):
        p = ClaudeCLIProvider(model="opus")
        assert p.name == "Claude CLI (opus)"

    @patch("llm_providers.subprocess.Popen")
    def test_send_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("  Hello world  ", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider()
        result = p.send("hi")
        assert result == "Hello world"
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd == ["claude", "-p", "-"]
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
        assert cmd == ["claude", "-p", "-", "--model", "sonnet"]

    @patch("llm_providers.subprocess.Popen")
    def test_send_failure_returns_none(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "error msg")
        mock_proc.returncode = 1
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider()
        result = p.send("hi")
        assert result is None

    @patch("llm_providers.subprocess.Popen", side_effect=FileNotFoundError)
    def test_send_missing_binary(self, mock_popen):
        p = ClaudeCLIProvider()
        result = p.send("hi")
        assert result is None

    @patch("llm_providers.subprocess.Popen")
    def test_send_timeout(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = __import__("subprocess").TimeoutExpired(cmd="claude", timeout=10)
        mock_popen.return_value = mock_proc
        p = ClaudeCLIProvider(timeout=10)
        result = p.send("hi")
        assert result is None
        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called_once()


# -- CodexCLIProvider tests --


class TestCodexCLIProvider:
    @patch("llm_providers.subprocess.Popen")
    def test_send_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("codex output", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = CodexCLIProvider()
        result = p.send("hi")
        assert result == "codex output"
        cmd = mock_popen.call_args[0][0]
        assert cmd == ["codex", "--quiet", "-"]

    def test_name(self):
        p = CodexCLIProvider(model="o3")
        assert p.name == "Codex CLI (o3)"


# -- GeminiCLIProvider tests --


class TestGeminiCLIProvider:
    @patch("llm_providers.subprocess.Popen")
    def test_send_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("gemini output", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        p = GeminiCLIProvider()
        result = p.send("hi")
        assert result == "gemini output"
        cmd = mock_popen.call_args[0][0]
        assert cmd == ["gemini", "-p", "-"]

    def test_name(self):
        p = GeminiCLIProvider(model="2.5-pro")
        assert p.name == "Gemini CLI (2.5-pro)"


# -- AnthropicAPIProvider tests --


class TestAnthropicAPIProvider:
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="pip install anthropic"):
                AnthropicAPIProvider()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False)
    def test_missing_api_key(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_mod}):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicAPIProvider()

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

        assert result == "Hello from Claude"
        mock_client.messages.create.assert_called_once()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False)
    def test_name(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_mod}):
            p = AnthropicAPIProvider(model="claude-opus-4-20250514")
        assert p.name == "Anthropic API (claude-opus-4-20250514)"


# -- OpenAIAPIProvider tests --


class TestOpenAIAPIProvider:
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="pip install openai"):
                OpenAIAPIProvider()

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
    def test_missing_api_key(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_mod}):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIAPIProvider()

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

        assert result == "Hello from OpenAI"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_name(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"openai": mock_mod}):
            p = OpenAIAPIProvider()
        assert p.name == "OpenAI API (gpt-4o)"


# -- GeminiAPIProvider tests --


class TestGeminiAPIProvider:
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"google": None, "google.generativeai": None}):
            with pytest.raises(ImportError, match="pip install google-generativeai"):
                GeminiAPIProvider()

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False)
    def test_missing_api_key(self):
        mock_google = MagicMock()
        mock_genai = MagicMock()
        with patch.dict("sys.modules", {
            "google": mock_google,
            "google.generativeai": mock_genai,
        }):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiAPIProvider()


# -- LiteLLMProvider tests --


class TestLiteLLMProvider:
    def test_missing_sdk(self):
        with patch.dict("sys.modules", {"litellm": None}):
            with pytest.raises(ImportError, match="pip install litellm"):
                LiteLLMProvider()

    def test_send_success(self):
        mock_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Hello from LiteLLM"
        mock_mod.completion.return_value = mock_resp

        with patch.dict("sys.modules", {"litellm": mock_mod}):
            p = LiteLLMProvider(model="gpt-4o")
            result = p.send("hi")

        assert result == "Hello from LiteLLM"

    def test_name(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"litellm": mock_mod}):
            p = LiteLLMProvider(model="claude-3-opus")
        assert p.name == "LiteLLM (claude-3-opus)"


# -- OllamaProvider tests --


class TestOllamaProvider:
    def test_name(self):
        p = OllamaProvider(model="codellama")
        assert p.name == "Ollama (codellama)"

    def test_default_model(self):
        p = OllamaProvider()
        assert p.model == "llama3"

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

        assert result == "Hello from Ollama"
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert "/api/generate" in req.full_url
        sent_data = json.loads(req.data.decode())
        assert sent_data["model"] == "llama3"
        assert sent_data["stream"] is False

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

        assert chunks == ["Hello", " world"]

    @patch(
        "llm_providers.urllib.request.urlopen",
        side_effect=__import__("urllib.error", fromlist=["URLError"]).URLError("Connection refused"),
    )
    def test_send_connection_error(self, mock_urlopen):
        p = OllamaProvider()
        result = p.send("hi")
        assert result is None


# -- CLI argument tests --


class TestCLIArgs:
    """Test --llm, --llm-model, and --claude-model backward compat in arg parsing."""

    def _parse(self, *cli_args):
        """Build the arg parser via build_parser() and parse given args."""
        parser = build_parser()
        return parser.parse_args(list(cli_args))

    def test_default_llm(self):
        args = self._parse()
        assert args.llm == "claude-cli"
        assert args.llm_model is None

    def test_llm_openai(self):
        args = self._parse("--llm", "openai", "--llm-model", "gpt-4o")
        assert args.llm == "openai"
        assert args.llm_model == "gpt-4o"

    def test_llm_ollama(self):
        args = self._parse("--llm", "ollama", "--llm-model", "mistral")
        assert args.llm == "ollama"
        assert args.llm_model == "mistral"

    def test_claude_model_backward_compat(self):
        args = self._parse("--claude-model", "opus")
        assert args.claude_model == "opus"
        # In main(), claude_model falls back to llm_model when llm_model is None
        assert args.llm_model is None

    def test_invalid_llm_rejected(self):
        with pytest.raises(SystemExit):
            self._parse("--llm", "not-a-provider")

    def test_all_provider_choices_accepted(self):
        for name in PROVIDERS:
            args = self._parse("--llm", name)
            assert args.llm == name


# ── Stdin-based CLI provider tests ────────────────────────────────────────


class TestCLIProvidersUseStdin:
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
        assert "long prompt here" not in cmd
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
        assert "long prompt here" not in cmd
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
        assert "long prompt here" not in cmd
        mock_proc.communicate.assert_called_once_with(input="long prompt here", timeout=120)


class TestCLIStreamingCleanup:
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


class TestOllamaTimeout:
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
        assert call_kwargs.kwargs.get("timeout") == 60

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
        assert call_kwargs.kwargs.get("timeout") == 60


class TestGeminiDefaultModel:
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
        assert p.model == "gemini-2.0-flash"


class TestDispatchLock:
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
        assert isinstance(d._dispatch_lock, threading.Lock)
