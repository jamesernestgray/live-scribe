/**
 * Tests for the LLM service.
 *
 * Verifies that each provider (Anthropic, OpenAI, Gemini) correctly:
 *   - Sends API requests with proper headers and body format
 *   - Parses successful responses
 *   - Throws meaningful errors on API failures
 *   - The factory function creates the right provider
 *   - The prompt builder formats transcripts correctly
 */

import {
  AnthropicProvider,
  OpenAIProvider,
  GeminiProvider,
  createProvider,
  buildPrompt,
} from '../../src/services/llm';

// ---------------------------------------------------------------------------
// Mock fetch globally
// ---------------------------------------------------------------------------

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

// ---------------------------------------------------------------------------
// AnthropicProvider
// ---------------------------------------------------------------------------

describe('AnthropicProvider', () => {
  const provider = new AnthropicProvider('test-api-key', 'claude-sonnet-4-20250514');

  it('sends a request with correct headers and body', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        content: [{ type: 'text', text: 'Hello from Claude' }],
      }),
    });

    const result = await provider.send('Test prompt');

    expect(result).toBe('Hello from Claude');
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.anthropic.com/v1/messages',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'x-api-key': 'test-api-key',
          'anthropic-version': '2023-06-01',
          'Content-Type': 'application/json',
        }),
      })
    );

    // Verify body contains the prompt
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.model).toBe('claude-sonnet-4-20250514');
    expect(body.messages[0].content).toBe('Test prompt');
  });

  it('throws on API error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: async () => 'Unauthorized',
    });

    await expect(provider.send('Test')).rejects.toThrow(
      'Anthropic API error (401): Unauthorized'
    );
  });

  it('handles empty content blocks', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ content: [] }),
    });

    const result = await provider.send('Test');
    expect(result).toBe('');
  });
});

// ---------------------------------------------------------------------------
// OpenAIProvider
// ---------------------------------------------------------------------------

describe('OpenAIProvider', () => {
  const provider = new OpenAIProvider('test-openai-key', 'gpt-4o');

  it('sends a request with correct format', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        choices: [{ message: { content: 'Hello from GPT' } }],
      }),
    });

    const result = await provider.send('Test prompt');

    expect(result).toBe('Hello from GPT');
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.openai.com/v1/chat/completions',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-openai-key',
        }),
      })
    );
  });

  it('throws on API error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 429,
      text: async () => 'Rate limited',
    });

    await expect(provider.send('Test')).rejects.toThrow(
      'OpenAI API error (429): Rate limited'
    );
  });
});

// ---------------------------------------------------------------------------
// GeminiProvider
// ---------------------------------------------------------------------------

describe('GeminiProvider', () => {
  const provider = new GeminiProvider('test-gemini-key', 'gemini-2.0-flash');

  it('sends a request with correct format', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        candidates: [
          { content: { parts: [{ text: 'Hello from Gemini' }] } },
        ],
      }),
    });

    const result = await provider.send('Test prompt');

    expect(result).toBe('Hello from Gemini');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('generativelanguage.googleapis.com'),
      expect.objectContaining({
        method: 'POST',
      })
    );

    // Verify API key is in the URL
    expect(mockFetch.mock.calls[0][0]).toContain('key=test-gemini-key');
  });

  it('throws on API error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      text: async () => 'Bad request',
    });

    await expect(provider.send('Test')).rejects.toThrow(
      'Gemini API error (400): Bad request'
    );
  });
});

// ---------------------------------------------------------------------------
// createProvider factory
// ---------------------------------------------------------------------------

describe('createProvider', () => {
  it('creates AnthropicProvider', () => {
    const p = createProvider('anthropic', 'key', 'model');
    expect(p.name).toBe('Anthropic Claude');
  });

  it('creates OpenAIProvider', () => {
    const p = createProvider('openai', 'key', 'model');
    expect(p.name).toBe('OpenAI');
  });

  it('creates GeminiProvider', () => {
    const p = createProvider('gemini', 'key', 'model');
    expect(p.name).toBe('Google Gemini');
  });

  it('throws for unknown provider', () => {
    expect(() =>
      createProvider('unknown' as any, 'key')
    ).toThrow('Unknown LLM provider: unknown');
  });
});

// ---------------------------------------------------------------------------
// buildPrompt
// ---------------------------------------------------------------------------

describe('buildPrompt', () => {
  it('formats system prompt and transcript correctly', () => {
    const result = buildPrompt(
      'You are a helpful assistant.',
      '[12:00:00] Hello world'
    );

    expect(result).toContain('You are a helpful assistant.');
    expect(result).toContain('--- TRANSCRIPT ---');
    expect(result).toContain('[12:00:00] Hello world');
    expect(result).toContain('--- END ---');
  });
});
