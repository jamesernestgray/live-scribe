# Live Scribe Mobile

A React Native mobile app (Android + iOS) for real-time audio transcription with LLM analysis. Built with [Expo](https://expo.dev), this is the mobile companion to the [live-scribe](../README.md) Python CLI tool.

## What It Does

Live Scribe Mobile captures audio from your phone's microphone, sends it to OpenAI's Whisper API for transcription, and lets you dispatch the transcript to an LLM (Claude, GPT, or Gemini) for real-time analysis.

### Two Operating Modes

**Standalone Mode** (default)
- Records audio directly on your phone
- Transcribes via OpenAI Whisper API (cloud)
- Sends transcripts to your choice of LLM (Anthropic, OpenAI, or Google)
- No computer needed — everything runs from your phone
- API keys stored securely on-device

**Remote Mode**
- Connects to a live-scribe server running on your computer via WebSocket
- Acts as a remote viewer and controller
- Useful when the Python backend is doing local Whisper transcription

---

## Prerequisites

Before you begin, make sure you have the following installed:

### Required for All Platforms
1. **Node.js 18+** — [Download from nodejs.org](https://nodejs.org/)
   ```bash
   # Verify installation
   node --version  # Should print v18.x.x or higher
   npm --version
   ```

2. **Expo CLI** — Installed automatically via npx, but you can also install globally:
   ```bash
   npm install -g expo-cli
   ```

3. **Expo Go app** (for testing on a physical device) — Install from the App Store (iOS) or Google Play Store (Android).

### For iOS Development (Mac only)
4. **Xcode 15+** — Install from the Mac App Store
   - After installing, open Xcode and accept the license agreement
   - Install the iOS Simulator: Xcode > Settings > Platforms > iOS
   - Install command-line tools:
     ```bash
     xcode-select --install
     ```

### For Android Development
5. **Android Studio** — [Download from developer.android.com](https://developer.android.com/studio)
   - During setup, install:
     - Android SDK
     - Android SDK Platform-Tools
     - Android Emulator
     - An Android Virtual Device (AVD) — API 34+ recommended
   - Set the `ANDROID_HOME` environment variable:
     ```bash
     # Add to your ~/.bashrc or ~/.zshrc:
     export ANDROID_HOME=$HOME/Library/Android/sdk  # macOS
     export ANDROID_HOME=$HOME/Android/Sdk           # Linux
     export PATH=$PATH:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools
     ```

### For Production Builds
6. **EAS CLI** (Expo Application Services) — Used for building APKs and IPAs:
   ```bash
   npm install -g eas-cli
   eas login  # Create an Expo account if you don't have one
   ```

---

## Setup

### 1. Install Dependencies

```bash
cd mobile
npm install
```

This installs all packages listed in `package.json`, including React Native, Expo modules, and navigation libraries.

### 2. Configure API Keys

The app needs API keys to function. You'll set these up in the app's Settings screen, but you need at least one of:

- **OpenAI API key** (required for transcription via Whisper)
  - Get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
  - This is used for both transcription (Whisper) and optionally for GPT analysis

- **Anthropic API key** (for Claude analysis)
  - Get one at [console.anthropic.com](https://console.anthropic.com/)

- **Google AI API key** (for Gemini analysis)
  - Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

Keys are stored securely on your device using `expo-secure-store` (Keychain on iOS, encrypted SharedPreferences on Android). They are **never** sent anywhere except directly to the respective provider's API.

---

## Running the App

### Development Mode (Recommended for Getting Started)

```bash
cd mobile
npx expo start
```

This starts the Expo development server. You'll see a QR code in your terminal.

**On a physical device:**
1. Open the Expo Go app on your phone
2. Scan the QR code from the terminal
3. The app will load on your device

**On iOS Simulator (Mac only):**
```bash
npx expo start --ios
# Or press 'i' after the dev server starts
```

**On Android Emulator:**
```bash
npx expo start --android
# Or press 'a' after the dev server starts
```

### Useful Development Commands

| Command | What it does |
|---------|-------------|
| `npx expo start` | Start the dev server |
| `npx expo start --ios` | Start and open in iOS Simulator |
| `npx expo start --android` | Start and open in Android Emulator |
| `npx expo start --clear` | Start with cleared cache |
| `npm test` | Run the test suite |
| `npm run lint` | Type-check with TypeScript |

---

## Building for Production

### Android APK / AAB

```bash
# Install EAS CLI if you haven't
npm install -g eas-cli

# Log in to Expo
eas login

# Build an APK (for direct install / testing)
eas build --platform android --profile preview

# Build an AAB (for Google Play Store submission)
eas build --platform android --profile production
```

You'll need to create an `eas.json` config first:
```bash
eas build:configure
```

### iOS IPA

```bash
# Build for iOS (requires Apple Developer account, $99/year)
eas build --platform ios

# Submit to TestFlight
eas submit --platform ios
```

**Note:** iOS builds require an Apple Developer Program membership. For testing on your own device, you can use Expo Go or a development build.

---

## Architecture Overview

```
mobile/
├── App.tsx                       # Root component, sets up navigation
├── src/
│   ├── screens/                  # Full-page views
│   │   ├── HomeScreen.tsx        # Main recording + transcription view
│   │   ├── SettingsScreen.tsx    # Configuration (API keys, provider, model)
│   │   └── HistoryScreen.tsx     # Past sessions browser
│   │
│   ├── components/               # Reusable UI components
│   │   ├── TranscriptView.tsx    # Scrolling transcript list
│   │   ├── LLMResponseView.tsx   # LLM response cards (supports streaming)
│   │   ├── RecordButton.tsx      # Animated record/stop button
│   │   ├── DispatchButton.tsx    # Send-to-LLM button
│   │   └── StatusBar.tsx         # Recording status indicators
│   │
│   ├── services/                 # Business logic (no React dependency)
│   │   ├── audio.ts              # Audio recording via expo-av
│   │   ├── transcription.ts      # OpenAI Whisper API client
│   │   ├── llm.ts                # LLM providers (Anthropic, OpenAI, Gemini)
│   │   └── storage.ts            # AsyncStorage + SecureStore wrapper
│   │
│   ├── hooks/                    # React hooks (bridge services to components)
│   │   ├── useAudioRecorder.ts   # Audio recording state management
│   │   ├── useTranscription.ts   # Transcription pipeline orchestration
│   │   └── useLLM.ts             # LLM dispatch state management
│   │
│   ├── types/                    # TypeScript interfaces
│   │   └── index.ts
│   │
│   ├── navigation/               # React Navigation setup
│   │   └── AppNavigator.tsx      # Bottom tab navigator
│   │
│   └── theme/                    # Design tokens
│       └── index.ts              # Colors, spacing, typography
│
├── __tests__/                    # Test suite
│   ├── services/
│   │   ├── llm.test.ts           # LLM provider tests
│   │   └── storage.test.ts       # Storage service tests
│   └── components/
│       └── TranscriptView.test.tsx
│
├── assets/                       # App icons and splash screen
├── app.json                      # Expo configuration
├── package.json                  # Dependencies
├── tsconfig.json                 # TypeScript configuration
└── babel.config.js               # Babel configuration
```

### Data Flow

```
Microphone
    │
    ▼
AudioRecorder (expo-av)
    │
    ▼ (audio chunks every N seconds)
    │
Whisper API (OpenAI)
    │
    ▼ (transcribed text segments)
    │
TranscriptBuffer (in-memory state)
    │
    ├──▶ TranscriptView (live display)
    │
    └──▶ LLM Provider (on dispatch)
            │
            ▼
         LLMResponseView (analysis display)
```

### Key Design Decisions

1. **Cloud transcription (Whisper API) instead of on-device:** On-device Whisper for React Native is still experimental. The API provides better accuracy with minimal setup. Audio chunks are small (5-10s of M4A at 128kbps = ~80-160KB per chunk).

2. **Direct API calls instead of a backend:** The app calls LLM APIs directly from the device. This means no server to maintain, but requires users to provide their own API keys.

3. **SecureStore for API keys:** Keys are encrypted at rest using the device's secure enclave (Keychain on iOS, encrypted SharedPreferences on Android).

4. **Hooks pattern:** Business logic lives in `services/` (pure TypeScript, no React dependency). React hooks in `hooks/` bridge services to components, managing state and side effects.

---

## How It Works

### Recording Pipeline

1. User taps the record button
2. `useAudioRecorder` requests microphone permission and starts `expo-av` recording
3. Every N seconds (configurable, default 5s), `useTranscription` captures an audio chunk
4. Each chunk is uploaded to the OpenAI Whisper API for transcription
5. Resulting text segments appear in the `TranscriptView` in real time

### LLM Dispatch

1. User taps the "Send to LLM" button (or auto-dispatch triggers)
2. `useLLM` formats the transcript and system prompt
3. The prompt is sent to the configured LLM provider's API
4. Response streams back in real time (or arrives all at once for non-streaming)
5. Response appears in the `LLMResponseView`

### Session Persistence

- When recording stops, the session (transcript + LLM responses) is saved to AsyncStorage
- The History tab shows all past sessions
- Sessions can be expanded to view full transcripts and responses
- Long-press a session to delete it

---

## Running Tests

```bash
cd mobile
npm test
```

The test suite includes:
- **LLM service tests:** Verify API request format, response parsing, and error handling for all three providers
- **Storage service tests:** Verify SecureStore and AsyncStorage interactions, settings merging, session CRUD
- **Component tests:** Smoke tests verifying components render without crashing

Tests use Jest with mocked native modules (expo-av, expo-secure-store, AsyncStorage). They verify TypeScript compiles correctly and business logic works as expected. Actual device testing requires running on a simulator or physical device.

---

## Known Limitations

1. **Transcription requires internet:** The Whisper API is cloud-based. Future versions could add on-device transcription via whisper.cpp.

2. **API costs:** Each audio chunk sent to Whisper and each LLM dispatch costs money based on the provider's pricing. Monitor your usage on each provider's dashboard.

3. **No background recording:** When the app is backgrounded on iOS, recording stops. This is an OS-level restriction. Android may continue briefly depending on settings.

4. **Audio gaps between chunks:** There's a brief gap (~100ms) when one chunk ends and the next begins. This rarely causes missed words but is technically not gapless.

5. **No speaker diarization:** The mobile app does not support speaker identification (unlike the Python backend with pyannote). All text appears without speaker labels unless added manually.

6. **Placeholder app icons:** The included icon and splash assets are solid-color placeholders. Replace them with proper branded assets before publishing.

7. **Remote mode is view-only:** The WebSocket remote mode is defined in the architecture but not yet fully implemented. Currently, the app works best in standalone mode.

---

## Troubleshooting

### "Microphone permission denied"
- iOS: Settings > Live Scribe > Microphone > Enable
- Android: Settings > Apps > Live Scribe > Permissions > Microphone > Allow

### "No API key found"
- Go to the Settings tab in the app
- Enter your API key for the provider you want to use
- Tap "Save"
- At minimum, you need an OpenAI key for Whisper transcription

### Build fails with "expo-av not found"
```bash
npx expo install expo-av
```

### Tests fail with "Cannot find module"
```bash
npm install
```

### Expo Go shows a blank screen
```bash
npx expo start --clear
```

---

## Contributing

This is the mobile frontend for live-scribe. The main project lives in the repository root. When making changes:

1. Keep services (`src/services/`) free of React dependencies for testability
2. Use the theme constants (`src/theme/`) for all colors and spacing
3. Add tests for new services and components
4. Run `npm run lint` to verify TypeScript compiles before committing
