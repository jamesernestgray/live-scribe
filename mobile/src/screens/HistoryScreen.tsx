/**
 * HistoryScreen — view past transcription sessions.
 *
 * Shows a list of saved sessions with:
 *   - Title, date, and duration
 *   - Number of transcript segments and LLM dispatches
 *   - Tap to expand and view full transcript + LLM responses
 *   - Swipe or long-press to delete
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Session } from '../types';
import {
  deleteAllSessions,
  deleteSession,
  loadAllSessions,
} from '../services/storage';
import { borderRadius, colors, shadow, spacing, typography } from '../theme';

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min === 0) return `${sec}s`;
  return `${min}m ${sec}s`;
}

function formatDate(timestamp: number): string {
  const d = new Date(timestamp);
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Session detail modal (inline expansion)
// ---------------------------------------------------------------------------

function SessionDetail({ session }: { session: Session }) {
  return (
    <View style={styles.detailContainer}>
      {/* Transcript */}
      <Text style={styles.detailHeading}>
        Transcript ({session.transcript.length} segments)
      </Text>
      {session.transcript.length === 0 ? (
        <Text style={styles.detailEmpty}>No transcript segments.</Text>
      ) : (
        session.transcript.map((seg) => {
          const time = new Date(seg.timestamp).toLocaleTimeString('en-US', {
            hour12: false,
          });
          return (
            <Text key={seg.id} style={styles.detailSegment}>
              <Text style={styles.detailTimestamp}>[{time}] </Text>
              {seg.speaker && (
                <Text style={styles.detailSpeaker}>[{seg.speaker}] </Text>
              )}
              {seg.text}
            </Text>
          );
        })
      )}

      {/* LLM Responses */}
      {session.llmResponses.length > 0 && (
        <>
          <Text style={[styles.detailHeading, { marginTop: spacing.md }]}>
            LLM Responses ({session.llmResponses.length})
          </Text>
          {session.llmResponses.map((resp) => (
            <View key={resp.id} style={styles.detailResponse}>
              <Text style={styles.detailResponseMeta}>
                {resp.provider}/{resp.model} | {resp.segmentCount} segments
              </Text>
              <Text style={styles.detailResponseText}>{resp.text}</Text>
            </View>
          ))}
        </>
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function HistoryScreen() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Load sessions
  const loadSessions = useCallback(async () => {
    const all = await loadAllSessions();
    setSessions(all);
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Pull to refresh
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadSessions();
    setRefreshing(false);
  }, [loadSessions]);

  // Delete a session
  const handleDelete = useCallback(
    (session: Session) => {
      Alert.alert(
        'Delete Session',
        `Delete "${session.title}"? This cannot be undone.`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Delete',
            style: 'destructive',
            onPress: async () => {
              await deleteSession(session.id);
              await loadSessions();
            },
          },
        ]
      );
    },
    [loadSessions]
  );

  // Clear all sessions
  const handleClearAll = useCallback(() => {
    Alert.alert(
      'Clear All Sessions',
      'Delete all saved sessions? This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete All',
          style: 'destructive',
          onPress: async () => {
            await deleteAllSessions();
            setSessions([]);
          },
        },
      ]
    );
  }, []);

  // Toggle expand
  const toggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  // Render a session card
  const renderSession = ({ item }: { item: Session }) => {
    const isExpanded = expandedId === item.id;

    return (
      <Pressable
        style={styles.sessionCard}
        onPress={() => toggleExpand(item.id)}
        onLongPress={() => handleDelete(item)}
      >
        {/* Card header */}
        <View style={styles.cardHeader}>
          <Text style={styles.sessionTitle} numberOfLines={1}>
            {item.title}
          </Text>
          <Text style={styles.expandIcon}>
            {isExpanded ? '\u25B2' : '\u25BC'}
          </Text>
        </View>

        {/* Card meta */}
        <View style={styles.cardMeta}>
          <Text style={styles.metaText}>{formatDate(item.startedAt)}</Text>
          <Text style={styles.metaDot}>{'\u00B7'}</Text>
          <Text style={styles.metaText}>{formatDuration(item.durationMs)}</Text>
          <Text style={styles.metaDot}>{'\u00B7'}</Text>
          <Text style={styles.metaText}>
            {item.transcript.length} segments
          </Text>
          <Text style={styles.metaDot}>{'\u00B7'}</Text>
          <Text style={styles.metaText}>
            {item.llmResponses.length} dispatches
          </Text>
        </View>

        {/* Expanded detail */}
        {isExpanded && <SessionDetail session={item} />}
      </Pressable>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.screenTitle}>History</Text>
        {sessions.length > 0 && (
          <Pressable onPress={handleClearAll}>
            <Text style={styles.clearAllText}>Clear All</Text>
          </Pressable>
        )}
      </View>

      {/* Sessions list */}
      {sessions.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            No saved sessions yet. Start a recording on the Home tab to create
            your first session.
          </Text>
        </View>
      ) : (
        <FlatList
          data={sessions}
          keyExtractor={(item) => item.id}
          renderItem={renderSession}
          contentContainerStyle={styles.listContent}
          refreshing={refreshing}
          onRefresh={handleRefresh}
        />
      )}
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  screenTitle: {
    ...typography.title,
  },
  clearAllText: {
    ...typography.caption,
    color: colors.error,
    fontWeight: '600',
  },
  listContent: {
    padding: spacing.md,
  },
  sessionCard: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    ...shadow.sm,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sessionTitle: {
    ...typography.heading,
    flex: 1,
    marginRight: spacing.sm,
  },
  expandIcon: {
    ...typography.caption,
    color: colors.textMuted,
  },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  metaText: {
    ...typography.caption,
    color: colors.textMuted,
  },
  metaDot: {
    ...typography.caption,
    color: colors.border,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  emptyText: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: 'center',
  },
  // Detail styles
  detailContainer: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.divider,
  },
  detailHeading: {
    ...typography.caption,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing.sm,
  },
  detailEmpty: {
    ...typography.caption,
    color: colors.textMuted,
    fontStyle: 'italic',
  },
  detailSegment: {
    ...typography.body,
    fontSize: 13,
    marginBottom: 2,
  },
  detailTimestamp: {
    color: colors.textMuted,
    fontFamily: 'monospace',
    fontSize: 11,
  },
  detailSpeaker: {
    color: colors.primary,
    fontWeight: '600',
    fontSize: 12,
  },
  detailResponse: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.sm,
    padding: spacing.sm,
    marginBottom: spacing.sm,
  },
  detailResponseMeta: {
    ...typography.caption,
    color: colors.textMuted,
    marginBottom: spacing.xs,
  },
  detailResponseText: {
    ...typography.body,
    fontSize: 13,
  },
});
