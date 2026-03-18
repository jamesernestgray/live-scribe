/**
 * LLMResponseView component.
 *
 * Displays LLM analysis responses as styled cards. Shows:
 *   - The latest response (streaming or complete)
 *   - A loading indicator while the LLM is thinking
 *   - Provider/model badge on each response
 *
 * Used on the HomeScreen below the transcript.
 */

import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { LLMResponse } from '../types';
import { borderRadius, colors, shadow, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LLMResponseViewProps {
  /** All LLM responses for this session. */
  responses: LLMResponse[];

  /** Text being streamed from the LLM (partial response). */
  streamingText: string;

  /** Whether an LLM request is in progress. */
  isLoading: boolean;

  /** Error message from the last LLM call, or null. */
  error: string | null;
}

// ---------------------------------------------------------------------------
// Response card component
// ---------------------------------------------------------------------------

function ResponseCard({ response }: { response: LLMResponse }) {
  const time = new Date(response.timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <View style={styles.card}>
      {/* Header row: provider badge + timestamp */}
      <View style={styles.cardHeader}>
        <View style={styles.providerBadge}>
          <Text style={styles.providerText}>
            {response.provider} / {response.model}
          </Text>
        </View>
        <Text style={styles.cardTimestamp}>
          {time} | {response.segmentCount} segments
        </Text>
      </View>

      {/* Response text */}
      <Text style={styles.responseText}>{response.text}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function LLMResponseView({
  responses,
  streamingText,
  isLoading,
  error,
}: LLMResponseViewProps) {
  // Show error state
  if (error) {
    return (
      <View style={styles.container}>
        <View style={[styles.card, styles.errorCard]}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      </View>
    );
  }

  // Show streaming response
  if (isLoading && streamingText) {
    return (
      <View style={styles.container}>
        <View style={[styles.card, styles.streamingCard]}>
          <View style={styles.cardHeader}>
            <View style={styles.streamingBadge}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={styles.streamingLabel}>Streaming...</Text>
            </View>
          </View>
          <Text style={styles.responseText}>{streamingText}</Text>
        </View>
      </View>
    );
  }

  // Show loading spinner (no streaming text yet)
  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Analyzing transcript...</Text>
      </View>
    );
  }

  // Show placeholder if no responses yet
  if (responses.length === 0) {
    return (
      <View style={styles.placeholderContainer}>
        <Text style={styles.placeholderText}>
          LLM analysis will appear here. Tap the dispatch button to send
          your transcript for analysis.
        </Text>
      </View>
    );
  }

  // Show response cards (most recent first)
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
      {[...responses].reverse().map((response) => (
        <ResponseCard key={response.id} response={response} />
      ))}
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    padding: spacing.sm,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    ...shadow.sm,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  providerBadge: {
    backgroundColor: colors.secondaryLight,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.sm,
  },
  providerText: {
    ...typography.caption,
    color: colors.textPrimary,
    fontWeight: '600',
  },
  cardTimestamp: {
    ...typography.caption,
  },
  responseText: {
    ...typography.body,
    lineHeight: 22,
  },
  streamingCard: {
    borderColor: colors.primary,
    borderWidth: 1,
  },
  streamingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  streamingLabel: {
    ...typography.caption,
    color: colors.primary,
    fontWeight: '600',
  },
  errorCard: {
    borderColor: colors.error,
    borderWidth: 1,
    margin: spacing.sm,
  },
  errorText: {
    ...typography.body,
    color: colors.error,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
  },
  loadingText: {
    ...typography.body,
    color: colors.textSecondary,
  },
  placeholderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  placeholderText: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: 'center',
  },
});
