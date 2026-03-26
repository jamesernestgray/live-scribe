/**
 * SettingsScreen — configure LLM provider, API keys, and app options.
 *
 * Sections:
 *   1. Operating Mode: Standalone or Remote
 *   2. Remote Server: Address, connection test, status indicator
 *   3. LLM Provider: Anthropic, OpenAI, or Gemini (standalone mode)
 *   4. API Keys: Securely stored per provider (standalone mode)
 *   5. Model Selection: Provider-specific model choices (standalone mode)
 *   6. System Prompt: Customizable LLM instruction
 *   7. Audio Settings: Chunk duration, auto-dispatch interval
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  AppSettings,
  ConnectionState,
  DEFAULT_SETTINGS,
  LLMProviderName,
} from '../types';
import {
  deleteApiKey,
  getApiKey,
  loadSettings,
  saveApiKey,
  saveSettings,
} from '../services/storage';
import { api } from '../services/api';
import { borderRadius, colors, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Provider options
// ---------------------------------------------------------------------------

const PROVIDER_OPTIONS: {
  name: LLMProviderName;
  label: string;
  models: string[];
}[] = [
  {
    name: 'anthropic',
    label: 'Anthropic Claude',
    models: ['claude-sonnet-4-20250514', 'claude-opus-4-20250514', 'claude-haiku-35-20241022'],
  },
  {
    name: 'openai',
    label: 'OpenAI',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
  },
  {
    name: 'gemini',
    label: 'Google Gemini',
    models: ['gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-2.0-flash-lite'],
  },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SettingsScreen() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);

  // API key input state (one per provider)
  const [apiKeys, setApiKeys] = useState<Record<LLMProviderName, string>>({
    anthropic: '',
    openai: '',
    gemini: '',
  });

  // Track which API keys are saved
  const [savedKeys, setSavedKeys] = useState<Record<LLMProviderName, boolean>>({
    anthropic: false,
    openai: false,
    gemini: false,
  });

  // Server connection testing state
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionState>('disconnected');
  const [isTesting, setIsTesting] = useState(false);
  const [serverUrlInput, setServerUrlInput] = useState('');

  // Load settings and check for saved keys on mount
  useEffect(() => {
    async function load() {
      const s = await loadSettings();
      setSettings(s);
      setServerUrlInput(s.serverUrl);

      // Check which providers have saved API keys
      const providers: LLMProviderName[] = ['anthropic', 'openai', 'gemini'];
      const saved: Record<LLMProviderName, boolean> = {
        anthropic: false,
        openai: false,
        gemini: false,
      };
      for (const p of providers) {
        const key = await getApiKey(p);
        saved[p] = !!key;
      }
      setSavedKeys(saved);

      // Auto-test connection if in remote mode
      if (s.mode === 'remote' && s.serverUrl) {
        testServerConnection(s.serverUrl);
      }
    }
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Save a single setting
  const updateSetting = useCallback(
    async (update: Partial<AppSettings>) => {
      const merged = await saveSettings(update);
      setSettings(merged);
    },
    []
  );

  // Save an API key
  const handleSaveApiKey = useCallback(
    async (provider: LLMProviderName) => {
      const key = apiKeys[provider].trim();
      if (!key) {
        Alert.alert('Empty Key', 'Please enter an API key.');
        return;
      }

      await saveApiKey(provider, key);
      setSavedKeys((prev) => ({ ...prev, [provider]: true }));
      setApiKeys((prev) => ({ ...prev, [provider]: '' }));
      Alert.alert('Saved', `${provider} API key saved securely.`);
    },
    [apiKeys]
  );

  // Delete an API key
  const handleDeleteApiKey = useCallback(
    async (provider: LLMProviderName) => {
      Alert.alert(
        'Delete API Key',
        `Remove the ${provider} API key?`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Delete',
            style: 'destructive',
            onPress: async () => {
              await deleteApiKey(provider);
              setSavedKeys((prev) => ({ ...prev, [provider]: false }));
            },
          },
        ]
      );
    },
    []
  );

  // Test server connection
  const testServerConnection = useCallback(
    async (url: string) => {
      if (!url.trim()) {
        Alert.alert('Empty URL', 'Please enter a server address.');
        return;
      }

      setIsTesting(true);
      setConnectionStatus('connecting');

      try {
        const status = await api.getStatus(url);
        if (status && typeof status.recording === 'boolean') {
          setConnectionStatus('connected');
          Alert.alert(
            'Connected',
            `Server is reachable.\n` +
              `Recording: ${status.recording ? 'Yes' : 'No'}\n` +
              `Model: ${status.model}\n` +
              `Segments: ${status.segments}`
          );
        } else {
          setConnectionStatus('disconnected');
          Alert.alert('Error', 'Server responded but with unexpected data.');
        }
      } catch {
        setConnectionStatus('disconnected');
        Alert.alert(
          'Connection Failed',
          'Could not reach the server. Make sure:\n\n' +
            '1. The live-scribe server is running\n' +
            '2. Your phone is on the same network\n' +
            '3. The IP address and port are correct\n' +
            '4. The server is bound to 0.0.0.0 (not 127.0.0.1)'
        );
      } finally {
        setIsTesting(false);
      }
    },
    []
  );

  // Save server URL and test connection
  const handleSaveServerUrl = useCallback(async () => {
    const url = serverUrlInput.trim().replace(/\/+$/, ''); // Remove trailing slashes
    if (!url) {
      Alert.alert('Empty URL', 'Please enter a server address.');
      return;
    }
    setServerUrlInput(url);
    await updateSetting({ serverUrl: url });
    await testServerConnection(url);
  }, [serverUrlInput, updateSetting, testServerConnection]);

  // Get the current provider's available models
  const currentProviderModels =
    PROVIDER_OPTIONS.find((p) => p.name === settings.llmProvider)?.models ??
    [];

  // Connection status indicator color
  const connectionColor =
    connectionStatus === 'connected'
      ? colors.success
      : connectionStatus === 'connecting'
      ? colors.warning
      : colors.textMuted;

  const connectionLabel =
    connectionStatus === 'connected'
      ? 'Connected'
      : connectionStatus === 'connecting'
      ? 'Testing...'
      : 'Not connected';

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Text style={styles.screenTitle}>Settings</Text>

        {/* -- Operating Mode -- */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Operating Mode</Text>
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Remote Mode</Text>
            <Switch
              value={settings.mode === 'remote'}
              onValueChange={(val) =>
                updateSetting({ mode: val ? 'remote' : 'standalone' })
              }
              trackColor={{ true: colors.primary, false: colors.border }}
              thumbColor={colors.textPrimary}
            />
          </View>
          <Text style={styles.hint}>
            {settings.mode === 'standalone'
              ? 'Standalone: Audio is captured and transcribed on this device.'
              : 'Remote: Connects to a live-scribe server on your computer.'}
          </Text>
        </View>

        {/* -- Remote Server -- */}
        {settings.mode === 'remote' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Server Address</Text>

            {/* Connection status indicator */}
            <View style={styles.connectionRow}>
              <View
                style={[styles.connectionDot, { backgroundColor: connectionColor }]}
              />
              <Text style={[styles.connectionLabel, { color: connectionColor }]}>
                {connectionLabel}
              </Text>
            </View>

            {/* Server URL input */}
            <View style={styles.serverInputRow}>
              <TextInput
                style={styles.serverInput}
                value={serverUrlInput}
                onChangeText={setServerUrlInput}
                placeholder="http://192.168.1.100:8765"
                placeholderTextColor={colors.textMuted}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
              />
              <Pressable
                style={[styles.testButton, isTesting && styles.testButtonDisabled]}
                onPress={handleSaveServerUrl}
                disabled={isTesting}
              >
                {isTesting ? (
                  <ActivityIndicator size="small" color={colors.textPrimary} />
                ) : (
                  <Text style={styles.testButtonText}>Save & Test</Text>
                )}
              </Pressable>
            </View>

            <Text style={styles.hint}>
              Enter the IP address and port of your live-scribe server.
              {'\n'}Example: http://192.168.1.5:8765
              {'\n\n'}The server must be started with --host 0.0.0.0 to accept
              connections from your phone.
            </Text>
          </View>
        )}

        {/* -- LLM Provider (standalone mode only) -- */}
        {settings.mode === 'standalone' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>LLM Provider</Text>
            <View style={styles.optionGroup}>
              {PROVIDER_OPTIONS.map((provider) => (
                <Pressable
                  key={provider.name}
                  style={[
                    styles.optionButton,
                    settings.llmProvider === provider.name &&
                      styles.optionButtonActive,
                  ]}
                  onPress={() =>
                    updateSetting({
                      llmProvider: provider.name,
                      llmModel: provider.models[0],
                    })
                  }
                >
                  <Text
                    style={[
                      styles.optionText,
                      settings.llmProvider === provider.name &&
                        styles.optionTextActive,
                    ]}
                  >
                    {provider.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}

        {/* -- API Keys (standalone mode only) -- */}
        {settings.mode === 'standalone' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>API Keys</Text>
            <Text style={styles.hint}>
              Keys are stored securely on your device using encrypted storage.
              They are never sent anywhere except to the provider's API.
            </Text>

            {PROVIDER_OPTIONS.map((provider) => (
              <View key={provider.name} style={styles.apiKeyRow}>
                <Text style={styles.apiKeyLabel}>
                  {provider.label}{' '}
                  {savedKeys[provider.name] ? '(saved)' : '(not set)'}
                </Text>
                <View style={styles.apiKeyInputRow}>
                  <TextInput
                    style={styles.apiKeyInput}
                    placeholder="Enter API key..."
                    placeholderTextColor={colors.textMuted}
                    value={apiKeys[provider.name]}
                    onChangeText={(text) =>
                      setApiKeys((prev) => ({
                        ...prev,
                        [provider.name]: text,
                      }))
                    }
                    secureTextEntry
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                  <Pressable
                    style={styles.saveButton}
                    onPress={() => handleSaveApiKey(provider.name)}
                  >
                    <Text style={styles.saveButtonText}>Save</Text>
                  </Pressable>
                  {savedKeys[provider.name] && (
                    <Pressable
                      style={styles.deleteButton}
                      onPress={() => handleDeleteApiKey(provider.name)}
                    >
                      <Text style={styles.deleteButtonText}>X</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            ))}
          </View>
        )}

        {/* -- Model Selection (standalone mode only) -- */}
        {settings.mode === 'standalone' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Model</Text>
            <View style={styles.optionGroup}>
              {currentProviderModels.map((model) => (
                <Pressable
                  key={model}
                  style={[
                    styles.optionButton,
                    settings.llmModel === model && styles.optionButtonActive,
                  ]}
                  onPress={() => updateSetting({ llmModel: model })}
                >
                  <Text
                    style={[
                      styles.optionText,
                      settings.llmModel === model && styles.optionTextActive,
                    ]}
                  >
                    {model}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}

        {/* -- System Prompt -- */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>System Prompt</Text>
          {settings.mode === 'remote' && (
            <Text style={styles.hint}>
              In remote mode, the system prompt is configured on the server.
              You can change it here for standalone mode.
            </Text>
          )}
          <TextInput
            style={styles.promptInput}
            multiline
            numberOfLines={5}
            value={settings.systemPrompt}
            onChangeText={(text) => updateSetting({ systemPrompt: text })}
            placeholder="Instructions for the LLM..."
            placeholderTextColor={colors.textMuted}
          />
          <Pressable
            style={styles.resetButton}
            onPress={() =>
              updateSetting({ systemPrompt: DEFAULT_SETTINGS.systemPrompt })
            }
          >
            <Text style={styles.resetButtonText}>Reset to Default</Text>
          </Pressable>
        </View>

        {/* -- Audio Settings (standalone mode only) -- */}
        {settings.mode === 'standalone' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Audio Settings</Text>
            <View style={styles.row}>
              <Text style={styles.rowLabel}>
                Chunk Duration: {settings.chunkDurationSec}s
              </Text>
            </View>
            <Text style={styles.hint}>
              How many seconds of audio to capture before sending to Whisper.
              Shorter = faster updates, longer = better accuracy.
            </Text>
            <View style={styles.optionGroup}>
              {[3, 5, 10, 15, 30].map((sec) => (
                <Pressable
                  key={sec}
                  style={[
                    styles.optionButton,
                    settings.chunkDurationSec === sec &&
                      styles.optionButtonActive,
                  ]}
                  onPress={() => updateSetting({ chunkDurationSec: sec })}
                >
                  <Text
                    style={[
                      styles.optionText,
                      settings.chunkDurationSec === sec &&
                        styles.optionTextActive,
                    ]}
                  >
                    {sec}s
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}

        {/* Bottom padding */}
        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    padding: spacing.md,
  },
  screenTitle: {
    ...typography.title,
    marginBottom: spacing.lg,
  },
  section: {
    marginBottom: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.md,
  },
  sectionTitle: {
    ...typography.heading,
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  rowLabel: {
    ...typography.body,
  },
  hint: {
    ...typography.caption,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },
  optionGroup: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  optionButton: {
    backgroundColor: colors.card,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  optionButtonActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  optionText: {
    ...typography.caption,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  optionTextActive: {
    color: colors.textPrimary,
    fontWeight: '700',
  },
  apiKeyRow: {
    marginTop: spacing.md,
  },
  apiKeyLabel: {
    ...typography.caption,
    fontWeight: '600',
    marginBottom: spacing.xs,
  },
  apiKeyInputRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  apiKeyInput: {
    flex: 1,
    backgroundColor: colors.card,
    color: colors.textPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    ...typography.body,
    fontSize: 13,
  },
  saveButton: {
    backgroundColor: colors.success,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    justifyContent: 'center',
  },
  saveButtonText: {
    ...typography.caption,
    color: colors.textPrimary,
    fontWeight: '700',
  },
  deleteButton: {
    backgroundColor: colors.error,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    justifyContent: 'center',
  },
  deleteButtonText: {
    ...typography.caption,
    color: colors.textPrimary,
    fontWeight: '700',
  },
  promptInput: {
    backgroundColor: colors.card,
    color: colors.textPrimary,
    padding: spacing.md,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    ...typography.body,
    fontSize: 13,
    minHeight: 100,
    textAlignVertical: 'top',
  },
  resetButton: {
    alignSelf: 'flex-end',
    marginTop: spacing.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  resetButtonText: {
    ...typography.caption,
    color: colors.primary,
    fontWeight: '600',
  },
  textInput: {
    backgroundColor: colors.card,
    color: colors.textPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    ...typography.body,
    fontSize: 14,
  },
  // Server connection styles
  connectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  connectionDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  connectionLabel: {
    ...typography.caption,
    fontWeight: '600',
  },
  serverInputRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  serverInput: {
    flex: 1,
    backgroundColor: colors.card,
    color: colors.textPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    ...typography.body,
    fontSize: 14,
  },
  testButton: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    justifyContent: 'center',
    minWidth: 90,
    alignItems: 'center',
  },
  testButtonDisabled: {
    opacity: 0.6,
  },
  testButtonText: {
    ...typography.caption,
    color: colors.textPrimary,
    fontWeight: '700',
  },
});
