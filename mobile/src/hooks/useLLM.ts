/**
 * Hook for dispatching transcript text to an LLM provider.
 *
 * Manages the LLM provider lifecycle, prompt building, and response state.
 * Supports both one-shot and streaming responses.
 *
 * Usage:
 * ```tsx
 * const { dispatch, responses, isLoading } = useLLM();
 *
 * // Send transcript to the LLM
 * await dispatch('Here is the transcript...');
 * ```
 */

import { useCallback, useRef, useState } from 'react';
import {
  buildPrompt,
  createProvider,
  LLMProvider,
} from '../services/llm';
import { getApiKey } from '../services/storage';
import { generateId } from '../services/storage';
import { LLMProviderName, LLMResponse } from '../types';

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface UseLLMReturn {
  /** All LLM responses received during this session. */
  responses: LLMResponse[];

  /** The most recent response text (for display). */
  latestResponse: string;

  /** Whether an LLM request is currently in progress. */
  isLoading: boolean;

  /** Partial text from a streaming response (updates as chunks arrive). */
  streamingText: string;

  /** Last error from the LLM, or null. */
  error: string | null;

  /**
   * Send transcript text to the configured LLM provider.
   *
   * @param formattedTranscript - The formatted transcript text.
   * @param systemPrompt        - System prompt for the LLM.
   * @param segmentCount        - Number of transcript segments included.
   * @param useStreaming         - Whether to use streaming mode (default: true).
   * @returns The response text, or null on error.
   */
  dispatch: (
    formattedTranscript: string,
    systemPrompt: string,
    segmentCount: number,
    useStreaming?: boolean
  ) => Promise<string | null>;

  /** Clear all responses (e.g. for a new session). */
  clearResponses: () => void;

  /**
   * Update the provider configuration.
   * Call this when the user changes provider/model in settings.
   */
  updateConfig: (
    provider: LLMProviderName,
    model: string
  ) => void;
}

// ---------------------------------------------------------------------------
// Hook implementation
// ---------------------------------------------------------------------------

export function useLLM(
  /** Initial provider name. */
  initialProvider: LLMProviderName = 'anthropic',
  /** Initial model identifier. */
  initialModel: string = 'claude-sonnet-4-20250514'
): UseLLMReturn {
  const [responses, setResponses] = useState<LLMResponse[]>([]);
  const [latestResponse, setLatestResponse] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Current configuration
  const providerNameRef = useRef<LLMProviderName>(initialProvider);
  const modelRef = useRef<string>(initialModel);

  // Cached provider instance
  const providerRef = useRef<LLMProvider | null>(null);

  /**
   * Get or create the LLM provider instance.
   * Fetches the API key from SecureStore.
   */
  const getProvider = useCallback(async (): Promise<LLMProvider | null> => {
    const providerName = providerNameRef.current;
    const model = modelRef.current;

    // Load API key from secure storage
    const apiKey = await getApiKey(providerName);
    if (!apiKey) {
      setError(
        `No API key found for ${providerName}. Set it in Settings.`
      );
      return null;
    }

    // Create a new provider instance
    providerRef.current = createProvider(providerName, apiKey, model);
    return providerRef.current;
  }, []);

  // Dispatch transcript to LLM
  const dispatch = useCallback(
    async (
      formattedTranscript: string,
      systemPrompt: string,
      segmentCount: number,
      useStreaming = true
    ): Promise<string | null> => {
      setError(null);
      setIsLoading(true);
      setStreamingText('');

      try {
        const provider = await getProvider();
        if (!provider) {
          setIsLoading(false);
          return null;
        }

        const prompt = buildPrompt(systemPrompt, formattedTranscript);
        let responseText: string;

        if (useStreaming) {
          // Streaming mode: update UI as chunks arrive
          responseText = await provider.sendStreaming(prompt, (chunk) => {
            setStreamingText((prev) => prev + chunk);
          });
        } else {
          // One-shot mode: wait for complete response
          responseText = await provider.send(prompt);
        }

        // Create response record
        const response: LLMResponse = {
          id: generateId(),
          provider: providerNameRef.current,
          model: modelRef.current,
          text: responseText,
          timestamp: Date.now(),
          segmentCount,
        };

        setResponses((prev) => [...prev, response]);
        setLatestResponse(responseText);
        setStreamingText('');
        setIsLoading(false);

        return responseText;
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : 'LLM request failed';
        setError(msg);
        setIsLoading(false);
        setStreamingText('');
        return null;
      }
    },
    [getProvider]
  );

  // Clear responses
  const clearResponses = useCallback(() => {
    setResponses([]);
    setLatestResponse('');
    setStreamingText('');
    setError(null);
  }, []);

  // Update config
  const updateConfig = useCallback(
    (provider: LLMProviderName, model: string) => {
      providerNameRef.current = provider;
      modelRef.current = model;
      // Clear cached provider so it gets recreated with new config
      providerRef.current = null;
    },
    []
  );

  return {
    responses,
    latestResponse,
    isLoading,
    streamingText,
    error,
    dispatch,
    clearResponses,
    updateConfig,
  };
}
