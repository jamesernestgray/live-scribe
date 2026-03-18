/**
 * Tests for the storage service.
 *
 * Verifies that:
 *   - API keys are stored/retrieved via SecureStore
 *   - Settings load with defaults for missing fields
 *   - Settings save merges with existing settings
 *   - Sessions are saved, loaded, and deleted correctly
 *   - generateId produces valid UUID-like strings
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import {
  saveApiKey,
  getApiKey,
  deleteApiKey,
  loadSettings,
  saveSettings,
  saveSession,
  loadAllSessions,
  deleteSession,
  generateId,
} from '../../src/services/storage';
import { DEFAULT_SETTINGS, Session } from '../../src/types';

// ---------------------------------------------------------------------------
// Reset mocks before each test
// ---------------------------------------------------------------------------

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
// API Keys (SecureStore)
// ---------------------------------------------------------------------------

describe('API Key storage', () => {
  it('saves an API key via SecureStore', async () => {
    await saveApiKey('anthropic', 'sk-test-key');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
      '@livescribe/apikey/anthropic',
      'sk-test-key'
    );
  });

  it('retrieves an API key via SecureStore', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('sk-test-key');

    const key = await getApiKey('openai');
    expect(SecureStore.getItemAsync).toHaveBeenCalledWith(
      '@livescribe/apikey/openai'
    );
    expect(key).toBe('sk-test-key');
  });

  it('returns null when no key is stored', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce(null);

    const key = await getApiKey('gemini');
    expect(key).toBeNull();
  });

  it('deletes an API key', async () => {
    await deleteApiKey('anthropic');
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
      '@livescribe/apikey/anthropic'
    );
  });
});

// ---------------------------------------------------------------------------
// Settings (AsyncStorage)
// ---------------------------------------------------------------------------

describe('Settings storage', () => {
  it('returns defaults when no settings are stored', async () => {
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(null);

    const settings = await loadSettings();
    expect(settings).toEqual(DEFAULT_SETTINGS);
  });

  it('merges saved settings with defaults', async () => {
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
      JSON.stringify({ llmProvider: 'openai' })
    );

    const settings = await loadSettings();
    expect(settings.llmProvider).toBe('openai');
    // Other fields should have defaults
    expect(settings.mode).toBe(DEFAULT_SETTINGS.mode);
    expect(settings.systemPrompt).toBe(DEFAULT_SETTINGS.systemPrompt);
  });

  it('saves settings by merging with existing', async () => {
    // loadSettings is called internally — return existing settings
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
      JSON.stringify({ llmProvider: 'anthropic', llmModel: 'claude-sonnet-4-20250514' })
    );

    const result = await saveSettings({ llmModel: 'gpt-4o' });

    expect(result.llmModel).toBe('gpt-4o');
    // Should have called setItem
    expect(AsyncStorage.setItem).toHaveBeenCalledWith(
      '@livescribe/settings',
      expect.any(String)
    );
  });

  it('handles corrupted settings gracefully', async () => {
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce('not valid json{{{');

    const settings = await loadSettings();
    expect(settings).toEqual(DEFAULT_SETTINGS);
  });
});

// ---------------------------------------------------------------------------
// Sessions (AsyncStorage)
// ---------------------------------------------------------------------------

describe('Session storage', () => {
  const mockSession: Session = {
    id: 'test-session-1',
    title: 'Test Session',
    startedAt: Date.now() - 60000,
    endedAt: Date.now(),
    durationMs: 60000,
    transcript: [
      {
        id: 'seg-1',
        text: 'Hello world',
        timestamp: Date.now(),
      },
    ],
    llmResponses: [],
  };

  it('saves a session and updates the index', async () => {
    // getSessionIndex returns empty
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(null);

    await saveSession(mockSession);

    expect(AsyncStorage.multiSet).toHaveBeenCalledWith([
      ['@livescribe/session_index', expect.stringContaining('test-session-1')],
      [
        '@livescribe/session/test-session-1',
        expect.any(String),
      ],
    ]);
  });

  it('loads all sessions sorted by date', async () => {
    const session1 = { ...mockSession, id: 's1', startedAt: 1000 };
    const session2 = { ...mockSession, id: 's2', startedAt: 2000 };

    // getSessionIndex
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
      JSON.stringify(['s1', 's2'])
    );

    // multiGet returns session data
    (AsyncStorage.multiGet as jest.Mock).mockResolvedValueOnce([
      ['@livescribe/session/s1', JSON.stringify(session1)],
      ['@livescribe/session/s2', JSON.stringify(session2)],
    ]);

    const sessions = await loadAllSessions();
    expect(sessions).toHaveLength(2);
    // Most recent first
    expect(sessions[0].id).toBe('s2');
    expect(sessions[1].id).toBe('s1');
  });

  it('deletes a session and updates the index', async () => {
    // getSessionIndex
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
      JSON.stringify(['s1', 's2'])
    );

    await deleteSession('s1');

    // Should update index without s1
    expect(AsyncStorage.multiSet).toHaveBeenCalledWith([
      ['@livescribe/session_index', JSON.stringify(['s2'])],
    ]);
    // Should remove session data
    expect(AsyncStorage.removeItem).toHaveBeenCalledWith(
      '@livescribe/session/s1'
    );
  });
});

// ---------------------------------------------------------------------------
// generateId
// ---------------------------------------------------------------------------

describe('generateId', () => {
  it('generates a UUID-like string', () => {
    const id = generateId();
    // Should match UUID v4 format
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    );
  });

  it('generates unique IDs', () => {
    const ids = new Set(Array.from({ length: 100 }, () => generateId()));
    expect(ids.size).toBe(100);
  });
});
