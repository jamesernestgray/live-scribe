/**
 * StatusBar component (not to be confused with React Native's StatusBar).
 *
 * Displays a compact status strip at the top of the HomeScreen showing:
 *   - Recording status indicator (green dot = idle, red pulsing = recording)
 *   - Number of transcript segments
 *   - Number of LLM dispatches
 *   - Current mode (Standalone / Remote)
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { AppMode, ConnectionState, RecordingStatus } from '../types';
import { colors, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface StatusBarProps {
  /** Current recording status. */
  recordingStatus: RecordingStatus;

  /** Number of transcript segments captured. */
  segmentCount: number;

  /** Number of chunks transcribed. */
  chunkCount: number;

  /** Number of LLM dispatches completed. */
  dispatchCount: number;

  /** Current operating mode. */
  mode: AppMode;

  /** WebSocket connection state (remote mode only). */
  connectionState?: ConnectionState;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AppStatusBar({
  recordingStatus,
  segmentCount,
  chunkCount,
  dispatchCount,
  mode,
  connectionState,
}: StatusBarProps) {
  const isRecording = recordingStatus === 'recording';
  const isRemote = mode === 'remote';

  // In remote mode, connection state takes priority for status indicator
  const statusColor = isRemote
    ? connectionState === 'connected'
      ? isRecording
        ? colors.recordingRed
        : colors.success
      : connectionState === 'connecting'
      ? colors.warning
      : colors.textMuted
    : isRecording
    ? colors.recordingRed
    : colors.success;

  const statusLabel = isRemote
    ? connectionState === 'connected'
      ? isRecording
        ? 'Recording'
        : 'Connected'
      : connectionState === 'connecting'
      ? 'Connecting...'
      : 'Disconnected'
    : recordingStatus === 'idle'
    ? 'Idle'
    : recordingStatus === 'recording'
    ? 'Recording'
    : recordingStatus === 'paused'
    ? 'Paused'
    : 'Processing';

  return (
    <View style={styles.container}>
      {/* Left: recording/connection status */}
      <View style={styles.statusGroup}>
        <View style={[styles.dot, { backgroundColor: statusColor }]} />
        <Text style={styles.statusText}>{statusLabel}</Text>
      </View>

      {/* Center: segment and chunk counts */}
      <View style={styles.statsGroup}>
        <Text style={styles.statText}>
          {segmentCount} seg{segmentCount !== 1 ? 's' : ''}
        </Text>
        <Text style={styles.divider}>|</Text>
        <Text style={styles.statText}>
          {chunkCount} chunk{chunkCount !== 1 ? 's' : ''}
        </Text>
        <Text style={styles.divider}>|</Text>
        <Text style={styles.statText}>
          {dispatchCount} dispatch{dispatchCount !== 1 ? 'es' : ''}
        </Text>
      </View>

      {/* Right: mode badge */}
      <View style={styles.modeBadge}>
        <Text style={styles.modeText}>
          {mode === 'standalone' ? 'Local' : 'Remote'}
        </Text>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  statusGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    ...typography.caption,
    fontWeight: '600',
  },
  statsGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  statText: {
    ...typography.caption,
    color: colors.textMuted,
  },
  divider: {
    ...typography.caption,
    color: colors.border,
  },
  modeBadge: {
    backgroundColor: colors.secondaryLight,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: 8,
  },
  modeText: {
    ...typography.caption,
    color: colors.textPrimary,
    fontWeight: '600',
    fontSize: 10,
    textTransform: 'uppercase',
  },
});
