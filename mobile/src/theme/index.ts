/**
 * Theme constants for Live Scribe mobile app.
 *
 * Defines colors, spacing, typography, and reusable style helpers
 * to keep the UI consistent across screens.
 */

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

export const colors = {
  // Background layers (dark theme to match the CLI aesthetic)
  background: '#1a1a2e',
  surface: '#16213e',
  surfaceLight: '#0f3460',
  card: '#1e2a4a',

  // Primary accent
  primary: '#e94560',
  primaryLight: '#ff6b81',
  primaryDark: '#c23152',

  // Secondary accent
  secondary: '#0f3460',
  secondaryLight: '#1a4a8a',

  // Text
  textPrimary: '#f0f0f0',
  textSecondary: '#a0a0b0',
  textMuted: '#6c6c80',

  // Semantic
  success: '#4caf50',
  warning: '#ff9800',
  error: '#f44336',
  info: '#2196f3',

  // Speaker colors (cycle through these for multi-speaker transcripts)
  speakers: [
    '#e94560', // red/pink
    '#4fc3f7', // light blue
    '#81c784', // green
    '#ffb74d', // orange
    '#ce93d8', // purple
    '#4dd0e1', // cyan
    '#fff176', // yellow
    '#a1887f', // brown
  ],

  // Recording indicator
  recordingRed: '#ff1744',
  recordingRedDim: '#b71c1c',

  // Borders and dividers
  border: '#2a2a4e',
  divider: '#2a2a4e',

  // Overlays
  overlay: 'rgba(0, 0, 0, 0.5)',
} as const;

// ---------------------------------------------------------------------------
// Spacing
// ---------------------------------------------------------------------------

/** Spacing scale based on 4px grid. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

// ---------------------------------------------------------------------------
// Typography
// ---------------------------------------------------------------------------

export const typography = {
  /** Large screen titles. */
  title: {
    fontSize: 24,
    fontWeight: '700' as const,
    color: colors.textPrimary,
  },
  /** Section headers. */
  heading: {
    fontSize: 18,
    fontWeight: '600' as const,
    color: colors.textPrimary,
  },
  /** Normal body text. */
  body: {
    fontSize: 15,
    fontWeight: '400' as const,
    color: colors.textPrimary,
    lineHeight: 22,
  },
  /** Small secondary text (timestamps, labels). */
  caption: {
    fontSize: 12,
    fontWeight: '400' as const,
    color: colors.textSecondary,
  },
  /** Monospace text for code/technical output. */
  mono: {
    fontSize: 13,
    fontFamily: 'monospace' as const,
    color: colors.textPrimary,
  },
} as const;

// ---------------------------------------------------------------------------
// Border radius
// ---------------------------------------------------------------------------

export const borderRadius = {
  sm: 6,
  md: 12,
  lg: 20,
  full: 999,
} as const;

// ---------------------------------------------------------------------------
// Shadows (iOS)
// ---------------------------------------------------------------------------

export const shadow = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
    elevation: 2,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 4,
  },
  lg: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
} as const;

// ---------------------------------------------------------------------------
// Helper: get speaker color by index
// ---------------------------------------------------------------------------

/**
 * Returns a consistent color for a given speaker label.
 * Uses a simple hash so the same speaker always gets the same color.
 */
export function getSpeakerColor(speaker: string): string {
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) {
    hash = speaker.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % colors.speakers.length;
  return colors.speakers[index];
}
