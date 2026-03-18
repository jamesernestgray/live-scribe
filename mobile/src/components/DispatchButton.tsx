/**
 * DispatchButton component.
 *
 * A button that sends the current transcript to the configured LLM
 * for analysis. Shows different states:
 *   - Ready:   Blue/purple button with "Send to LLM" label
 *   - Loading: Spinner + "Analyzing..." label
 *   - Disabled: Grayed out (nothing to send or no API key)
 */

import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { colors, borderRadius, shadow, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface DispatchButtonProps {
  /** Called when the button is pressed. */
  onPress: () => void;

  /** Whether an LLM request is in progress. */
  isLoading: boolean;

  /** Whether the button is disabled (e.g. no transcript segments). */
  disabled?: boolean;

  /** Number of transcript segments that will be sent. */
  segmentCount?: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DispatchButton({
  onPress,
  isLoading,
  disabled = false,
  segmentCount = 0,
}: DispatchButtonProps) {
  const isDisabled = disabled || isLoading;

  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.button,
        isDisabled && styles.buttonDisabled,
        pressed && !isDisabled && styles.buttonPressed,
      ]}
    >
      <View style={styles.content}>
        {isLoading ? (
          <>
            <ActivityIndicator size="small" color={colors.textPrimary} />
            <Text style={styles.label}>Analyzing...</Text>
          </>
        ) : (
          <>
            {/* Brain emoji as icon */}
            <Text style={styles.icon}>{'\uD83E\uDDE0'}</Text>
            <Text style={[styles.label, isDisabled && styles.labelDisabled]}>
              Send to LLM
            </Text>
            {segmentCount > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{segmentCount}</Text>
              </View>
            )}
          </>
        )}
      </View>
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  button: {
    backgroundColor: colors.secondaryLight,
    borderRadius: borderRadius.lg,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.lg,
    ...shadow.sm,
  },
  buttonDisabled: {
    backgroundColor: colors.surface,
    opacity: 0.5,
  },
  buttonPressed: {
    opacity: 0.8,
    transform: [{ scale: 0.97 }],
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  icon: {
    fontSize: 18,
  },
  label: {
    ...typography.body,
    color: colors.textPrimary,
    fontWeight: '600',
  },
  labelDisabled: {
    color: colors.textMuted,
  },
  badge: {
    backgroundColor: colors.primary,
    borderRadius: borderRadius.full,
    minWidth: 22,
    height: 22,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xs,
  },
  badgeText: {
    ...typography.caption,
    color: colors.textPrimary,
    fontWeight: '700',
    fontSize: 11,
  },
});
