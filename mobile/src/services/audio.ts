/**
 * Audio recording service for Live Scribe mobile app.
 *
 * Uses expo-av to capture microphone audio. Supports:
 *   - Start/stop recording (returns a file URI for the complete recording)
 *   - Chunk-based capture (record for N seconds, return the chunk URI)
 *
 * Audio is recorded in M4A format (AAC) which is well-supported on both
 * iOS and Android, and works with the OpenAI Whisper API.
 *
 * IMPORTANT: The app must request microphone permission before using
 * this service. The useAudioRecorder hook handles that automatically.
 */

import { Audio } from 'expo-av';

// ---------------------------------------------------------------------------
// Recording options
// ---------------------------------------------------------------------------

/**
 * High-quality recording preset suitable for speech transcription.
 * M4A/AAC at 128kbps, 16kHz mono — balances quality and file size.
 */
const RECORDING_OPTIONS: Audio.RecordingOptions = {
  isMeteringEnabled: true,
  android: {
    extension: '.m4a',
    outputFormat: Audio.AndroidOutputFormat.MPEG_4,
    audioEncoder: Audio.AndroidAudioEncoder.AAC,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 128000,
  },
  ios: {
    extension: '.m4a',
    outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
    audioQuality: Audio.IOSAudioQuality.HIGH,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 128000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: {
    mimeType: 'audio/webm',
    bitsPerSecond: 128000,
  },
};

// ---------------------------------------------------------------------------
// AudioRecorder class
// ---------------------------------------------------------------------------

/**
 * Manages audio recording lifecycle.
 *
 * Usage:
 * ```ts
 * const recorder = new AudioRecorder();
 * await recorder.start();
 * // ... record for a while ...
 * const uri = await recorder.stop(); // file URI to the recorded audio
 * ```
 *
 * For chunk-based capture (used during continuous transcription):
 * ```ts
 * const recorder = new AudioRecorder();
 * await recorder.start();
 * const chunkUri = await recorder.captureChunk(5000); // 5 seconds
 * // chunkUri contains 5s of audio; recorder continues with a new recording
 * ```
 */
export class AudioRecorder {
  /** The current expo-av Recording instance, or null if idle. */
  private recording: Audio.Recording | null = null;

  /** Whether we are actively recording. */
  private _isRecording = false;

  /** Timestamp (epoch ms) when the current recording started. */
  private _startTime = 0;

  /** Returns true if currently recording. */
  get isRecording(): boolean {
    return this._isRecording;
  }

  /** Returns epoch ms when current recording started (0 if not recording). */
  get startTime(): number {
    return this._startTime;
  }

  /**
   * Request microphone permission and configure audio mode.
   * Call this once before the first recording.
   *
   * @returns `true` if permission was granted.
   */
  async requestPermission(): Promise<boolean> {
    const { status } = await Audio.requestPermissionsAsync();
    if (status !== 'granted') {
      return false;
    }

    // Configure audio session for recording
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
      // Keep audio playing through earpiece/speaker when recording
      staysActiveInBackground: false,
    });

    return true;
  }

  /**
   * Start recording audio from the microphone.
   *
   * @throws if permission has not been granted or if already recording.
   */
  async start(): Promise<void> {
    if (this._isRecording) {
      throw new Error('Already recording. Call stop() first.');
    }

    const recording = new Audio.Recording();
    await recording.prepareToRecordAsync(RECORDING_OPTIONS);
    await recording.startAsync();

    this.recording = recording;
    this._isRecording = true;
    this._startTime = Date.now();
  }

  /**
   * Stop recording and return the URI to the recorded audio file.
   *
   * @returns Local file URI (e.g. `file:///data/.../recording.m4a`).
   * @throws if not currently recording.
   */
  async stop(): Promise<string> {
    if (!this.recording || !this._isRecording) {
      throw new Error('Not currently recording. Call start() first.');
    }

    await this.recording.stopAndUnloadAsync();
    const uri = this.recording.getURI();

    // Reset audio mode so other apps can use the speaker
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
    });

    this.recording = null;
    this._isRecording = false;
    this._startTime = 0;

    if (!uri) {
      throw new Error('Recording completed but no URI was returned.');
    }

    return uri;
  }

  /**
   * Capture a chunk of audio for the specified duration.
   *
   * This stops the current recording, saves the chunk, and immediately
   * starts a new recording so there is minimal gap in audio capture.
   *
   * @param durationMs - How long to record this chunk (milliseconds).
   *                     If the recording has been running longer than this,
   *                     it stops immediately and returns what was captured.
   * @returns Local file URI for the audio chunk.
   */
  async captureChunk(durationMs: number): Promise<string> {
    if (!this.recording || !this._isRecording) {
      throw new Error('Not currently recording. Call start() first.');
    }

    const elapsed = Date.now() - this._startTime;
    if (elapsed < durationMs) {
      // Wait for the remaining time
      await new Promise((resolve) =>
        setTimeout(resolve, durationMs - elapsed)
      );
    }

    // Stop current recording and get the chunk
    await this.recording.stopAndUnloadAsync();
    const uri = this.recording.getURI();

    // Immediately start a new recording to minimize gaps
    const newRecording = new Audio.Recording();
    await newRecording.prepareToRecordAsync(RECORDING_OPTIONS);
    await newRecording.startAsync();

    this.recording = newRecording;
    this._startTime = Date.now();
    // _isRecording stays true

    if (!uri) {
      throw new Error('Chunk recording completed but no URI was returned.');
    }

    return uri;
  }
}
