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
 * Supports two operating modes:
 *   - Standalone: Audio is captured and transcribed locally on the device.
 *   - Remote: Connects to the live-scribe Python backend via HTTP/WebSocket.
 *             The server handles audio capture, transcription, and LLM dispatch.
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
import { useRemoteServer } from '../hooks/useRemoteServer';
import { loadSettings, getApiKey, saveSession, generateId } from '../services/storage';
import { AppSettings, DEFAULT_SETTINGS, LLMResponse, Session, TranscriptSegment } from '../types';
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

  const isRemoteMode = settings.mode === 'remote';

  // ---------------------------------------------------------------------------
  // Standalone hooks (used when mode === 'standalone')
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
  // Remote server hook (used when mode === 'remote')
  // ---------------------------------------------------------------------------
  const remote = useRemoteServer();

  // Connect/disconnect WebSocket when entering/leaving remote mode
  useEffect(() => {
    if (isRemoteMode && settings.serverUrl) {
      remote.connect(settings.serverUrl);
    } else {
      remote.disconnect();
    }
    // Only re-run when mode or serverUrl changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRemoteMode, settings.serverUrl]);

  // ---------------------------------------------------------------------------
  // Derived state (unified across modes)
  // ---------------------------------------------------------------------------
  const currentSegments: TranscriptSegment[] = isRemoteMode
    ? remote.segments
    : transcription.transcript;

  const currentIsRecording = isRemoteMode
    ? remote.isRecording
    : transcription.isTranscribing;

  const currentRecordingStatus = isRemoteMode
    ? remote.isRecording
      ? 'recording' as const
      : 'idle' as const
    : audioRecorder.status;

  const currentSegmentCount = currentSegments.length;

  const currentChunkCount = isRemoteMode
    ? (remote.serverStatus?.segments ?? 0)
    : transcription.chunkCount;

  const currentDispatchCount = isRemoteMode
    ? remote.llmResponses.length
    : llm.responses.length;

  // Build LLMResponse[] from remote responses for the LLMResponseView component
  const remoteLlmResponsesForView: LLMResponse[] = remote.llmResponses.map(
    (r) => ({
      id: String(r.id),
      provider: 'remote' as LLMResponse['provider'],
      model: remote.serverStatus?.model ?? 'unknown',
      text: r.response,
      timestamp: Date.now(),
      segmentCount: 0,
    })
  );

  const currentLlmResponses = isRemoteMode
    ? remoteLlmResponsesForView
    : llm.responses;

  const currentStreamingText = isRemoteMode
    ? remote.streamingText
    : llm.streamingText;

  const currentIsLoading = isRemoteMode
    ? remote.isDispatching
    : llm.isLoading;

  const currentLlmError = isRemoteMode
    ? remote.error
    : llm.error;

  const currentError = isRemoteMode
    ? remote.error
    : audioRecorder.error || transcription.error;

  // ---------------------------------------------------------------------------
  // Recording toggle
  // ---------------------------------------------------------------------------
  const handleRecordPress = useCallback(async () => {
    if (isRemoteMode) {
      // Remote mode: start/stop via the backend API
      if (remote.isRecording) {
        await remote.stopRecording();
      } else {
        remote.clearState();
        const success = await remote.startRecording();
        if (!success && remote.error) {
          Alert.alert('Start Failed', remote.error);
        }
      }
    } else {
      // Standalone mode: local recording + transcription
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
    }
  }, [
    isRemoteMode,
    remote,
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
    if (isRemoteMode) {
      // Remote mode: dispatch via the backend API
      if (currentSegmentCount === 0) {
        Alert.alert('Nothing to Send', 'Start recording first.');
        return;
      }
      const success = await remote.dispatch();
      if (!success && remote.error) {
        Alert.alert('Dispatch Failed', remote.error);
      }
    } else {
      // Standalone mode: dispatch locally
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
    }
  }, [isRemoteMode, remote, transcription, llm, settings.systemPrompt, currentSegmentCount]);

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
        recordingStatus={currentRecordingStatus}
        segmentCount={currentSegmentCount}
        chunkCount={currentChunkCount}
        dispatchCount={currentDispatchCount}
        mode={settings.mode}
        connectionState={
          isRemoteMode ? remote.connectionState : undefined
        }
      />

      {/* Error banner */}
      {currentError && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{currentError}</Text>
        </View>
      )}

      {/* Remote mode: connection warning */}
      {isRemoteMode && !remote.isConnected && (
        <View style={styles.warningBanner}>
          <Text style={styles.warningText}>
            Not connected to server. Check Settings for the server address.
          </Text>
        </View>
      )}

      {/* Main content: transcript + LLM response */}
      <View style={styles.content}>
        {/* Transcript panel (top 60%) */}
        <View style={styles.transcriptPanel}>
          <Text style={styles.panelLabel}>Transcript</Text>
          <TranscriptView segments={currentSegments} />
        </View>

        {/* LLM panel (bottom 40%) */}
        <View style={styles.llmPanel}>
          <Text style={styles.panelLabel}>LLM Analysis</Text>
          <LLMResponseView
            responses={currentLlmResponses}
            streamingText={currentStreamingText}
            isLoading={currentIsLoading}
            error={currentLlmError}
          />
        </View>
      </View>

      {/* Bottom control bar */}
      <View style={styles.controlBar}>
        <DispatchButton
          onPress={handleDispatch}
          isLoading={currentIsLoading}
          disabled={
            isRemoteMode
              ? !remote.isConnected || currentSegmentCount === 0
              : currentSegmentCount === 0
          }
          segmentCount={currentSegmentCount}
        />

        <RecordButton
          status={currentRecordingStatus}
          durationSec={isRemoteMode ? 0 : audioRecorder.durationSec}
          onPress={handleRecordPress}
          disabled={
            isRemoteMode
              ? !remote.isConnected
              : !audioRecorder.hasPermission
          }
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
  warningBanner: {
    backgroundColor: colors.warning + '20',
    borderLeftWidth: 3,
    borderLeftColor: colors.warning,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginHorizontal: spacing.md,
    marginTop: spacing.xs,
  },
  warningText: {
    ...typography.caption,
    color: colors.warning,
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
