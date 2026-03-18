/**
 * SettingsScreen — configure LLM provider, API keys, and app options.
 *
 * Sections:
 *   1. Operating Mode: Standalone or Remote
 *   2. LLM Provider: Anthropic, OpenAI, or Gemini
 *   3. API Keys: Securely stored per provider
 *   4. Model Selection: Provider-specific model choices
 *   5. System Prompt: Customizable LLM instruction
 *   6. Audio Settings: Chunk duration, auto-dispatch interval
 *   7. Remote Mode: Server URL (when in remote mode)
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
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

  // Load settings and check for saved keys on mount
  useEffect(() => {
    async function load() {
      const s = await loadSettings();
      setSettings(s);

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
    }
    load();
  }, []);

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

  // Get the current provider's available models
  const currentProviderModels =
    PROVIDER_OPTIONS.find((p) => p.name === settings.llmProvider)?.models ??
    [];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <Text style={styles.screenTitle}>Settings</Text>

        {/* ── Operating Mode ── */}
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
              : 'Remote: Connects to a live-scribe server via WebSocket.'}
          </Text>
        </View>

        {/* ── LLM Provider ── */}
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

        {/* ── API Keys ── */}
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

        {/* ── Model Selection ── */}
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

        {/* ── System Prompt ── */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>System Prompt</Text>
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

        {/* ── Audio Settings ── */}
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

        {/* ── Remote Mode Settings ── */}
        {settings.mode === 'remote' && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Remote Server</Text>
            <TextInput
              style={styles.textInput}
              value={settings.serverUrl}
              onChangeText={(text) => updateSetting({ serverUrl: text })}
              placeholder="ws://localhost:8765"
              placeholderTextColor={colors.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />
            <Text style={styles.hint}>
              WebSocket URL of the live-scribe server running on your computer.
            </Text>
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
});
