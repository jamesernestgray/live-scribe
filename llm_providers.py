"""
Multi-LLM provider system for live-scribe.

Supports multiple LLM backends via a unified interface:
  - claude-cli:  Claude CLI subprocess (default, no extra deps)
  - anthropic:   Anthropic Python SDK
  - openai:      OpenAI Python SDK
  - codex-cli:   Codex CLI subprocess
  - gemini:      Google Generative AI SDK
  - gemini-cli:  Gemini CLI subprocess
  - ollama:      Ollama local server via HTTP (no extra deps)
  - litellm:     LiteLLM universal proxy SDK
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Generator


class LLMProvider(ABC):
    """Base class for all LLM providers."""

    @abstractmethod
    def send(self, prompt: str) -> str | None:
        """Send a prompt and return the full response (blocking)."""
        ...

    @abstractmethod
    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        """Send a prompt and yield response chunks as they arrive."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...


# ---------------------------------------------------------------------------
# 1. Claude CLI (default — current behavior)
# ---------------------------------------------------------------------------

class ClaudeCLIProvider(LLMProvider):
    """Invokes the `claude` CLI as a subprocess."""

    def __init__(self, model: str | None = None, timeout: int = 120, **kwargs):
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        label = "Claude CLI"
        if self.model:
            label += f" ({self.model})"
        return label

    def send(self, prompt: str) -> str | None:
        cmd = ["claude", "-p", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            if r.returncode == 0:
                return r.stdout.strip()
            import sys
            print(f"  ⚠ claude exited {r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            import sys
            print("  ⚠ claude timed out", file=sys.stderr)
        except FileNotFoundError:
            import sys
            print("  ⚠ 'claude' not found in PATH", file=sys.stderr)
        return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        cmd = ["claude", "-p", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for line in proc.stdout:
                yield line
            proc.wait()
        except FileNotFoundError:
            import sys
            print("  ⚠ 'claude' not found in PATH", file=sys.stderr)


# ---------------------------------------------------------------------------
# 2. Anthropic API
# ---------------------------------------------------------------------------

class AnthropicAPIProvider(LLMProvider):
    """Uses the official `anthropic` Python SDK."""

    def __init__(self, model: str | None = None, **kwargs):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            raise ImportError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Set ANTHROPIC_API_KEY environment variable")
        self.model = model or "claude-sonnet-4-20250514"
        self._client = anthropic.Anthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return f"Anthropic API ({self.model})"

    def send(self, prompt: str) -> str | None:
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as exc:
            import sys
            print(f"  ⚠ Anthropic API error: {exc}", file=sys.stderr)
            return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as exc:
            import sys
            print(f"  ⚠ Anthropic API streaming error: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 3. OpenAI API
# ---------------------------------------------------------------------------

class OpenAIAPIProvider(LLMProvider):
    """Uses the official `openai` Python SDK."""

    def __init__(self, model: str | None = None, **kwargs):
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ImportError(
                "OpenAI SDK not installed. Run: pip install openai"
            )
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Set OPENAI_API_KEY environment variable")
        self.model = model or "gpt-4o"
        self._client = openai.OpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return f"OpenAI API ({self.model})"

    def send(self, prompt: str) -> str | None:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as exc:
            import sys
            print(f"  ⚠ OpenAI API error: {exc}", file=sys.stderr)
            return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as exc:
            import sys
            print(f"  ⚠ OpenAI API streaming error: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 4. Codex CLI
# ---------------------------------------------------------------------------

class CodexCLIProvider(LLMProvider):
    """Invokes the `codex` CLI as a subprocess (headless mode)."""

    def __init__(self, model: str | None = None, timeout: int = 120, **kwargs):
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        label = "Codex CLI"
        if self.model:
            label += f" ({self.model})"
        return label

    def send(self, prompt: str) -> str | None:
        cmd = ["codex", "--quiet", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            if r.returncode == 0:
                return r.stdout.strip()
            import sys
            print(f"  ⚠ codex exited {r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            import sys
            print("  ⚠ codex timed out", file=sys.stderr)
        except FileNotFoundError:
            import sys
            print("  ⚠ 'codex' not found in PATH", file=sys.stderr)
        return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        cmd = ["codex", "--quiet", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for line in proc.stdout:
                yield line
            proc.wait()
        except FileNotFoundError:
            import sys
            print("  ⚠ 'codex' not found in PATH", file=sys.stderr)


# ---------------------------------------------------------------------------
# 5. Gemini API (Google Generative AI SDK)
# ---------------------------------------------------------------------------

class GeminiAPIProvider(LLMProvider):
    """Uses the `google-generativeai` Python SDK."""

    def __init__(self, model: str | None = None, **kwargs):
        try:
            import google.generativeai as genai  # noqa: F401
        except ImportError:
            raise ImportError(
                "Google Generative AI SDK not installed. Run: pip install google-generativeai"
            )
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Set GEMINI_API_KEY environment variable")
        genai.configure(api_key=api_key)
        self.model = model or "gemini-pro"
        self._genai = genai
        self._model = genai.GenerativeModel(self.model)

    @property
    def name(self) -> str:
        return f"Gemini API ({self.model})"

    def send(self, prompt: str) -> str | None:
        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as exc:
            import sys
            print(f"  ⚠ Gemini API error: {exc}", file=sys.stderr)
            return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        try:
            response = self._model.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            import sys
            print(f"  ⚠ Gemini API streaming error: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 6. Gemini CLI
# ---------------------------------------------------------------------------

class GeminiCLIProvider(LLMProvider):
    """Invokes the `gemini` CLI as a subprocess (headless mode)."""

    def __init__(self, model: str | None = None, timeout: int = 120, **kwargs):
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        label = "Gemini CLI"
        if self.model:
            label += f" ({self.model})"
        return label

    def send(self, prompt: str) -> str | None:
        cmd = ["gemini", "-p", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            if r.returncode == 0:
                return r.stdout.strip()
            import sys
            print(f"  ⚠ gemini exited {r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            import sys
            print("  ⚠ gemini timed out", file=sys.stderr)
        except FileNotFoundError:
            import sys
            print("  ⚠ 'gemini' not found in PATH", file=sys.stderr)
        return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        cmd = ["gemini", "-p", prompt]
        if self.model:
            cmd.extend(["--model", self.model])
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for line in proc.stdout:
                yield line
            proc.wait()
        except FileNotFoundError:
            import sys
            print("  ⚠ 'gemini' not found in PATH", file=sys.stderr)


# ---------------------------------------------------------------------------
# 7. Ollama (local HTTP, no extra deps)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """Talks to a local Ollama server via HTTP (no extra dependencies)."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str = "http://localhost:11434",
        **kwargs,
    ):
        self.model = model or "llama3"
        self.base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"

    def send(self, prompt: str) -> str | None:
        url = f"{self.base_url}/api/generate"
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode())
                return body.get("response")
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            import sys
            print(f"  ⚠ Ollama error: {exc}", file=sys.stderr)
            return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        url = f"{self.base_url}/api/generate"
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                for line in resp:
                    if line.strip():
                        chunk = json.loads(line.decode())
                        token = chunk.get("response", "")
                        if token:
                            yield token
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            import sys
            print(f"  ⚠ Ollama streaming error: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 8. LiteLLM (universal fallback)
# ---------------------------------------------------------------------------

class LiteLLMProvider(LLMProvider):
    """Uses the `litellm` SDK as a universal proxy to many LLM providers."""

    def __init__(self, model: str | None = None, **kwargs):
        try:
            import litellm  # noqa: F401
        except ImportError:
            raise ImportError(
                "LiteLLM SDK not installed. Run: pip install litellm"
            )
        self.model = model or "gpt-4o"
        self._litellm = litellm

    @property
    def name(self) -> str:
        return f"LiteLLM ({self.model})"

    def send(self, prompt: str) -> str | None:
        try:
            response = self._litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as exc:
            import sys
            print(f"  ⚠ LiteLLM error: {exc}", file=sys.stderr)
            return None

    def send_streaming(self, prompt: str) -> Generator[str, None, None]:
        try:
            response = self._litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as exc:
            import sys
            print(f"  ⚠ LiteLLM streaming error: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Provider registry & factory
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude-cli": ClaudeCLIProvider,
    "anthropic": AnthropicAPIProvider,
    "openai": OpenAIAPIProvider,
    "codex-cli": CodexCLIProvider,
    "gemini": GeminiAPIProvider,
    "gemini-cli": GeminiCLIProvider,
    "ollama": OllamaProvider,
    "litellm": LiteLLMProvider,
}


def create_provider(name: str, model: str | None = None, **kwargs) -> LLMProvider:
    """Instantiate an LLM provider by registry name.

    Args:
        name: Key from PROVIDERS dict (e.g. "claude-cli", "openai").
        model: Optional model name passed to the provider constructor.
        **kwargs: Extra keyword arguments forwarded to the provider.

    Returns:
        An initialised LLMProvider instance.

    Raises:
        ValueError: If *name* is not in the registry.
    """
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {name}. Available: {list(PROVIDERS.keys())}"
        )
    return PROVIDERS[name](model=model, **kwargs)
