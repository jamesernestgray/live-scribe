/**
 * Hook for managing the remote server connection in the Live Scribe app.
 *
 * When the app is in "remote" mode, this hook:
 *   - Connects to the backend via WebSocket for real-time updates
 *   - Receives transcript segments, LLM responses, and status changes
 *   - Provides methods to start/stop recording and dispatch via REST API
 *   - Tracks connection state for the UI
 *
 * Usage:
 * ```tsx
 * const remote = useRemoteServer(serverUrl);
 * // remote.segments, remote.llmResponses, remote.isRecording, etc.
 * // remote.startRecording(), remote.stopRecording(), remote.dispatch()
 * ```
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api,
  ConnectionState,
  LiveScribeWebSocket,
  ServerStatus,
  StartConfig,
  WsLlmResponseMessage,
  WsLlmStreamingChunkMessage,
  WsMessage,
  WsSegmentMessage,
} from '../services/api';
import { TranscriptSegment } from '../types';
import { generateId } from '../services/storage';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** An LLM response received from the remote server. */
export interface RemoteLLMResponse {
  id: number;
  time: string;
  response: string;
}

export interface UseRemoteServerReturn {
  /** Current WebSocket connection state. */
  connectionState: ConnectionState;

  /** Whether connected to the server. */
  isConnected: boolean;

  /** Whether the server is currently recording. */
  isRecording: boolean;

  /** Server status (model, segment count). */
  serverStatus: ServerStatus | null;

  /** Transcript segments received via WebSocket. */
  segments: TranscriptSegment[];

  /** LLM responses received via WebSocket. */
  llmResponses: RemoteLLMResponse[];

  /** Current streaming text (from llm_streaming_chunk messages). */
  streamingText: string;

  /** Current streaming dispatch ID. */
  streamingId: number | null;

  /** Whether an LLM dispatch is in progress. */
  isDispatching: boolean;

  /** Last error message, or null. */
  error: string | null;

  /** Connect to the server (called when entering remote mode). */
  connect: (serverUrl: string) => void;

  /** Disconnect from the server. */
  disconnect: () => void;

  /** Start recording on the server. */
  startRecording: (config?: StartConfig) => Promise<boolean>;

  /** Stop recording on the server. */
  stopRecording: () => Promise<boolean>;

  /** Trigger LLM dispatch on the server. */
  dispatch: () => Promise<boolean>;

  /** Clear local segment and response state. */
  clearState: () => void;

  /** Test connection to a server URL (returns true if reachable). */
  testConnection: (serverUrl: string) => Promise<boolean>;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useRemoteServer(): UseRemoteServerReturn {
  const [connectionState, setConnectionState] =
    useState<ConnectionState>('disconnected');
  const [isRecording, setIsRecording] = useState(false);
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [llmResponses, setLlmResponses] = useState<RemoteLLMResponse[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [streamingId, setStreamingId] = useState<number | null>(null);
  const [isDispatching, setIsDispatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Persist the server URL for API calls
  const serverUrlRef = useRef<string>('');

  // WebSocket instance (persists across renders)
  const wsRef = useRef<LiveScribeWebSocket>(new LiveScribeWebSocket());

  // Streaming accumulator ref (avoids stale closure in callbacks)
  const streamingTextRef = useRef('');
  const streamingIdRef = useRef<number | null>(null);

  // -----------------------------------------------------------------------
  // WebSocket message handler
  // -----------------------------------------------------------------------
  const handleMessage = useCallback((msg: WsMessage) => {
    switch (msg.type) {
      case 'segment': {
        const segMsg = msg as WsSegmentMessage;
        const segment: TranscriptSegment = {
          id: generateId(),
          text: segMsg.text,
          timestamp: Date.now(),
          speaker: segMsg.speaker ?? undefined,
          // Store the formatted time from the server for display
        };
        setSegments((prev) => [...prev, segment]);
        break;
      }

      case 'status': {
        const status: ServerStatus = {
          recording: msg.recording,
          model: msg.model,
          segments: msg.segments,
        };
        setServerStatus(status);
        setIsRecording(msg.recording);
        break;
      }

      case 'llm_response': {
        const respMsg = msg as WsLlmResponseMessage;
        const resp: RemoteLLMResponse = {
          id: respMsg.id,
          time: respMsg.time,
          response: respMsg.response,
        };
        setLlmResponses((prev) => [...prev, resp]);

        // If this was the streaming response, finalize it
        if (streamingIdRef.current === respMsg.id) {
          setStreamingText('');
          setStreamingId(null);
          streamingTextRef.current = '';
          streamingIdRef.current = null;
        }
        setIsDispatching(false);
        break;
      }

      case 'llm_streaming_chunk': {
        const chunkMsg = msg as WsLlmStreamingChunkMessage;
        if (streamingIdRef.current === null) {
          streamingIdRef.current = chunkMsg.id;
          setStreamingId(chunkMsg.id);
        }
        streamingTextRef.current += chunkMsg.chunk;
        setStreamingText(streamingTextRef.current);
        break;
      }
    }
  }, []);

  // -----------------------------------------------------------------------
  // Connection management
  // -----------------------------------------------------------------------
  const connect = useCallback(
    (serverUrl: string) => {
      setError(null);
      serverUrlRef.current = serverUrl;
      setConnectionState('connecting');

      wsRef.current.connect(serverUrl, {
        onMessage: handleMessage,
        onOpen: () => {
          setConnectionState('connected');
          setError(null);
        },
        onClose: () => {
          setConnectionState('disconnected');
        },
        onError: (errMsg) => {
          setError(errMsg);
        },
      });
    },
    [handleMessage]
  );

  const disconnect = useCallback(() => {
    wsRef.current.close();
    setConnectionState('disconnected');
  }, []);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      wsRef.current.close();
    };
  }, []);

  // -----------------------------------------------------------------------
  // REST API actions
  // -----------------------------------------------------------------------
  const startRecording = useCallback(
    async (config?: StartConfig): Promise<boolean> => {
      const baseUrl = serverUrlRef.current;
      if (!baseUrl) {
        setError('No server URL configured');
        return false;
      }

      try {
        setError(null);
        const result = await api.start(baseUrl, config);
        if (result.error) {
          setError(result.error);
          return false;
        }
        return true;
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : 'Failed to start recording';
        setError(msg);
        return false;
      }
    },
    []
  );

  const stopRecording = useCallback(async (): Promise<boolean> => {
    const baseUrl = serverUrlRef.current;
    if (!baseUrl) {
      setError('No server URL configured');
      return false;
    }

    try {
      setError(null);
      const result = await api.stop(baseUrl);
      if (result.error) {
        setError(result.error);
        return false;
      }
      return true;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Failed to stop recording';
      setError(msg);
      return false;
    }
  }, []);

  const dispatch = useCallback(async (): Promise<boolean> => {
    const baseUrl = serverUrlRef.current;
    if (!baseUrl) {
      setError('No server URL configured');
      return false;
    }

    try {
      setError(null);
      setIsDispatching(true);
      setStreamingText('');
      streamingTextRef.current = '';
      streamingIdRef.current = null;

      const result = await api.dispatch(baseUrl);
      if (result.error) {
        setError(result.error);
        setIsDispatching(false);
        return false;
      }

      // Track the dispatch ID for streaming
      if (result.dispatch_id !== undefined) {
        streamingIdRef.current = result.dispatch_id;
        setStreamingId(result.dispatch_id);
      }
      return true;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Failed to dispatch';
      setError(msg);
      setIsDispatching(false);
      return false;
    }
  }, []);

  const clearState = useCallback(() => {
    setSegments([]);
    setLlmResponses([]);
    setStreamingText('');
    setStreamingId(null);
    setIsDispatching(false);
    setError(null);
    streamingTextRef.current = '';
    streamingIdRef.current = null;
  }, []);

  const testConnection = useCallback(
    async (serverUrl: string): Promise<boolean> => {
      try {
        await api.getStatus(serverUrl);
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  return {
    connectionState,
    isConnected: connectionState === 'connected',
    isRecording,
    serverStatus,
    segments,
    llmResponses,
    streamingText,
    streamingId,
    isDispatching,
    error,
    connect,
    disconnect,
    startRecording,
    stopRecording,
    dispatch,
    clearState,
    testConnection,
  };
}
