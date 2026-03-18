#!/usr/bin/env python3
"""
live-scribe: Real-time audio transcription with periodic Claude analysis.

Captures microphone audio, transcribes locally with faster-whisper,
and periodically sends accumulated transcription to Claude CLI for processing.
"""

import argparse
import platform
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


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

    def __init__(self):
        self._segments: list[dict] = []
        self._unsent: list[dict] = []
        self._lock = threading.Lock()

    def add(self, text: str, timestamp: float, speaker: str | None = None):
        entry = {"text": text, "time": timestamp, "speaker": speaker}
        with self._lock:
            self._segments.append(entry)
            self._unsent.append(entry)

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


class AudioTranscriber:
    """Captures microphone audio and transcribes with faster-whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        chunk_sec: int = 5,
        diarize: bool = False,
    ):
        print(f"⏳ Loading whisper model '{model_size}' on {device}…")
        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        print("✅ Model loaded.")
        self.sample_rate = 16000
        self.chunk_sec = chunk_sec
        self.diarize = diarize
        self.buffer = TranscriptionBuffer()
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

            segments, _info = self.model.transcribe(
                audio,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
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

    def stop(self):
        self._running = False
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()


class ClaudeDispatcher:
    """Sends accumulated transcript to Claude CLI, either on a timer or on demand."""

    def __init__(
        self,
        buffer: TranscriptionBuffer,
        system_prompt: str,
        interval: int | None = None,
        claude_model: str | None = None,
        timeout: int = 120,
        context: bool = False,
        context_limit: int = 0,
    ):
        self.buffer = buffer
        self.system_prompt = system_prompt
        self.interval = interval  # None = manual mode
        self.claude_model = claude_model
        self.timeout = timeout
        self.context = context
        self.context_limit = context_limit
        self._running = False
        self._dispatch_count = 0

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

        if prior:
            parts.append("--- PRIOR CONTEXT ---")
            parts.append(self._format_segments(prior))
            parts.append("")

        parts.append("--- NEW TRANSCRIPT ---")
        parts.append(self._format_segments(new))
        parts.append("--- END ---")

        return "\n".join(parts)

    def _call_claude(self, prompt: str) -> str | None:
        cmd = ["claude", "-p", prompt]
        if self.claude_model:
            cmd.extend(["--model", self.claude_model])
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if r.returncode == 0:
                return r.stdout.strip()
            print(f"  ⚠ claude exited {r.returncode}: {r.stderr[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("  ⚠ claude timed out", file=sys.stderr)
        except FileNotFoundError:
            print("  ⚠ 'claude' not found in PATH", file=sys.stderr)
        return None

    def dispatch(self) -> bool:
        """Send unsent transcript to Claude. Returns True if anything was sent."""
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
        print(f"  🧠 Prompting Claude ({n} new{ctx}) [#{self._dispatch_count}]")
        print(f"{'━'*60}")

        response = self._call_claude(prompt)
        if response:
            print(f"\n{response}\n")
            print(f"{'━'*60}\n")
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
        description="Live audio transcription with periodic Claude analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s                          # defaults: base model, 60s auto, new-only
  %(prog)s --manual --context       # manual dispatch with full history
  %(prog)s --context --context-limit 20  # rolling window of last 20 segments
  %(prog)s --model small -i 30      # better accuracy, prompt every 30s
  %(prog)s --manual --prompt "Extract action items from this meeting."
  %(prog)s --list-devices            # show mic options
  %(prog)s --system-audio            # capture desktop audio via BlackHole/etc.
  %(prog)s --system-audio --input-device 5  # system audio with manual device
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
        "--claude-model", default=None,
        help="Model to pass to claude CLI (e.g. sonnet, opus)",
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
        "--system-audio", action="store_true",
        help="Capture system/desktop audio via virtual loopback device (e.g. BlackHole)",
    )

    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
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

    manual = args.manual
    trigger_label = "Enter key (manual)" if manual else f"{args.interval}s (auto)"

    # ── Banner ──
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  live-scribe                                            ║")
    print("║  Real-time transcription → Claude analysis              ║")
    print("╠══════════════════════════════════════════════════════════╣")
    diarize_label = "on (pyannote 3.1)" if args.diarize else "off"
    print(f"║  Whisper model : {args.model:<40}║")
    print(f"║  Diarization   : {diarize_label:<40}║")
    context_label = (
        f"full history (last {args.context_limit})" if args.context and args.context_limit
        else "full history" if args.context
        else "new only"
    )
    print(f"║  Chunk size    : {args.chunk}s{' '*(39-len(str(args.chunk)))}║")
    print(f"║  Claude trigger: {trigger_label:<40}║")
    print(f"║  Context mode  : {context_label:<40}║")
    if system_audio_device_name:
        print(f"║  Audio source  : {system_audio_device_name:<40}║")
    if args.claude_model:
        print(f"║  Claude model  : {args.claude_model:<40}║")
    print("╠══════════════════════════════════════════════════════════╣")
    if manual:
        print("║  Enter = send to Claude  │  Ctrl+C = stop              ║")
    else:
        print("║  Ctrl+C to stop                                        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    transcriber = AudioTranscriber(
        model_size=args.model,
        device=args.compute,
        chunk_sec=args.chunk,
        diarize=args.diarize,
    )
    dispatcher = ClaudeDispatcher(
        buffer=transcriber.buffer,
        system_prompt=args.prompt,
        interval=None if manual else args.interval,
        claude_model=args.claude_model,
        context=args.context,
        context_limit=args.context_limit,
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

        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    transcriber.start()
    dispatcher.start_timer()  # no-op in manual mode

    if manual:
        print("  🎙  Listening… (press Enter to send to Claude)\n")
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
