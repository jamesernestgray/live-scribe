/**
 * TranscriptView component.
 *
 * Displays a scrolling list of transcript segments with timestamps
 * and optional speaker labels (color-coded). Auto-scrolls to the
 * bottom as new segments arrive.
 *
 * Used on the HomeScreen as the main transcript display area.
 */

import React, { useEffect, useRef } from 'react';
import {
  FlatList,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { TranscriptSegment } from '../types';
import { borderRadius, colors, getSpeakerColor, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TranscriptViewProps {
  /** The transcript segments to display. */
  segments: TranscriptSegment[];

  /** Optional: show a placeholder when empty. */
  placeholder?: string;
}

// ---------------------------------------------------------------------------
// Segment row component (memoized for performance)
// ---------------------------------------------------------------------------

const SegmentRow = React.memo(function SegmentRow({
  segment,
}: {
  segment: TranscriptSegment;
}) {
  const time = new Date(segment.timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const speakerColor = segment.speaker
    ? getSpeakerColor(segment.speaker)
    : undefined;

  return (
    <View style={styles.segmentRow}>
      {/* Timestamp */}
      <Text style={styles.timestamp}>{time}</Text>

      {/* Speaker label (if present) */}
      {segment.speaker && (
        <Text style={[styles.speaker, { color: speakerColor }]}>
          [{segment.speaker}]
        </Text>
      )}

      {/* Transcript text */}
      <Text style={styles.segmentText}>{segment.text}</Text>
    </View>
  );
});

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TranscriptView({
  segments,
  placeholder = 'Transcript will appear here when you start recording...',
}: TranscriptViewProps) {
  const flatListRef = useRef<FlatList>(null);

  // Auto-scroll to bottom when new segments arrive
  useEffect(() => {
    if (segments.length > 0 && flatListRef.current) {
      // Small delay to let the layout settle
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [segments.length]);

  if (segments.length === 0) {
    return (
      <View style={styles.placeholderContainer}>
        <Text style={styles.placeholderText}>{placeholder}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        ref={flatListRef}
        data={segments}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <SegmentRow segment={item} />}
        contentContainerStyle={styles.listContent}
        // Performance optimizations
        initialNumToRender={20}
        maxToRenderPerBatch={10}
        windowSize={10}
        removeClippedSubviews={true}
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    overflow: 'hidden',
  },
  listContent: {
    padding: spacing.sm,
  },
  segmentRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  timestamp: {
    ...typography.caption,
    fontFamily: 'monospace',
    color: colors.textMuted,
    marginRight: spacing.sm,
    minWidth: 65,
  },
  speaker: {
    ...typography.caption,
    fontWeight: '600',
    marginRight: spacing.sm,
  },
  segmentText: {
    ...typography.body,
    flex: 1,
    flexShrink: 1,
  },
  placeholderContainer: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
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
