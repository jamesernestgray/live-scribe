/**
 * API service for connecting to the live-scribe Python backend.
 *
 * Provides:
 *   - REST client for all backend HTTP endpoints
 *   - WebSocket client with auto-reconnect for real-time updates
 *   - Configurable base URL (needed since mobile is on a different device)
 *
 * The backend runs FastAPI on the user's machine (e.g. http://192.168.1.x:8765).
 * The mobile app connects over the local network.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import type { ConnectionState } from '../types';

// ---------------------------------------------------------------------------
// Types for backend API responses
// ---------------------------------------------------------------------------

/** Shape of GET /api/status */
export interface ServerStatus {
  recording: boolean;
  model: string;
  segments: number;
}

/** Shape of a transcript segment from the backend */
export interface ServerSegment {
  time: string;
  speaker: string | null;
  text: string;
}

/** Shape of GET /api/transcript */
export interface TranscriptResponse {
  segments: ServerSegment[];
}

/** Shape of GET /api/devices */
export interface DevicesResponse {
  devices: Array<{
    index: number;
    name: string;
    channels: number;
    default: boolean;
  }>;
}

/** Shape of GET /api/presets */
export interface PresetsResponse {
  presets: Record<string, { name: string; prompt: string }>;
  default: string;
}

/** Config body for POST /api/start */
export interface StartConfig {
  model?: string;
  language?: string | null;
  prompt?: string;
  interval?: number;
  context?: boolean;
  context_limit?: number;
  llm?: string;
  llm_model?: string | null;
  stream?: boolean;
  conversation?: boolean;
  diarize?: boolean;
  input_device?: number | null;
  compute?: string;
}

/** Shape of POST /api/settings body (same keys as StartConfig) */
export type SettingsBody = StartConfig;

/** Generic OK response from the backend */
export interface OkResponse {
  ok: boolean;
  dispatch_id?: number;
  error?: string;
  settings?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// WebSocket message types (from backend to client)
// ---------------------------------------------------------------------------

export interface WsSegmentMessage {
  type: 'segment';
  time: string;
  speaker: string | null;
  text: string;
}

export interface WsStatusMessage {
  type: 'status';
  recording: boolean;
  model: string;
  segments: number;
}

export interface WsLlmResponseMessage {
  type: 'llm_response';
  id: number;
  time: string;
  response: string;
}

export interface WsLlmStreamingChunkMessage {
  type: 'llm_streaming_chunk';
  id: number;
  chunk: string;
}

export type WsMessage =
  | WsSegmentMessage
  | WsStatusMessage
  | WsLlmResponseMessage
  | WsLlmStreamingChunkMessage;

// ---------------------------------------------------------------------------
// Server URL persistence
// ---------------------------------------------------------------------------

const SERVER_URL_KEY = '@livescribe/server_url';
const DEFAULT_SERVER_URL = 'http://192.168.1.100:8765';

/**
 * Load the saved server URL from AsyncStorage.
 * Falls back to a sensible default if none is saved.
 */
export async function loadServerUrl(): Promise<string> {
  try {
    const url = await AsyncStorage.getItem(SERVER_URL_KEY);
    return url || DEFAULT_SERVER_URL;
  } catch {
    return DEFAULT_SERVER_URL;
  }
}

/**
 * Save the server URL to AsyncStorage.
 */
export async function saveServerUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(SERVER_URL_KEY, url);
}

// ---------------------------------------------------------------------------
// REST API client
// ---------------------------------------------------------------------------

/**
 * REST client for the live-scribe backend.
 *
 * All methods accept a baseUrl parameter (e.g. "http://192.168.1.5:8765").
 * Callers are responsible for providing the correct URL.
 */
export const api = {
  /**
   * GET /api/status - Get current recording state.
   */
  async getStatus(baseUrl: string): Promise<ServerStatus> {
    const res = await fetch(`${baseUrl}/api/status`);
    if (!res.ok) throw new Error(`Status request failed (${res.status})`);
    return res.json();
  },

  /**
   * POST /api/start - Start recording with optional config.
   */
  async start(baseUrl: string, config?: StartConfig): Promise<OkResponse> {
    const res = await fetch(`${baseUrl}/api/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config ?? {}),
    });
    return res.json();
  },

  /**
   * POST /api/stop - Stop recording.
   */
  async stop(baseUrl: string): Promise<OkResponse> {
    const res = await fetch(`${baseUrl}/api/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    return res.json();
  },

  /**
   * POST /api/dispatch - Trigger LLM dispatch on the server.
   */
  async dispatch(baseUrl: string): Promise<OkResponse> {
    const res = await fetch(`${baseUrl}/api/dispatch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    return res.json();
  },

  /**
   * GET /api/transcript - Get all transcript segments.
   */
  async getTranscript(baseUrl: string): Promise<TranscriptResponse> {
    const res = await fetch(`${baseUrl}/api/transcript`);
    if (!res.ok) throw new Error(`Transcript request failed (${res.status})`);
    return res.json();
  },

  /**
   * GET /api/presets - Get all prompt presets.
   */
  async getPresets(baseUrl: string): Promise<PresetsResponse> {
    const res = await fetch(`${baseUrl}/api/presets`);
    if (!res.ok) throw new Error(`Presets request failed (${res.status})`);
    return res.json();
  },

  /**
   * GET /api/devices - Get available audio input devices.
   */
  async getDevices(baseUrl: string): Promise<DevicesResponse> {
    const res = await fetch(`${baseUrl}/api/devices`);
    if (!res.ok) throw new Error(`Devices request failed (${res.status})`);
    return res.json();
  },

  /**
   * POST /api/settings - Update server-side settings.
   */
  async updateSettings(
    baseUrl: string,
    settings: SettingsBody
  ): Promise<OkResponse> {
    const res = await fetch(`${baseUrl}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    return res.json();
  },

  /**
   * GET /api/transcript/export - Get transcript export URL.
   * Returns the URL string (caller should use Linking or download).
   */
  getExportUrl(
    baseUrl: string,
    format: 'txt' | 'md' | 'json' | 'srt' = 'txt'
  ): string {
    return `${baseUrl}/api/transcript/export?format=${format}`;
  },
};

// ---------------------------------------------------------------------------
// WebSocket client with auto-reconnect
// ---------------------------------------------------------------------------

// Re-export ConnectionState from types for convenience
export type { ConnectionState } from '../types';

export interface WebSocketCallbacks {
  onMessage?: (msg: WsMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: string) => void;
}

/**
 * WebSocket client for real-time updates from the live-scribe backend.
 *
 * Features:
 *   - Auto-reconnect with exponential backoff
 *   - Converts HTTP base URL to WebSocket URL automatically
 *   - JSON message parsing
 *
 * Usage:
 * ```ts
 * const ws = new LiveScribeWebSocket();
 * ws.connect('http://192.168.1.5:8765', {
 *   onMessage: (msg) => console.log(msg),
 *   onOpen: () => console.log('Connected'),
 * });
 * // later:
 * ws.send({ type: 'dispatch' });
 * ws.close();
 * ```
 */
export class LiveScribeWebSocket {
  private ws: WebSocket | null = null;
  private url: string | null = null;
  private callbacks: WebSocketCallbacks = {};
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private intentionallyClosed = false;
  private _state: ConnectionState = 'disconnected';

  /** Current connection state. */
  get state(): ConnectionState {
    return this._state;
  }

  /** Whether the WebSocket is currently connected. */
  get isConnected(): boolean {
    return this._state === 'connected';
  }

  /**
   * Connect to the backend WebSocket.
   *
   * @param baseUrl   - The HTTP base URL (e.g. "http://192.168.1.5:8765").
   *                    Automatically converted to ws:// or wss://.
   * @param callbacks - Message and lifecycle callbacks.
   */
  connect(baseUrl: string, callbacks: WebSocketCallbacks): void {
    this.url = this.httpToWs(baseUrl);
    this.callbacks = callbacks;
    this.intentionallyClosed = false;
    this.reconnectDelay = 1000;
    this.open();
  }

  /**
   * Send a JSON message to the server.
   */
  send(msg: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  /**
   * Close the connection (without auto-reconnect).
   */
  close(): void {
    this.intentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this._state = 'disconnected';
  }

  // -----------------------------------------------------------------------
  // Private
  // -----------------------------------------------------------------------

  private httpToWs(httpUrl: string): string {
    // Convert http://host:port -> ws://host:port/ws
    // Convert https://host:port -> wss://host:port/ws
    let wsUrl = httpUrl.replace(/^http/, 'ws');
    // Remove trailing slash if present
    wsUrl = wsUrl.replace(/\/$/, '');
    return `${wsUrl}/ws`;
  }

  private open(): void {
    if (!this.url) return;

    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this._state = 'connecting';

    try {
      this.ws = new WebSocket(this.url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'WebSocket creation failed';
      this.callbacks.onError?.(msg);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this._state = 'connected';
      this.reconnectDelay = 1000;
      this.callbacks.onOpen?.();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as WsMessage;
        this.callbacks.onMessage?.(msg);
      } catch {
        // Skip malformed messages
      }
    };

    this.ws.onclose = () => {
      this._state = 'disconnected';
      this.callbacks.onClose?.();
      if (!this.intentionallyClosed) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after this; avoid duplicate error handling
      this.callbacks.onError?.('WebSocket connection error');
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay
      );
    }, this.reconnectDelay);
  }
}
