# Roadmap & Future Features

This document tracks planned features, enhancements, and known issues that need to be addressed in future updates.

## Recently Completed Features
- [x] **Remote Control Server (Android)**: WebSocket-based remote control server enabling an Android companion app to control mouse, trigger actions, and receive UI state updates over LAN.
- [x] **Open Code in IDE**: Right-click any code block in the popup to open it directly in PyCharm or Antigravity IDE, with language-aware temp file creation.
- [x] **WebSocket Migration**: Migrated remote control server from HTTP polling to WebSocket for lower latency, real-time state push, and message coalescing for high-frequency mouse events.
- [x] **Popup State Reset**: Consecutive LLM responses now correctly clear and reset the popup text.
- [x] **Voice Activity Detection**: Implemented voice activity detection to automatically start/stop recording.
- [x] **Active Profile Placement**: Moved active profile selection to the main application tab for easier access.
- [x] **Android App Response Viewer**: Display rendered Markdown responses directly in the Android app.
- [x] **Session Browser**: Full-featured session browser dialog with tree view, prompt/response panels, tag management, filtering, renaming, and multi-delete.
- [x] **LLM Retry Mechanism**: Automatic retry with exponential backoff (up to 3 attempts) on transient LLM errors (503, rate limits, connection issues). Configurable via `llm_max_retries` and `llm_retry_base_delay`.
- [x] **Elaborate Session Structure**: Per-session folder hierarchy (`sessions/<uuid>/`) with `session.json`, `images/`, and `transcription.txt`. Speaker name attribution in transcription segments. Source-type icons in session browser. Transparent migration of legacy flat-file sessions.

## Core & Architecture Improvements
- [ ] **Type Hinting**: Add comprehensive Python type hints (especially for variables initialized to `None`) to improve IDE autocomplete, static analysis, and code maintainability.
- [ ] **Asynchronous Remote OCR Service**: When the remote OCR source is enabled, start the service asynchronously. Disable the capture and multi-select buttons until the service port is successfully polled. Ensure that if the app starts the service, it correctly kills it upon exiting.
- [ ] **Application Initialization State**: Introduce a "Ready" popup indicating that initialization has finished. Prevent showing the control panel or accepting keyboard shortcuts until the application is fully loaded.
- [ ] **Better Parsing of Verification Results**: Improve parsing and formatting of verification script (`verify.ps1`/`verify.sh`) output to provide clearer, more structured results.

## UI/UX Enhancements
- [ ] **Popup Sizing Stability**: Fix the issue where small prompt popups dynamically change sizes (starting large and subsequently shrinking).
- [ ] **Large Output Scroll Position**: Maintain the user's scroll position when large chunks of text are streamed into the popup.
- [ ] **Audio Recording UI**: Improve visual feedback during audio recording with better indicators and controls.

## Processing & Integration
- [ ] **Text-to-Speech (TTS) Improvements**: Enhance the TTS feature to read one sentence at a time, and include UI controls (buttons) to skip forward or backward through the spoken sentences.
- [ ] **Grammar & Accuracy Corrections**: Introduce a dedicated feature/button to analyze and correct the grammar or factual accuracy of the extracted or generated text.
- [ ] **Personalized Answers**: Add personalized answer capabilities that tailor LLM responses based on user preferences, context, or user profile. Allow users to include external context (files, documents, URLs) in the prompt to provide additional background information to the LLM.
- [ ] **Jira & Confluence Integration**: Explore and implement integration with Jira and Confluence for importing context, creating tickets, or publishing results.
- [ ] **Local LLM Integration Tests**: Add robust integration tests that utilize a simple, small, local LLM model to verify the end-to-end processing pipeline offline.
- [ ] **Summarize Audio Conversation**: Add the ability to summarize an entire audio conversation/session, producing a concise summary of the full transcription.

## Audio & Speech Features
- [ ] **Speech Recognition Enhancements**: Improve speech recognition accuracy with better noise cancellation and language detection.
- [ ] **Transcription Language Selection**: Allow users to choose the transcription language instead of hardcoding English (`lang="en"`). Expose this setting in the config UI, control panel, and Android app, and then pass it to the WhisperLive client.
- [ ] **Optional Translation Language**: Allow users to choose an optional translation language for real-time transcription. WhisperLive already supports translation on the server side — expose this via config and UI.
- [ ] **Multiple Language Support**: Add support for multiple languages in speech recognition and TTS.
- [ ] **Audio Level Visualization**: Add real-time audio level visualization during recording.
- [ ] **Fix Recording from Meetup Calls**: Investigate and fix issues with recording audio from Meetup/virtual meeting applications.
- [ ] **Dual Audio Channel Recording**: Listen to both microphone and speaker simultaneously and record them as separate sentences, enabling speaker-attributed transcription.

## Remote Control & Android Integration
- [ ] **Android Session Browsing**: Allow browsing sessions and retrieving response images directly in the Android app.
- [ ] **Touch Gestures**: Add pinch-to-zoom and multi-finger gestures on the Android touchpad.

## Developer Workflow
- [ ] **Claude Code with Skills & Git Worktrees**: Integrate Claude Code with skill files (power skills) and git worktrees for more efficient AI-assisted development.
- [ ] **E2E Tests in Claude Code**: Run end-to-end tests in Claude Code after each development task to catch regressions early.

## Testing & Quality Assurance
- [ ] **Cross-Platform Testing**: Improve testing coverage for different operating systems (Windows, macOS, Linux).
- [ ] **Error Recovery Testing**: Enhance testing for error recovery and fallback mechanisms.
- [ ] **Audio Device Compatibility**: Improve testing with various audio devices and configurations.

## Documentation
- [ ] **User Guide**: Create comprehensive user guide with screenshots and tutorials.
- [ ] **Troubleshooting Guide**: Expand troubleshooting section with common issues and solutions.