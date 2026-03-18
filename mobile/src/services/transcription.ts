/**
 * Transcription service for Live Scribe mobile app.
 *
 * Sends audio files to OpenAI's Whisper API for speech-to-text.
 * This is the "standalone" transcription path — the mobile app captures
 * audio locally, uploads chunks to the Whisper API, and gets text back.
 *
 * Why cloud-based Whisper instead of on-device?
 *   - On-device Whisper models for React Native are still experimental
 *   - The API gives excellent accuracy with minimal setup
 *   - File sizes are small (5-10s chunks of M4A at 128kbps = ~80-160KB)
 *
 * Future: could add on-device transcription via whisper.cpp bindings.
 */

import { TranscriptSegment } from '../types';
import { generateId } from './storage';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Raw response shape from the OpenAI Whisper API. */
interface WhisperResponse {
  text: string;
}

/** Verbose response with segment-level timestamps. */
interface WhisperVerboseResponse {
  text: string;
  segments: Array<{
    id: number;
    text: string;
    start: number;
    end: number;
  }>;
}

// ---------------------------------------------------------------------------
// Main transcription function
// ---------------------------------------------------------------------------

/**
 * Transcribe an audio file using the OpenAI Whisper API.
 *
 * @param audioUri - Local file URI to the audio file (e.g. from AudioRecorder).
 * @param apiKey   - OpenAI API key.
 * @param options  - Optional configuration.
 * @returns The transcribed text as a string.
 *
 * @example
 * ```ts
 * const text = await transcribeAudio(
 *   'file:///tmp/chunk.m4a',
 *   'sk-...',
 * );
 * console.log(text); // "Hello, this is a test recording."
 * ```
 */
export async function transcribeAudio(
  audioUri: string,
  apiKey: string,
  options: {
    /** Whisper model to use. Default: "whisper-1". */
    model?: string;
    /** Language hint (ISO 639-1). Omit for auto-detect. */
    language?: string;
    /** Optional prompt to guide transcription style. */
    prompt?: string;
  } = {}
): Promise<string> {
  const { model = 'whisper-1', language, prompt } = options;

  // Build multipart form data
  const formData = new FormData();

  // React Native's fetch supports passing file URIs directly via FormData.
  // We create a file-like object with the URI, name, and MIME type.
  const file = {
    uri: audioUri,
    name: 'audio.m4a',
    type: 'audio/m4a',
  } as unknown as Blob;

  formData.append('file', file);
  formData.append('model', model);

  if (language) {
    formData.append('language', language);
  }
  if (prompt) {
    formData.append('prompt', prompt);
  }

  const response = await fetch(
    'https://api.openai.com/v1/audio/transcriptions',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        // Do NOT set Content-Type — fetch sets it automatically with boundary
      },
      body: formData,
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Whisper API error (${response.status}): ${errorText}`
    );
  }

  const data: WhisperResponse = await response.json();
  return data.text.trim();
}

/**
 * Transcribe audio and return individual segments with timestamps.
 *
 * Uses the "verbose_json" response format to get segment-level detail.
 * Each segment becomes a TranscriptSegment with a unique ID and timestamp.
 *
 * @param audioUri       - Local file URI to the audio file.
 * @param apiKey         - OpenAI API key.
 * @param chunkStartTime - Wall-clock time (epoch ms) when this chunk started recording.
 *                         Used to compute absolute timestamps for each segment.
 * @returns Array of TranscriptSegment objects.
 */
export async function transcribeAudioWithSegments(
  audioUri: string,
  apiKey: string,
  chunkStartTime: number,
  options: {
    model?: string;
    language?: string;
    prompt?: string;
  } = {}
): Promise<TranscriptSegment[]> {
  const { model = 'whisper-1', language, prompt } = options;

  const formData = new FormData();

  const file = {
    uri: audioUri,
    name: 'audio.m4a',
    type: 'audio/m4a',
  } as unknown as Blob;

  formData.append('file', file);
  formData.append('model', model);
  formData.append('response_format', 'verbose_json');

  if (language) {
    formData.append('language', language);
  }
  if (prompt) {
    formData.append('prompt', prompt);
  }

  const response = await fetch(
    'https://api.openai.com/v1/audio/transcriptions',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: formData,
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Whisper API error (${response.status}): ${errorText}`
    );
  }

  const data: WhisperVerboseResponse = await response.json();

  // Convert Whisper segments to our TranscriptSegment format
  return data.segments
    .filter((seg) => seg.text.trim().length > 0)
    .map((seg) => ({
      id: generateId(),
      text: seg.text.trim(),
      // Whisper segment timestamps are relative to the chunk start (in seconds).
      // Convert to absolute epoch milliseconds.
      timestamp: chunkStartTime + seg.start * 1000,
    }));
}
