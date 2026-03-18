/**
 * Storage service for Live Scribe mobile app.
 *
 * Uses two storage backends:
 *   - expo-secure-store:  API keys and other sensitive credentials
 *   - AsyncStorage:       Sessions, settings, and non-sensitive data
 *
 * All functions are async because both backends are async on native.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import {
  AppSettings,
  DEFAULT_SETTINGS,
  LLMProviderName,
  Session,
} from '../types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** AsyncStorage key for app settings. */
const SETTINGS_KEY = '@livescribe/settings';

/** AsyncStorage key prefix for saved sessions. */
const SESSION_PREFIX = '@livescribe/session/';

/** AsyncStorage key that stores the list of session IDs. */
const SESSION_INDEX_KEY = '@livescribe/session_index';

/** SecureStore key pattern for API keys: `@livescribe/apikey/<provider>`. */
const API_KEY_PREFIX = '@livescribe/apikey/';

// ---------------------------------------------------------------------------
// API keys (SecureStore — encrypted on device)
// ---------------------------------------------------------------------------

/**
 * Store an API key securely on the device.
 *
 * @param provider - Which LLM provider this key belongs to.
 * @param apiKey   - The raw API key string.
 */
export async function saveApiKey(
  provider: LLMProviderName,
  apiKey: string
): Promise<void> {
  await SecureStore.setItemAsync(`${API_KEY_PREFIX}${provider}`, apiKey);
}

/**
 * Retrieve an API key from secure storage.
 *
 * @returns The API key string, or `null` if none is stored.
 */
export async function getApiKey(
  provider: LLMProviderName
): Promise<string | null> {
  return SecureStore.getItemAsync(`${API_KEY_PREFIX}${provider}`);
}

/**
 * Delete an API key from secure storage.
 */
export async function deleteApiKey(
  provider: LLMProviderName
): Promise<void> {
  await SecureStore.deleteItemAsync(`${API_KEY_PREFIX}${provider}`);
}

// ---------------------------------------------------------------------------
// App settings (AsyncStorage)
// ---------------------------------------------------------------------------

/**
 * Load app settings, falling back to defaults for any missing fields.
 */
export async function loadSettings(): Promise<AppSettings> {
  try {
    const raw = await AsyncStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    // Merge with defaults so new settings fields are always present
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/**
 * Save app settings. Merges with existing settings so you can pass a
 * partial update.
 */
export async function saveSettings(
  update: Partial<AppSettings>
): Promise<AppSettings> {
  const current = await loadSettings();
  const merged = { ...current, ...update };
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(merged));
  return merged;
}

// ---------------------------------------------------------------------------
// Sessions (AsyncStorage)
// ---------------------------------------------------------------------------

/**
 * Get the list of saved session IDs, most recent first.
 */
async function getSessionIndex(): Promise<string[]> {
  try {
    const raw = await AsyncStorage.getItem(SESSION_INDEX_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Save a session to storage.
 * Adds it to the index and stores the full session data.
 */
export async function saveSession(session: Session): Promise<void> {
  const index = await getSessionIndex();

  // Add to front of index (most recent first), deduplicate
  const updated = [session.id, ...index.filter((id) => id !== session.id)];

  await AsyncStorage.multiSet([
    [SESSION_INDEX_KEY, JSON.stringify(updated)],
    [`${SESSION_PREFIX}${session.id}`, JSON.stringify(session)],
  ]);
}

/**
 * Load a single session by ID.
 */
export async function loadSession(id: string): Promise<Session | null> {
  try {
    const raw = await AsyncStorage.getItem(`${SESSION_PREFIX}${id}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Load all sessions, most recent first.
 * Returns lightweight summaries (transcript and responses are included).
 */
export async function loadAllSessions(): Promise<Session[]> {
  const index = await getSessionIndex();
  if (index.length === 0) return [];

  const keys = index.map((id) => `${SESSION_PREFIX}${id}`);
  const pairs = await AsyncStorage.multiGet(keys);

  const sessions: Session[] = [];
  for (const [, value] of pairs) {
    if (value) {
      try {
        sessions.push(JSON.parse(value));
      } catch {
        // Skip corrupted entries
      }
    }
  }

  // Sort by start time, most recent first
  sessions.sort((a, b) => b.startedAt - a.startedAt);
  return sessions;
}

/**
 * Delete a session by ID.
 */
export async function deleteSession(id: string): Promise<void> {
  const index = await getSessionIndex();
  const updated = index.filter((sid) => sid !== id);

  await AsyncStorage.multiSet([
    [SESSION_INDEX_KEY, JSON.stringify(updated)],
  ]);
  await AsyncStorage.removeItem(`${SESSION_PREFIX}${id}`);
}

/**
 * Delete all sessions. Use with caution.
 */
export async function deleteAllSessions(): Promise<void> {
  const index = await getSessionIndex();
  const keys = index.map((id) => `${SESSION_PREFIX}${id}`);
  keys.push(SESSION_INDEX_KEY);
  await AsyncStorage.multiRemove(keys);
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

/**
 * Generate a simple UUID v4 (good enough for local session IDs).
 */
export function generateId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
