/**
 * Hook for managing the transcription pipeline.
 *
 * Coordinates the AudioRecorder and Whisper API transcription service
 * to produce a continuous stream of TranscriptSegments.
 *
 * The pipeline works like this:
 *   1. Start recording audio (via useAudioRecorder)
 *   2. Every N seconds, capture a chunk of audio
 *   3. Send each chunk to the OpenAI Whisper API
 *   4. Append the resulting segments to the transcript
 *
 * This hook manages step 2-4 and the resulting state.
 *
 * Usage:
 * ```tsx
 * const { transcript, isTranscribing, startPipeline, stopPipeline } =
 *   useTranscription(audioRecorder, whisperApiKey, chunkDurationSec);
 * ```
 */

import { useCallback, useRef, useState } from 'react';
import {
  transcribeAudioWithSegments,
} from '../services/transcription';
import { TranscriptSegment } from '../types';
import { UseAudioRecorderReturn } from './useAudioRecorder';

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface UseTranscriptionReturn {
  /** All transcript segments accumulated so far. */
  transcript: TranscriptSegment[];

  /** Whether the transcription pipeline is actively running. */
  isTranscribing: boolean;

  /** Number of chunks that have been transcribed. */
  chunkCount: number;

  /** Last error from the transcription service, or null. */
  error: string | null;

  /**
   * Start the continuous transcription pipeline.
   * Begins recording and starts the chunk capture loop.
   */
  startPipeline: () => Promise<void>;

  /**
   * Stop the transcription pipeline.
   * Stops recording and processes any remaining audio.
   */
  stopPipeline: () => Promise<void>;

  /** Clear all transcript segments (e.g. for a new session). */
  clearTranscript: () => void;

  /** Manually add a segment (e.g. from a WebSocket in remote mode). */
  addSegment: (segment: TranscriptSegment) => void;

  /** Get the full transcript as formatted text (for sending to LLM). */
  getFormattedTranscript: () => string;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useTranscription(
  /** The audio recorder hook instance. */
  audioRecorder: UseAudioRecorderReturn,
  /** OpenAI API key for Whisper. */
  whisperApiKey: string,
  /** How many seconds of audio per transcription chunk. */
  chunkDurationSec: number = 5
): UseTranscriptionReturn {
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [chunkCount, setChunkCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Ref to control the chunk capture loop
  const loopRunningRef = useRef(false);

  // Ref to track the interval timer
  const intervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * The chunk capture loop.
   * Runs continuously while recording, capturing and transcribing chunks.
   */
  const runChunkLoop = useCallback(async () => {
    if (!loopRunningRef.current) return;

    try {
      // Capture a chunk of audio
      const chunkUri = await audioRecorder.captureChunk(
        chunkDurationSec * 1000
      );

      if (!chunkUri || !loopRunningRef.current) return;

      // The chunk started recording `chunkDurationSec` ago
      const chunkStartTime = Date.now() - chunkDurationSec * 1000;

      // Send to Whisper API for transcription
      const segments = await transcribeAudioWithSegments(
        chunkUri,
        whisperApiKey,
        chunkStartTime
      );

      if (segments.length > 0 && loopRunningRef.current) {
        setTranscript((prev) => [...prev, ...segments]);
        setChunkCount((prev) => prev + 1);
      }
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Transcription failed';
      setError(msg);
      console.warn('Transcription chunk error:', msg);
    }

    // Schedule next chunk if still running
    if (loopRunningRef.current) {
      // Use setTimeout instead of setInterval to avoid overlap
      intervalRef.current = setTimeout(runChunkLoop, 100);
    }
  }, [audioRecorder, whisperApiKey, chunkDurationSec]);

  // Start pipeline
  const startPipeline = useCallback(async () => {
    setError(null);

    if (!whisperApiKey) {
      setError(
        'OpenAI API key required for transcription. Set it in Settings.'
      );
      return;
    }

    // Start recording
    const started = await audioRecorder.start();
    if (!started) {
      setError('Failed to start audio recording.');
      return;
    }

    setIsTranscribing(true);
    loopRunningRef.current = true;

    // Wait for the first chunk duration, then start the loop
    intervalRef.current = setTimeout(runChunkLoop, chunkDurationSec * 1000);
  }, [audioRecorder, whisperApiKey, chunkDurationSec, runChunkLoop]);

  // Stop pipeline
  const stopPipeline = useCallback(async () => {
    loopRunningRef.current = false;

    if (intervalRef.current) {
      clearTimeout(intervalRef.current);
      intervalRef.current = null;
    }

    // Stop recording and get the final audio
    const finalUri = await audioRecorder.stop();

    if (finalUri && whisperApiKey) {
      try {
        // Transcribe the final chunk
        const chunkStartTime = Date.now() - (audioRecorder.durationSec * 1000);
        const segments = await transcribeAudioWithSegments(
          finalUri,
          whisperApiKey,
          chunkStartTime
        );

        if (segments.length > 0) {
          setTranscript((prev) => [...prev, ...segments]);
          setChunkCount((prev) => prev + 1);
        }
      } catch (err) {
        console.warn('Final chunk transcription error:', err);
      }
    }

    setIsTranscribing(false);
  }, [audioRecorder, whisperApiKey]);

  // Clear transcript
  const clearTranscript = useCallback(() => {
    setTranscript([]);
    setChunkCount(0);
    setError(null);
  }, []);

  // Add a single segment (for remote mode / WebSocket)
  const addSegment = useCallback((segment: TranscriptSegment) => {
    setTranscript((prev) => [...prev, segment]);
  }, []);

  // Format transcript as text for LLM prompt
  const getFormattedTranscript = useCallback((): string => {
    return transcript
      .map((seg) => {
        const time = new Date(seg.timestamp).toLocaleTimeString('en-US', {
          hour12: false,
        });
        const speaker = seg.speaker ? ` [${seg.speaker}]` : '';
        return `[${time}]${speaker} ${seg.text}`;
      })
      .join('\n');
  }, [transcript]);

  return {
    transcript,
    isTranscribing,
    chunkCount,
    error,
    startPipeline,
    stopPipeline,
    clearTranscript,
    addSegment,
    getFormattedTranscript,
  };
}
