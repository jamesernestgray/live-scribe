/**
 * App.tsx — Root component for Live Scribe mobile app.
 *
 * Sets up:
 *   - SafeAreaProvider for proper insets on notched devices
 *   - StatusBar configuration (light text on dark background)
 *   - AppNavigator (bottom tab navigation)
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import AppNavigator from './src/navigation/AppNavigator';

export default function App() {
  return (
    <SafeAreaProvider>
      {/* Light status bar text for the dark background */}
      <StatusBar style="light" />
      <AppNavigator />
    </SafeAreaProvider>
  );
}
