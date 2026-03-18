/**
 * HomeScreen — the main transcription view.
 *
 * Layout:
 *   - Top: Status bar (recording indicator, segment count, mode)
 *   - Middle: Two panels split vertically:
 *       - Top panel: Scrolling transcript (TranscriptView)
 *       - Bottom panel: LLM response area (LLMResponseView)
 *   - Bottom: Control bar with Record button + Dispatch button + timer
 *
 * This screen orchestrates the audio recording, transcription pipeline,
 * and LLM dispatch using the custom hooks.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import TranscriptView from '../components/TranscriptView';
import LLMResponseView from '../components/LLMResponseView';
import RecordButton from '../components/RecordButton';
import DispatchButton from '../components/DispatchButton';
import AppStatusBar from '../components/StatusBar';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { useTranscription } from '../hooks/useTranscription';
import { useLLM } from '../hooks/useLLM';
import { loadSettings, getApiKey, saveSession, generateId } from '../services/storage';
import { AppSettings, DEFAULT_SETTINGS, Session } from '../types';
import { colors, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function HomeScreen() {
  // ---------------------------------------------------------------------------
  // Settings state
  // ---------------------------------------------------------------------------
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [whisperApiKey, setWhisperApiKey] = useState('');
  const [sessionId] = useState(generateId());

  // Load settings on mount and when screen focuses
  useEffect(() => {
    async function load() {
      const s = await loadSettings();
      setSettings(s);

      // Whisper uses the OpenAI API key
      const key = await getApiKey('openai');
      setWhisperApiKey(key ?? '');
    }
    load();
  }, []);

  // ---------------------------------------------------------------------------
  // Hooks
  // ---------------------------------------------------------------------------
  const audioRecorder = useAudioRecorder();

  const transcription = useTranscription(
    audioRecorder,
    whisperApiKey,
    settings.chunkDurationSec
  );

  const llm = useLLM(settings.llmProvider, settings.llmModel);

  // Update LLM config when settings change
  useEffect(() => {
    llm.updateConfig(settings.llmProvider, settings.llmModel);
  }, [settings.llmProvider, settings.llmModel]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------------------
  // Recording toggle
  // ---------------------------------------------------------------------------
  const handleRecordPress = useCallback(async () => {
    if (transcription.isTranscribing) {
      // Stop recording
      await transcription.stopPipeline();

      // Save session
      const session: Session = {
        id: sessionId,
        title: `Session ${new Date().toLocaleDateString()}`,
        startedAt: Date.now() - audioRecorder.durationSec * 1000,
        endedAt: Date.now(),
        durationMs: audioRecorder.durationSec * 1000,
        transcript: transcription.transcript,
        llmResponses: llm.responses,
      };
      await saveSession(session);
    } else {
      // Check for API key before starting
      if (!whisperApiKey) {
        Alert.alert(
          'API Key Required',
          'An OpenAI API key is needed for transcription. Go to Settings to add one.',
          [{ text: 'OK' }]
        );
        return;
      }
      await transcription.startPipeline();
    }
  }, [
    transcription,
    sessionId,
    audioRecorder.durationSec,
    llm.responses,
    whisperApiKey,
  ]);

  // ---------------------------------------------------------------------------
  // LLM dispatch
  // ---------------------------------------------------------------------------
  const handleDispatch = useCallback(async () => {
    if (transcription.transcript.length === 0) {
      Alert.alert('Nothing to Send', 'Record some audio first.');
      return;
    }

    const formattedTranscript = transcription.getFormattedTranscript();
    await llm.dispatch(
      formattedTranscript,
      settings.systemPrompt,
      transcription.transcript.length
    );
  }, [transcription, llm, settings.systemPrompt]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Title bar */}
      <View style={styles.titleBar}>
        <Text style={styles.title}>Live Scribe</Text>
      </View>

      {/* Status bar */}
      <AppStatusBar
        recordingStatus={audioRecorder.status}
        segmentCount={transcription.transcript.length}
        chunkCount={transcription.chunkCount}
        dispatchCount={llm.responses.length}
        mode={settings.mode}
      />

      {/* Error banner */}
      {(audioRecorder.error || transcription.error) && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>
            {audioRecorder.error || transcription.error}
          </Text>
        </View>
      )}

      {/* Main content: transcript + LLM response */}
      <View style={styles.content}>
        {/* Transcript panel (top 60%) */}
        <View style={styles.transcriptPanel}>
          <Text style={styles.panelLabel}>Transcript</Text>
          <TranscriptView segments={transcription.transcript} />
        </View>

        {/* LLM panel (bottom 40%) */}
        <View style={styles.llmPanel}>
          <Text style={styles.panelLabel}>LLM Analysis</Text>
          <LLMResponseView
            responses={llm.responses}
            streamingText={llm.streamingText}
            isLoading={llm.isLoading}
            error={llm.error}
          />
        </View>
      </View>

      {/* Bottom control bar */}
      <View style={styles.controlBar}>
        <DispatchButton
          onPress={handleDispatch}
          isLoading={llm.isLoading}
          disabled={transcription.transcript.length === 0}
          segmentCount={transcription.transcript.length}
        />

        <RecordButton
          status={audioRecorder.status}
          durationSec={audioRecorder.durationSec}
          onPress={handleRecordPress}
          disabled={!audioRecorder.hasPermission}
        />

        {/* Spacer to balance the layout */}
        <View style={styles.controlSpacer} />
      </View>
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
  titleBar: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  title: {
    ...typography.title,
  },
  errorBanner: {
    backgroundColor: colors.error + '20',
    borderLeftWidth: 3,
    borderLeftColor: colors.error,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginHorizontal: spacing.md,
    marginTop: spacing.xs,
  },
  errorText: {
    ...typography.caption,
    color: colors.error,
  },
  content: {
    flex: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  transcriptPanel: {
    flex: 3,
  },
  llmPanel: {
    flex: 2,
  },
  panelLabel: {
    ...typography.caption,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing.xs,
  },
  controlBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.surface,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.divider,
  },
  controlSpacer: {
    width: 100,
  },
});
