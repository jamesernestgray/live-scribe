#!/usr/bin/env python3
"""
live-scribe: Real-time audio transcription with periodic LLM analysis.

Captures microphone audio, transcribes locally with faster-whisper,
and periodically sends accumulated transcription to an LLM for processing.
Supports multiple LLM backends via --llm (default: claude-cli).
"""

import argparse
import platform
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from llm_providers import PROVIDERS, create_provider


def find_system_audio_device() -> tuple[int, str] | None:
    """Auto-detect a virtual audio loopback device for system audio capture.

    Scans all input-capable devices for names matching known virtual audio
    drivers (BlackHole, Soundflower, Loopback, PulseAudio monitor, etc.).

    Returns (device_index, device_name) or None if no match is found.
    """
    devices = sd.query_devices()
    keywords = ["blackhole", "soundflower", "loopback", "monitor", "stereo mix", "what u hear"]
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            name_lower = dev['name'].lower()
            if any(kw in name_lower for kw in keywords):
                return (i, dev['name'])
    return None


def get_system_audio_install_instructions() -> str:
    """Return platform-specific instructions for installing a virtual audio device."""
    system = platform.system()
    if system == "Darwin":
        return "Install BlackHole: brew install blackhole-2ch"
    elif system == "Linux":
        return "Use PulseAudio monitor: pactl list sources | grep monitor"
    elif system == "Windows":
        return "Enable Stereo Mix in Sound settings"
    else:
        return "Install a virtual audio loopback driver for your platform"


class TranscriptionBuffer:
    """Thread-safe buffer for accumulating transcription segments."""

    def __init__(self, output_file=None):
        self._segments: list[dict] = []
        self._unsent: list[dict] = []
        self._lock = threading.Lock()
        self._output_fh = None
        if output_file:
            self._output_fh = open(output_file, "a", encoding="utf-8")

    def add(self, text: str, timestamp: float, speaker: str | None = None):
        entry = {"text": text, "time": timestamp, "speaker": speaker}
        with self._lock:
            self._segments.append(entry)
            self._unsent.append(entry)
        # Streaming file write (--output): append immediately and flush
        if self._output_fh:
            ts = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            spk = f" [{speaker}]" if speaker else ""
            self._output_fh.write(f"[{ts}]{spk} {text}\n")
            self._output_fh.flush()

    def take_unsent(self) -> list[dict]:
        """Return and clear unsent segments."""
        with self._lock:
            out = list(self._unsent)
            self._unsent.clear()
            return out

    def take_with_context(self, context_limit: int = 0) -> tuple[list[dict], list[dict]]:
        """Return (prior_context, new_segments) and mark new as sent.

        context_limit: max prior segments to include (0 = unlimited).
        """
        with self._lock:
            new = list(self._unsent)
            # prior = everything that was already sent
            prior_count = len(self._segments) - len(self._unsent)
            prior = list(self._segments[:prior_count])
            if context_limit > 0:
                prior = prior[-context_limit:]
            self._unsent.clear()
            return prior, new

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._segments)

    def __len__(self):
        with self._lock:
            return len(self._segments)

    def close_output(self):
        """Close the streaming output file handle, if any."""
        if self._output_fh:
            self._output_fh.close()
            self._output_fh = None


class AudioTranscriber:
    """Captures microphone audio and transcribes with faster-whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        chunk_sec: int = 5,
        diarize: bool = False,
        language: str | None = None,
        output_file: str | None = None,
    ):
        print(f"⏳ Loading whisper model '{model_size}' on {device}…")
        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        print("✅ Model loaded.")
        self.sample_rate = 16000
        self.chunk_sec = chunk_sec
        self.diarize = diarize
        self.language = language
        self.buffer = TranscriptionBuffer(output_file=output_file)
        self._running = False
        self._audio_chunks: list[np.ndarray] = []
        self._audio_lock = threading.Lock()

        if diarize:
            import os
            import torch  # noqa: F401 — ensures torch is available
            from pyannote.audio import Pipeline

            token = os.environ.get("HF_TOKEN")
            if not token:
                print("  ⚠ HF_TOKEN not set — diarization requires it", file=sys.stderr)
                sys.exit(1)
            print("⏳ Loading speaker diarization model…")
            self._diarize_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=token,
            )
            print("✅ Diarization model loaded.")
            if self.chunk_sec < 30:
                print(f"  ℹ Chunk size raised to 30s for diarization (was {self.chunk_sec}s)")
                self.chunk_sec = 30

    # -- sounddevice callback (runs on audio thread) --
    def _on_audio(self, indata, frames, time_info, status):
        if status:
            print(f"  ⚠ audio: {status}", file=sys.stderr)
        with self._audio_lock:
            self._audio_chunks.append(indata.copy())

    def _assign_speakers(self, whisper_segments: list, audio: np.ndarray) -> list[tuple[str, str | None, float, float]]:
        """Run pyannote diarization and align speaker labels to whisper segments.

        Returns list of (text, speaker, seg_start, seg_end).
        """
        import torch

        waveform = torch.from_numpy(audio).unsqueeze(0)  # (1, samples)
        diarization = self._diarize_pipeline({
            "waveform": waveform,
            "sample_rate": self.sample_rate,
        })

        # Build a list of speaker turns for fast lookup
        turns = [
            (turn.start, turn.end, speaker)
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ]

        labeled = []
        for seg in whisper_segments:
            text = seg.text.strip()
            if not text:
                continue
            mid = (seg.start + seg.end) / 2
            speaker = None
            for t_start, t_end, spk in turns:
                if t_start <= mid <= t_end:
                    speaker = spk
                    break
            labeled.append((text, speaker, seg.start, seg.end))
        return labeled

    # -- transcription loop (runs on its own thread) --
    def _transcribe_loop(self):
        while self._running:
            time.sleep(self.chunk_sec)

            with self._audio_lock:
                if not self._audio_chunks:
                    continue
                raw = np.concatenate(self._audio_chunks)
                self._audio_chunks.clear()

            audio = raw.flatten().astype(np.float32)
            chunk_wall_start = time.time() - (len(audio) / self.sample_rate)

            transcribe_kwargs = dict(
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            if self.language:
                transcribe_kwargs["language"] = self.language
            segments, _info = self.model.transcribe(audio, **transcribe_kwargs)
            segments = list(segments)  # consume generator before diarization

            if not any(s.text.strip() for s in segments):
                continue

            if self.diarize:
                labeled = self._assign_speakers(segments, audio)
                for text, speaker, seg_start, _seg_end in labeled:
                    wall_ts = chunk_wall_start + seg_start
                    spk = speaker or "?"
                    self.buffer.add(text, wall_ts, speaker=spk)
                    pretty = datetime.fromtimestamp(wall_ts).strftime("%H:%M:%S")
                    print(f"  [{pretty}] [{spk}] {text}")
            else:
                for seg in segments:
                    text = seg.text.strip()
                    if not text:
                        continue
                    wall_ts = chunk_wall_start + seg.start
                    self.buffer.add(text, wall_ts)
                    pretty = datetime.fromtimestamp(wall_ts).strftime("%H:%M:%S")
                    print(f"  [{pretty}] {text}")

    def start(self):
        self._running = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._on_audio,
        )
        self._stream.start()
        self._thread = threading.Thread(
            target=self._transcribe_loop, daemon=True
        )
        self._thread.start()

    def transcribe_file(self, audio_path: str):
        """Transcribe an audio file instead of live microphone input.

        Processes the entire file, populates the buffer, then returns.
        """
        print(f"  Processing audio file: {audio_path}")
        transcribe_kwargs = dict(
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        if self.language:
            transcribe_kwargs["language"] = self.language

        segments, _info = self.model.transcribe(audio_path, **transcribe_kwargs)
        segments = list(segments)

        if not any(s.text.strip() for s in segments):
            print("  (no speech detected in file)")
            return

        wall_start = time.time()
        if self.diarize:
            # For diarization on a file, load audio as numpy for pyannote
            import soundfile as sf
            audio_data, sr = sf.read(audio_path, dtype="float32")
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)  # mono
            if sr != self.sample_rate:
                # Resample to 16kHz for pyannote
                import librosa
                audio_data = librosa.resample(audio_data, orig_sr=sr, target_sr=self.sample_rate)
            labeled = self._assign_speakers(segments, audio_data)
            for text, speaker, seg_start, _seg_end in labeled:
                wall_ts = wall_start + seg_start
                spk = speaker or "?"
                self.buffer.add(text, wall_ts, speaker=spk)
                pretty = datetime.fromtimestamp(wall_ts).strftime("%H:%M:%S")
                print(f"  [{pretty}] [{spk}] {text}")
        else:
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                wall_ts = wall_start + seg.start
                self.buffer.add(text, wall_ts)
                pretty = datetime.fromtimestamp(wall_ts).strftime("%H:%M:%S")
                print(f"  [{pretty}] {text}")

        print(f"  File transcription complete: {len(self.buffer)} segment(s)")

    def stop(self):
        self._running = False
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()
        self.buffer.close_output()


class LLMDispatcher:
    """Sends accumulated transcript to an LLM provider, either on a timer or on demand."""

    def __init__(
        self,
        buffer: TranscriptionBuffer,
        system_prompt: str,
        provider_name: str = "claude-cli",
        model: str | None = None,
        interval: int | None = None,
        timeout: int = 120,
        context: bool = False,
        context_limit: int = 0,
        session_log_file: str | None = None,
        stream: bool = False,
        conversation: bool = False,
        conversation_limit: int = 0,
    ):
        self.buffer = buffer
        self.system_prompt = system_prompt
        self.interval = interval  # None = manual mode
        self.context = context
        self.context_limit = context_limit
        self.stream = stream
        self.conversation = conversation
        self.conversation_limit = conversation_limit
        self._history: list[dict] = []  # {"transcript": str, "response": str}
        self._running = False
        self._dispatch_count = 0
        self._session_log_fh = None
        if session_log_file:
            self._session_log_fh = open(session_log_file, "a", encoding="utf-8")

        # Build provider kwargs — CLI providers accept a timeout
        provider_kwargs: dict = {}
        if provider_name in ("claude-cli", "codex-cli", "gemini-cli"):
            provider_kwargs["timeout"] = timeout

        self.provider = create_provider(provider_name, model=model, **provider_kwargs)

    @staticmethod
    def _format_segments(segments: list[dict]) -> str:
        lines = []
        for seg in segments:
            ts = datetime.fromtimestamp(seg["time"]).strftime("%H:%M:%S")
            spk = f" [{seg['speaker']}]" if seg.get("speaker") else ""
            lines.append(f"[{ts}]{spk} {seg['text']}")
        return "\n".join(lines)

    def _build_prompt(self, prior: list[dict], new: list[dict]) -> str:
        parts = [self.system_prompt, ""]

        if self.conversation and self._history:
            history = self._history
            if self.conversation_limit > 0:
                history = history[-self.conversation_limit:]
            parts.append("--- CONVERSATION HISTORY ---")
            for turn in history:
                parts.append(turn["transcript"])
                parts.append(f"YOUR RESPONSE: {turn['response']}")
                parts.append("")
            # Remove trailing blank if present before next section
            if parts[-1] == "":
                parts.pop()
            parts.append("")

        if prior:
            parts.append("--- PRIOR CONTEXT ---")
            parts.append(self._format_segments(prior))
            parts.append("")

        parts.append("--- NEW TRANSCRIPT ---")
        parts.append(self._format_segments(new))
        parts.append("--- END ---")

        return "\n".join(parts)

    def dispatch(self) -> bool:
        """Send unsent transcript to the LLM. Returns True if anything was sent."""
        if self.context:
            prior, new = self.buffer.take_with_context(self.context_limit)
            if not new:
                print("  (nothing new to send)")
                return False
            prompt = self._build_prompt(prior, new)
        else:
            new = self.buffer.take_unsent()
            if not new:
                print("  (nothing new to send)")
                return False
            prompt = self._build_prompt([], new)

        self._dispatch_count += 1
        n = len(new)
        ctx = f" + {len(prior)} prior" if self.context and prior else ""
        print(f"\n{'━'*60}")
        print(f"  🧠 Prompting {self.provider.name} ({n} new{ctx}) [#{self._dispatch_count}]")
        print(f"{'━'*60}")

        if self.stream:
            print()  # blank line before streamed output
            full_response = []
            for chunk in self.provider.send_streaming(prompt):
                print(chunk, end='', flush=True)
                full_response.append(chunk)
            response = ''.join(full_response).strip() or None
            if response:
                print(f"\n{'━'*60}\n")
        else:
            response = self.provider.send(prompt)
            if response:
                print(f"\n{response}\n")
                print(f"{'━'*60}\n")

        # Conversation history: track transcript/response pairs
        if self.conversation and response:
            self._history.append({
                "transcript": self._format_segments(new),
                "response": response,
            })

        # Session log: write both transcript and response
        if self._session_log_fh:
            ts_now = datetime.now().strftime("%H:%M:%S")
            self._session_log_fh.write(
                f"=== DISPATCH #{self._dispatch_count} at {ts_now} ===\n"
            )
            self._session_log_fh.write("TRANSCRIPT:\n")
            self._session_log_fh.write(self._format_segments(new) + "\n\n")
            self._session_log_fh.write("LLM RESPONSE:\n")
            self._session_log_fh.write((response or "(no response)") + "\n\n")
            self._session_log_fh.flush()

        return True

    def _timer_loop(self):
        while self._running:
            time.sleep(self.interval)
            self.dispatch()

    def start_timer(self):
        """Start automatic dispatch on interval. No-op in manual mode."""
        if self.interval is None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._session_log_fh:
            self._session_log_fh.close()
            self._session_log_fh = None

    def conversation_summary(self) -> str | None:
        """Return a summary of the conversation history, or None if not in conversation mode."""
        if not self.conversation or not self._history:
            return None
        total_turns = len(self._history)
        total_transcript_chars = sum(len(h["transcript"]) for h in self._history)
        total_response_chars = sum(len(h["response"]) for h in self._history)
        lines = [
            "Conversation summary",
            f"  Turns           : {total_turns}",
            f"  Transcript chars: {total_transcript_chars}",
            f"  Response chars  : {total_response_chars}",
        ]
        if self.conversation_limit > 0:
            lines.append(f"  History limit   : {self.conversation_limit}")
        return "\n".join(lines)


# Backward-compatible alias
ClaudeDispatcher = LLMDispatcher


def save_transcript(segments: list[dict], path: Path):
    """Save full session transcript to file."""
    with open(path, "w") as f:
        for seg in segments:
            ts = datetime.fromtimestamp(seg["time"]).strftime("%Y-%m-%d %H:%M:%S")
            spk = f" [{seg['speaker']}]" if seg.get("speaker") else ""
            f.write(f"[{ts}]{spk} {seg['text']}\n")
    print(f"  📄 Transcript saved to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Live audio transcription with periodic LLM analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s                          # defaults: base model, 60s auto, claude-cli
  %(prog)s --llm openai --llm-model gpt-4o  # use OpenAI
  %(prog)s --llm ollama --llm-model llama3   # use local Ollama
  %(prog)s --manual --context       # manual dispatch with full history
  %(prog)s --context --context-limit 20  # rolling window of last 20 segments
  %(prog)s --model small -i 30      # better accuracy, prompt every 30s
  %(prog)s --manual --prompt "Extract action items from this meeting."
  %(prog)s --conversation           # Claude remembers its prior responses
  %(prog)s --conversation --conversation-limit 5  # keep last 5 turns
  %(prog)s --list-devices            # show mic options
  %(prog)s -l es                     # transcribe Spanish audio
  %(prog)s -o transcript.txt         # stream transcript to file in real-time
  %(prog)s --audio-file meeting.wav  # transcribe a recording
  %(prog)s --log-session session.log # save transcript + Claude responses
  %(prog)s --system-audio            # capture desktop audio via BlackHole/etc.
  %(prog)s --system-audio --input-device 5  # system audio with manual device
  %(prog)s --web                         # launch web UI on port 8765
  %(prog)s --web --port 9000             # web UI on custom port
""",
    )
    parser.add_argument(
        "--model", "-m", default="base",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "--interval", "-i", type=int, default=60,
        help="Seconds between Claude prompts (default: 60, ignored with --manual)",
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="Manual mode: press Enter to send transcript to Claude",
    )
    parser.add_argument(
        "--chunk", type=int, default=5,
        help="Seconds of audio per transcription chunk (default: 5)",
    )
    parser.add_argument(
        "--prompt", default=(
            "You are a real-time AI collaborator listening to a live audio transcription. "
            "Engage with what's being said: answer questions, provide analysis, "
            "offer relevant expertise, and surface useful context. "
            "If the speaker asks something, answer it directly. "
            "If they're discussing a design or problem, contribute meaningfully. "
            "Be concise and direct."
        ),
        help="System prompt sent to Claude with each transcript batch",
    )
    parser.add_argument(
        "--context", action="store_true",
        help="Send full transcript history with each dispatch (not just new segments)",
    )
    parser.add_argument(
        "--context-limit", type=int, default=0,
        help="Max prior segments to include as context (0 = unlimited, default: 0)",
    )
    parser.add_argument(
        "--conversation", action="store_true",
        help="Maintain conversation history across dispatches so Claude remembers prior responses",
    )
    parser.add_argument(
        "--conversation-limit", type=int, default=0,
        help="Max conversation turns to include in prompt (0 = unlimited, default: 0)",
    )
    parser.add_argument(
        "--llm", default="claude-cli",
        choices=list(PROVIDERS.keys()),
        help="LLM provider to use (default: claude-cli)",
    )
    parser.add_argument(
        "--llm-model", default=None,
        help="Model name for the selected LLM provider",
    )
    parser.add_argument(
        "--claude-model", default=None,
        help="(Deprecated: use --llm-model) Model to pass to claude CLI",
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Save full transcript to this file on exit",
    )
    parser.add_argument(
        "--diarize", action="store_true",
        help="Enable speaker diarization (requires HF_TOKEN, increases chunk to 30s)",
    )
    parser.add_argument(
        "--stream", action="store_true",
        help="Stream Claude's response in real-time instead of waiting for completion",
    )
    parser.add_argument(
        "--compute", default="cpu",
        choices=["cpu", "cuda", "auto"],
        help="Compute device for whisper (default: cpu)",
    )
    parser.add_argument(
        "--list-devices", action="store_true",
        help="List audio input devices and exit",
    )
    parser.add_argument(
        "--input-device", type=int, default=None,
        help="Audio input device index (see --list-devices)",
    )
    parser.add_argument(
        "--language", "-l", default=None,
        help="Whisper language code for transcription (e.g. en, es, fr, de, ja, zh). Default: auto-detect",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Stream transcript to this file in real-time (append, flush after each segment)",
    )
    parser.add_argument(
        "--audio-file", default=None,
        help="Path to audio file (wav, mp3, etc.) to transcribe instead of live mic",
    )
    parser.add_argument(
        "--log-session", default=None,
        help="Log both transcript and Claude responses to this file after each dispatch",
    )
    parser.add_argument(
        "--system-audio", action="store_true",
        help="Capture system/desktop audio via virtual loopback device (e.g. BlackHole)",
    )
    parser.add_argument(
        "--web", action="store_true",
        help="Launch the web UI instead of the terminal interface",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Port for the web UI server (default: 8765)",
    )

    args = parser.parse_args()

    # Validate --audio-file path
    if args.audio_file and not Path(args.audio_file).is_file():
        parser.error(f"Audio file not found: {args.audio_file}")

    if args.list_devices:
        print(sd.query_devices())
        return

    # ── Web UI mode ──
    if args.web:
        from web_server import start_web_server
        start_web_server(
            port=args.port,
            model=args.model,
            prompt=args.prompt,
            interval=args.interval,
            context=args.context,
            context_limit=args.context_limit,
            claude_model=args.claude_model,
        )
        return

    # ── System audio / input device selection ──
    system_audio_device_name = None
    if args.input_device is not None:
        # Explicit --input-device always wins, even with --system-audio
        sd.default.device[0] = args.input_device
        if args.system_audio:
            # Look up the device name for the banner
            try:
                dev_info = sd.query_devices(args.input_device)
                system_audio_device_name = dev_info['name']
            except Exception:
                system_audio_device_name = f"device #{args.input_device}"
    elif args.system_audio:
        result = find_system_audio_device()
        if result is None:
            instructions = get_system_audio_install_instructions()
            print(f"\n  Error: No virtual audio loopback device found.", file=sys.stderr)
            print(f"  {instructions}\n", file=sys.stderr)
            sys.exit(1)
        device_index, device_name = result
        sd.default.device[0] = device_index
        system_audio_device_name = device_name
        print(f"  System audio device: {device_name} (index {device_index})")

    # Handle deprecated --claude-model → --llm-model
    llm_model = args.llm_model
    if args.claude_model:
        import warnings
        warnings.warn(
            "--claude-model is deprecated, use --llm-model instead",
            DeprecationWarning,
            stacklevel=1,
        )
        if llm_model is None:
            llm_model = args.claude_model

    manual = args.manual
    trigger_label = "Enter key (manual)" if manual else f"{args.interval}s (auto)"
    llm_label = args.llm
    if llm_model:
        llm_label += f" / {llm_model}"

    # ── Banner ──
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  live-scribe                                            ║")
    print("║  Real-time transcription → LLM analysis                 ║")
    print("╠══════════════════════════════════════════════════════════╣")
    diarize_label = "on (pyannote 3.1)" if args.diarize else "off"
    lang_label = args.language if args.language else "auto-detect"
    input_label = f"file: {args.audio_file}" if args.audio_file else "microphone"
    print(f"║  Whisper model : {args.model:<40}║")
    print(f"║  Language      : {lang_label:<40}║")
    print(f"║  Input         : {input_label:<40}║")
    print(f"║  Diarization   : {diarize_label:<40}║")
    context_label = (
        f"full history (last {args.context_limit})" if args.context and args.context_limit
        else "full history" if args.context
        else "new only"
    )
    convo_label = (
        f"on (last {args.conversation_limit} turns)" if args.conversation and args.conversation_limit
        else "on" if args.conversation
        else "off"
    )
    print(f"║  Chunk size    : {args.chunk}s{' '*(39-len(str(args.chunk)))}║")
    print(f"║  LLM provider  : {llm_label:<40}║")
    print(f"║  LLM trigger   : {trigger_label:<40}║")
    print(f"║  Context mode  : {context_label:<40}║")
    if system_audio_device_name:
        print(f"║  Audio source  : {system_audio_device_name:<40}║")
    print(f"║  Conversation  : {convo_label:<40}║")
    if args.output:
        print(f"║  Streaming to  : {args.output:<40}║")
    if args.log_session:
        print(f"║  Session log   : {args.log_session:<40}║")
    stream_label = "on" if args.stream else "off"
    print(f"║  Streaming     : {stream_label:<40}║")
    print("╠══════════════════════════════════════════════════════════╣")
    if manual:
        print("║  Enter = send to LLM  │  Ctrl+C = stop                 ║")
    else:
        print("║  Ctrl+C to stop                                        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    transcriber = AudioTranscriber(
        model_size=args.model,
        device=args.compute,
        chunk_sec=args.chunk,
        diarize=args.diarize,
        language=args.language,
        output_file=args.output,
    )
    dispatcher = LLMDispatcher(
        buffer=transcriber.buffer,
        system_prompt=args.prompt,
        provider_name=args.llm,
        model=llm_model,
        interval=None if manual else args.interval,
        context=args.context,
        context_limit=args.context_limit,
        session_log_file=args.log_session,
        stream=args.stream,
        conversation=args.conversation,
        conversation_limit=args.conversation_limit,
    )

    def shutdown(sig=None, frame=None):
        print("\n\n  Shutting down…")
        dispatcher.stop()
        transcriber.stop()

        all_segs = transcriber.buffer.all()
        if all_segs:
            print(f"\n{'━'*60}")
            print("  Full session transcript")
            print(f"{'━'*60}")
            for seg in all_segs:
                ts = datetime.fromtimestamp(seg["time"]).strftime("%H:%M:%S")
                spk = f" [{seg['speaker']}]" if seg.get("speaker") else ""
                print(f"  [{ts}]{spk} {seg['text']}")
            print(f"{'━'*60}")
            print(f"  {len(all_segs)} segment(s) recorded\n")

            if args.save:
                save_transcript(all_segs, Path(args.save))

        convo_summary = dispatcher.conversation_summary()
        if convo_summary:
            print(f"\n{'━'*60}")
            print(f"  {convo_summary}")
            print(f"{'━'*60}\n")

        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── Audio file mode: transcribe file, dispatch, then exit ──
    if args.audio_file:
        transcriber.transcribe_file(args.audio_file)
        dispatcher.dispatch()
        shutdown()
        return

    # ── Live microphone mode ──
    transcriber.start()
    dispatcher.start_timer()  # no-op in manual mode

    if manual:
        print("  🎙  Listening… (press Enter to send to LLM)\n")
        while True:
            try:
                input()
                dispatcher.dispatch()
            except EOFError:
                shutdown()
    else:
        print("  🎙  Listening…\n")
        while True:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
