/**
 * Core type definitions for Live Scribe mobile app.
 *
 * These interfaces mirror the data structures used by the Python
 * live_scribe.py backend, adapted for the mobile/TypeScript world.
 */

// ---------------------------------------------------------------------------
// Transcription
// ---------------------------------------------------------------------------

/** A single transcription segment produced by Whisper or received via WebSocket. */
export interface TranscriptSegment {
  /** Unique identifier (UUID v4). */
  id: string;
  /** Transcribed text for this segment. */
  text: string;
  /** Wall-clock timestamp (epoch milliseconds) when the segment was captured. */
  timestamp: number;
  /** Speaker label if diarization is active (e.g. "SPEAKER_00"). */
  speaker?: string;
}

/** Full transcript: an ordered list of segments. */
export type Transcript = TranscriptSegment[];

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------

/** Supported LLM provider names (for standalone mode). */
export type LLMProviderName = 'anthropic' | 'openai' | 'gemini';

/**
 * Provider names that can appear on an LLMResponse.
 * Includes 'remote' for responses received from the backend server.
 */
export type LLMResponseProvider = LLMProviderName | 'remote';

/** Configuration for a single LLM provider. */
export interface LLMConfig {
  provider: LLMProviderName;
  /** The model identifier (e.g. "claude-sonnet-4-20250514", "gpt-4o", "gemini-2.0-flash"). */
  model: string;
  /** API key — stored in SecureStore, loaded at runtime. */
  apiKey: string;
}

/** A response received from an LLM dispatch. */
export interface LLMResponse {
  id: string;
  /** Which provider generated this response. */
  provider: LLMResponseProvider;
  model: string;
  /** The full response text. */
  text: string;
  /** Epoch ms when the response was received. */
  timestamp: number;
  /** How many transcript segments were included in the prompt. */
  segmentCount: number;
}

// ---------------------------------------------------------------------------
// Sessions (persisted history)
// ---------------------------------------------------------------------------

/** A saved recording/transcription session. */
export interface Session {
  id: string;
  /** Human-readable title (auto-generated or user-edited). */
  title: string;
  /** Epoch ms when the session started. */
  startedAt: number;
  /** Epoch ms when the session ended (0 if still active). */
  endedAt: number;
  /** Total recording duration in milliseconds. */
  durationMs: number;
  /** All transcript segments captured during the session. */
  transcript: Transcript;
  /** All LLM responses generated during the session. */
  llmResponses: LLMResponse[];
}

// ---------------------------------------------------------------------------
// App settings
// ---------------------------------------------------------------------------

/** Operating mode for the app. */
export type AppMode = 'standalone' | 'remote';

/** Persisted app settings (stored in AsyncStorage). */
export interface AppSettings {
  /** Current operating mode. */
  mode: AppMode;

  /** Selected LLM provider. */
  llmProvider: LLMProviderName;
  /** Selected model identifier. */
  llmModel: string;
  /** Custom system prompt for LLM analysis. */
  systemPrompt: string;

  /**
   * For remote mode: the live-scribe server HTTP URL.
   * E.g. "http://192.168.1.5:8765"
   * The WebSocket URL is derived automatically (ws://host:port/ws).
   */
  serverUrl: string;

  /** Audio chunk duration in seconds (how often Whisper processes audio). */
  chunkDurationSec: number;
  /** Auto-dispatch interval in seconds (0 = manual only). */
  autoDispatchIntervalSec: number;
}

/** Sensible defaults for new installs. */
export const DEFAULT_SETTINGS: AppSettings = {
  mode: 'standalone',
  llmProvider: 'anthropic',
  llmModel: 'claude-sonnet-4-20250514',
  systemPrompt:
    'You are a real-time AI collaborator listening to a live audio transcription. ' +
    'Engage with what\'s being said: answer questions, provide analysis, ' +
    'offer relevant expertise, and surface useful context. ' +
    'If the speaker asks something, answer it directly. ' +
    'If they\'re discussing a design or problem, contribute meaningfully. ' +
    'Be concise and direct.',
  serverUrl: 'http://192.168.1.100:8765',
  chunkDurationSec: 5,
  autoDispatchIntervalSec: 60,
};

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

/** Root tab navigator param list. */
export type RootTabParamList = {
  Home: undefined;
  History: undefined;
  Settings: undefined;
};

// ---------------------------------------------------------------------------
// Recording state
// ---------------------------------------------------------------------------

/** High-level recording status shown in the UI. */
export type RecordingStatus = 'idle' | 'recording' | 'paused' | 'processing';

// ---------------------------------------------------------------------------
// Remote server connection
// ---------------------------------------------------------------------------

/** WebSocket connection state for the remote server. */
export type ConnectionState = 'disconnected' | 'connecting' | 'connected';
