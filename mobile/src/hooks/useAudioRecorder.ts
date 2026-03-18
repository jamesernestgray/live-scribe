/**
 * Hook for managing audio recording in the Live Scribe app.
 *
 * Wraps the AudioRecorder service with React state management.
 * Handles permissions, recording lifecycle, and chunk-based capture
 * for continuous transcription.
 *
 * Usage:
 * ```tsx
 * function RecordScreen() {
 *   const { isRecording, duration, start, stop, error } = useAudioRecorder();
 *
 *   return (
 *     <Button
 *       title={isRecording ? 'Stop' : 'Record'}
 *       onPress={isRecording ? stop : start}
 *     />
 *   );
 * }
 * ```
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { AudioRecorder } from '../services/audio';
import { RecordingStatus } from '../types';

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface UseAudioRecorderReturn {
  /** Current recording status. */
  status: RecordingStatus;

  /** Shorthand: true when status is 'recording'. */
  isRecording: boolean;

  /** Recording duration in seconds (updates every second while recording). */
  durationSec: number;

  /** Whether microphone permission has been granted. */
  hasPermission: boolean;

  /** Last error message, or null. */
  error: string | null;

  /** Request microphone permission. Called automatically on mount. */
  requestPermission: () => Promise<boolean>;

  /**
   * Start recording.
   * @returns true if recording started successfully.
   */
  start: () => Promise<boolean>;

  /**
   * Stop recording.
   * @returns The URI to the recorded audio file, or null on error.
   */
  stop: () => Promise<string | null>;

  /**
   * Capture a chunk of audio (stops current, saves, restarts).
   * Used for continuous transcription pipeline.
   *
   * @param durationMs - Chunk duration in milliseconds.
   * @returns The URI to the audio chunk, or null on error.
   */
  captureChunk: (durationMs: number) => Promise<string | null>;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useAudioRecorder(): UseAudioRecorderReturn {
  const [status, setStatus] = useState<RecordingStatus>('idle');
  const [durationSec, setDurationSec] = useState(0);
  const [hasPermission, setHasPermission] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use a ref for the recorder so it persists across renders
  const recorderRef = useRef<AudioRecorder>(new AudioRecorder());

  // Timer ref for duration updates
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  // Start the duration timer
  const startTimer = useCallback(() => {
    // Clear any existing timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    setDurationSec(0);
    timerRef.current = setInterval(() => {
      const recorder = recorderRef.current;
      if (recorder.isRecording) {
        const elapsed = Math.floor((Date.now() - recorder.startTime) / 1000);
        setDurationSec(elapsed);
      }
    }, 1000);
  }, []);

  // Stop the duration timer
  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Request permission
  const requestPermission = useCallback(async (): Promise<boolean> => {
    try {
      const granted = await recorderRef.current.requestPermission();
      setHasPermission(granted);
      if (!granted) {
        setError('Microphone permission denied. Please enable it in Settings.');
      }
      return granted;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Permission request failed';
      setError(msg);
      return false;
    }
  }, []);

  // Auto-request permission on mount
  useEffect(() => {
    requestPermission();
  }, [requestPermission]);

  // Start recording
  const start = useCallback(async (): Promise<boolean> => {
    try {
      setError(null);

      if (!hasPermission) {
        const granted = await requestPermission();
        if (!granted) return false;
      }

      await recorderRef.current.start();
      setStatus('recording');
      startTimer();
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start recording';
      setError(msg);
      setStatus('idle');
      return false;
    }
  }, [hasPermission, requestPermission, startTimer]);

  // Stop recording
  const stop = useCallback(async (): Promise<string | null> => {
    try {
      setError(null);
      setStatus('processing');
      stopTimer();

      const uri = await recorderRef.current.stop();
      setStatus('idle');
      setDurationSec(0);
      return uri;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to stop recording';
      setError(msg);
      setStatus('idle');
      setDurationSec(0);
      return null;
    }
  }, [stopTimer]);

  // Capture a chunk
  const captureChunk = useCallback(
    async (durationMs: number): Promise<string | null> => {
      try {
        setError(null);
        const uri = await recorderRef.current.captureChunk(durationMs);
        return uri;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to capture chunk';
        setError(msg);
        return null;
      }
    },
    []
  );

  return {
    status,
    isRecording: status === 'recording',
    durationSec,
    hasPermission,
    error,
    requestPermission,
    start,
    stop,
    captureChunk,
  };
}
