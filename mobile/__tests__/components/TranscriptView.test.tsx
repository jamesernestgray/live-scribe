/**
 * Smoke tests for the TranscriptView component.
 *
 * Verifies that:
 *   - The component renders without crashing
 *   - It shows a placeholder when there are no segments
 *   - It renders segments with timestamps and text
 *   - Speaker labels are displayed when present
 */

import React from 'react';
import { render } from '@testing-library/react-native';
import TranscriptView from '../../src/components/TranscriptView';
import { TranscriptSegment } from '../../src/types';

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockSegments: TranscriptSegment[] = [
  {
    id: 'seg-1',
    text: 'Hello, this is a test.',
    timestamp: new Date('2025-01-15T10:30:00').getTime(),
  },
  {
    id: 'seg-2',
    text: 'Second segment with speaker.',
    timestamp: new Date('2025-01-15T10:30:05').getTime(),
    speaker: 'SPEAKER_00',
  },
  {
    id: 'seg-3',
    text: 'Third segment from another speaker.',
    timestamp: new Date('2025-01-15T10:30:10').getTime(),
    speaker: 'SPEAKER_01',
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TranscriptView', () => {
  it('renders without crashing', () => {
    const { toJSON } = render(<TranscriptView segments={[]} />);
    expect(toJSON()).toBeTruthy();
  });

  it('shows placeholder when segments are empty', () => {
    const { getByText } = render(<TranscriptView segments={[]} />);
    expect(
      getByText('Transcript will appear here when you start recording...')
    ).toBeTruthy();
  });

  it('shows custom placeholder', () => {
    const { getByText } = render(
      <TranscriptView segments={[]} placeholder="Custom placeholder" />
    );
    expect(getByText('Custom placeholder')).toBeTruthy();
  });

  it('renders transcript segments with text', () => {
    const { getByText } = render(
      <TranscriptView segments={mockSegments} />
    );
    expect(getByText('Hello, this is a test.')).toBeTruthy();
    expect(getByText('Second segment with speaker.')).toBeTruthy();
    expect(getByText('Third segment from another speaker.')).toBeTruthy();
  });

  it('renders speaker labels when present', () => {
    const { getByText } = render(
      <TranscriptView segments={mockSegments} />
    );
    expect(getByText('[SPEAKER_00]')).toBeTruthy();
    expect(getByText('[SPEAKER_01]')).toBeTruthy();
  });
});
