/**
 * RecordButton component.
 *
 * A large, circular microphone button that pulses red when recording.
 * Tap to start/stop recording. The visual design mirrors a classic
 * voice recorder UI.
 *
 * States:
 *   - idle:       Gray circle with mic icon, "Tap to Record" label
 *   - recording:  Red pulsing circle, "Recording..." label, duration timer
 *   - processing: Spinner, "Processing..." label
 */

import React, { useEffect, useRef } from 'react';
import {
  Animated,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { RecordingStatus } from '../types';
import { colors, shadow, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RecordButtonProps {
  /** Current recording status. */
  status: RecordingStatus;

  /** Recording duration in seconds (only shown when recording). */
  durationSec: number;

  /** Called when the button is pressed. */
  onPress: () => void;

  /** Whether the button is disabled (e.g. no mic permission). */
  disabled?: boolean;
}

// ---------------------------------------------------------------------------
// Helper: format seconds as MM:SS
// ---------------------------------------------------------------------------

function formatDuration(totalSec: number): string {
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RecordButton({
  status,
  durationSec,
  onPress,
  disabled = false,
}: RecordButtonProps) {
  const isRecording = status === 'recording';
  const isProcessing = status === 'processing';

  // Pulsing animation for the recording state
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (isRecording) {
      // Start pulsing animation
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.15,
            duration: 800,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 800,
            useNativeDriver: true,
          }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else {
      // Reset to default scale
      pulseAnim.setValue(1);
    }
  }, [isRecording, pulseAnim]);

  // Determine button appearance
  const buttonColor = isRecording
    ? colors.recordingRed
    : isProcessing
    ? colors.textMuted
    : colors.primary;

  const label = isRecording
    ? 'Recording...'
    : isProcessing
    ? 'Processing...'
    : 'Tap to Record';

  // Mic icon using Unicode (avoids needing an icon library)
  const icon = isRecording ? '\u23F9' : '\uD83C\uDFA4'; // stop symbol : microphone

  return (
    <View style={styles.container}>
      {/* Duration timer (visible when recording) */}
      {isRecording && (
        <Text style={styles.duration}>{formatDuration(durationSec)}</Text>
      )}

      {/* The button */}
      <Pressable
        onPress={onPress}
        disabled={disabled || isProcessing}
        style={({ pressed }) => [
          styles.pressable,
          pressed && !disabled && styles.pressed,
        ]}
      >
        <Animated.View
          style={[
            styles.button,
            { backgroundColor: buttonColor },
            { transform: [{ scale: pulseAnim }] },
            disabled && styles.disabled,
          ]}
        >
          <Text style={styles.icon}>{icon}</Text>
        </Animated.View>
      </Pressable>

      {/* Label */}
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const BUTTON_SIZE = 80;

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: spacing.sm,
  },
  duration: {
    ...typography.heading,
    fontFamily: 'monospace',
    color: colors.recordingRed,
    fontWeight: '700',
  },
  pressable: {
    // Increase touch target beyond the visual button
    padding: spacing.sm,
  },
  pressed: {
    opacity: 0.8,
  },
  button: {
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    borderRadius: BUTTON_SIZE / 2,
    justifyContent: 'center',
    alignItems: 'center',
    ...shadow.lg,
  },
  disabled: {
    opacity: 0.4,
  },
  icon: {
    fontSize: 32,
    color: colors.textPrimary,
  },
  label: {
    ...typography.caption,
    color: colors.textSecondary,
  },
});
