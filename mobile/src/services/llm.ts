/**
 * LLM service for Live Scribe mobile app.
 *
 * Provides a unified interface for dispatching transcript text to
 * multiple LLM providers (Anthropic Claude, OpenAI GPT, Google Gemini).
 *
 * Each provider implements the LLMProvider interface, which supports
 * both one-shot and streaming responses.
 *
 * Usage:
 * ```ts
 * const provider = createProvider('anthropic', 'sk-...', 'claude-sonnet-4-20250514');
 * const response = await provider.send('Analyze this transcript...');
 * // or streaming:
 * const full = await provider.sendStreaming(prompt, (chunk) => {
 *   console.log('Partial:', chunk);
 * });
 * ```
 */

import { LLMProviderName } from '../types';

// ---------------------------------------------------------------------------
// Provider interface
// ---------------------------------------------------------------------------

/**
 * Common interface that all LLM providers implement.
 * This allows the rest of the app to be provider-agnostic.
 */
export interface LLMProvider {
  /** Display name of the provider (e.g. "Anthropic Claude"). */
  name: string;

  /**
   * Send a prompt and wait for the complete response.
   *
   * @param prompt - The full prompt text (system prompt + transcript).
   * @returns The complete response text.
   */
  send(prompt: string): Promise<string>;

  /**
   * Send a prompt and stream the response in chunks.
   *
   * @param prompt  - The full prompt text.
   * @param onChunk - Called with each text chunk as it arrives.
   * @returns The complete response text (concatenation of all chunks).
   */
  sendStreaming(
    prompt: string,
    onChunk: (text: string) => void
  ): Promise<string>;
}

// ---------------------------------------------------------------------------
// Anthropic Claude
// ---------------------------------------------------------------------------

/**
 * Anthropic Claude provider.
 * Uses the Messages API (https://docs.anthropic.com/en/api/messages).
 */
export class AnthropicProvider implements LLMProvider {
  readonly name = 'Anthropic Claude';
  private apiKey: string;
  private model: string;

  constructor(apiKey: string, model = 'claude-sonnet-4-20250514') {
    this.apiKey = apiKey;
    this.model = model;
  }

  async send(prompt: string): Promise<string> {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: 4096,
        messages: [
          {
            role: 'user',
            content: prompt,
          },
        ],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `Anthropic API error (${response.status}): ${errorText}`
      );
    }

    const data = await response.json();
    // The Messages API returns content blocks; extract text from the first one
    const textBlock = data.content?.find(
      (block: { type: string }) => block.type === 'text'
    );
    return textBlock?.text ?? '';
  }

  async sendStreaming(
    prompt: string,
    onChunk: (text: string) => void
  ): Promise<string> {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': this.apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: 4096,
        stream: true,
        messages: [
          {
            role: 'user',
            content: prompt,
          },
        ],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `Anthropic API error (${response.status}): ${errorText}`
      );
    }

    // Parse SSE stream
    return this.parseSSEStream(response, (event) => {
      if (event.type === 'content_block_delta') {
        const delta = event.delta;
        if (delta?.type === 'text_delta' && delta.text) {
          onChunk(delta.text);
          return delta.text;
        }
      }
      return '';
    });
  }

  /**
   * Parse a Server-Sent Events stream from the Anthropic API.
   * Generic helper used by sendStreaming.
   */
  private async parseSSEStream(
    response: Response,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    processEvent: (event: any) => string
  ): Promise<string> {
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // Keep the last potentially incomplete line in the buffer
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6);
          if (jsonStr === '[DONE]') continue;
          try {
            const event = JSON.parse(jsonStr);
            fullText += processEvent(event);
          } catch {
            // Skip malformed JSON lines
          }
        }
      }
    }

    return fullText;
  }
}

// ---------------------------------------------------------------------------
// OpenAI GPT
// ---------------------------------------------------------------------------

/**
 * OpenAI provider.
 * Uses the Chat Completions API.
 */
export class OpenAIProvider implements LLMProvider {
  readonly name = 'OpenAI';
  private apiKey: string;
  private model: string;

  constructor(apiKey: string, model = 'gpt-4o') {
    this.apiKey = apiKey;
    this.model = model;
  }

  async send(prompt: string): Promise<string> {
    const response = await fetch(
      'https://api.openai.com/v1/chat/completions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({
          model: this.model,
          messages: [
            {
              role: 'user',
              content: prompt,
            },
          ],
          max_tokens: 4096,
        }),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `OpenAI API error (${response.status}): ${errorText}`
      );
    }

    const data = await response.json();
    return data.choices?.[0]?.message?.content ?? '';
  }

  async sendStreaming(
    prompt: string,
    onChunk: (text: string) => void
  ): Promise<string> {
    const response = await fetch(
      'https://api.openai.com/v1/chat/completions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({
          model: this.model,
          messages: [
            {
              role: 'user',
              content: prompt,
            },
          ],
          max_tokens: 4096,
          stream: true,
        }),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `OpenAI API error (${response.status}): ${errorText}`
      );
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6);
          if (jsonStr === '[DONE]') continue;
          try {
            const event = JSON.parse(jsonStr);
            const content = event.choices?.[0]?.delta?.content;
            if (content) {
              onChunk(content);
              fullText += content;
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    }

    return fullText;
  }
}

// ---------------------------------------------------------------------------
// Google Gemini
// ---------------------------------------------------------------------------

/**
 * Google Gemini provider.
 * Uses the Generative Language API.
 */
export class GeminiProvider implements LLMProvider {
  readonly name = 'Google Gemini';
  private apiKey: string;
  private model: string;

  constructor(apiKey: string, model = 'gemini-2.0-flash') {
    this.apiKey = apiKey;
    this.model = model;
  }

  async send(prompt: string): Promise<string> {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        contents: [
          {
            parts: [{ text: prompt }],
          },
        ],
        generationConfig: {
          maxOutputTokens: 4096,
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `Gemini API error (${response.status}): ${errorText}`
      );
    }

    const data = await response.json();
    return (
      data.candidates?.[0]?.content?.parts?.[0]?.text ?? ''
    );
  }

  async sendStreaming(
    prompt: string,
    onChunk: (text: string) => void
  ): Promise<string> {
    // Gemini uses streamGenerateContent with alt=sse
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:streamGenerateContent?alt=sse&key=${this.apiKey}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        contents: [
          {
            parts: [{ text: prompt }],
          },
        ],
        generationConfig: {
          maxOutputTokens: 4096,
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `Gemini API error (${response.status}): ${errorText}`
      );
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const jsonStr = line.slice(6);
          try {
            const event = JSON.parse(jsonStr);
            const text =
              event.candidates?.[0]?.content?.parts?.[0]?.text;
            if (text) {
              onChunk(text);
              fullText += text;
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    }

    return fullText;
  }
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create an LLM provider instance by name.
 *
 * @param providerName - Which provider to use.
 * @param apiKey       - The API key for that provider.
 * @param model        - The model identifier (provider-specific).
 * @returns A configured LLMProvider instance.
 *
 * @example
 * ```ts
 * const provider = createProvider('anthropic', 'sk-ant-...', 'claude-sonnet-4-20250514');
 * const response = await provider.send('Hello!');
 * ```
 */
export function createProvider(
  providerName: LLMProviderName,
  apiKey: string,
  model?: string
): LLMProvider {
  switch (providerName) {
    case 'anthropic':
      return new AnthropicProvider(apiKey, model);
    case 'openai':
      return new OpenAIProvider(apiKey, model);
    case 'gemini':
      return new GeminiProvider(apiKey, model);
    default:
      throw new Error(`Unknown LLM provider: ${providerName}`);
  }
}

// ---------------------------------------------------------------------------
// Prompt builder
// ---------------------------------------------------------------------------

/**
 * Build a prompt for the LLM from a system prompt and transcript segments.
 * Mirrors the format used by the Python ClaudeDispatcher.
 *
 * @param systemPrompt - The system-level instruction.
 * @param transcript   - Formatted transcript text.
 * @returns The complete prompt string.
 */
export function buildPrompt(
  systemPrompt: string,
  transcript: string
): string {
  return [
    systemPrompt,
    '',
    '--- TRANSCRIPT ---',
    transcript,
    '--- END ---',
  ].join('\n');
}
