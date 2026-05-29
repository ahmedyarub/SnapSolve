# Roadmap & Future Features

This document tracks planned features, enhancements, and known issues that need to be addressed in future updates.

## Recently Completed Features
- [x] **Stealth Mode (Hide from Capture)**: Windows can be excluded from screen-capture APIs (OBS, video calls, Win+Shift+S) while remaining visible on the user's monitor.
- [x] **Remote Control Server (Android)**: WebSocket-based remote control server enabling an Android companion app to control mouse, trigger actions, and receive UI state updates over LAN.
- [x] **Open Code in IDE**: Right-click any code block in the popup to open it directly in PyCharm or Antigravity IDE, with language-aware temp file creation.
- [x] **WebSocket Migration**: Migrated remote control server from HTTP polling to WebSocket for lower latency, real-time state push, and message coalescing for high-frequency mouse events.
- [x] **Popup State Reset**: Consecutive LLM responses now correctly clear and reset the popup text.
- [x] **Voice Activity Detection**: Implemented voice activity detection to automatically start/stop recording.
- [x] **Active Profile Placement**: Moved active profile selection to the main application tab for easier access.
- [x] **Android App Response Viewer**: Display rendered Markdown responses directly in the Android app.
- [x] **Session Browser**: Full-featured session browser dialog with tree view, prompt/response panels, tag management, filtering, renaming, and multi-delete.
- [x] **LLM Retry Mechanism**: Automatic retry with exponential backoff (up to 3 attempts) on transient LLM errors (503, rate limits, connection issues). Configurable via `llm_max_retries` and `llm_retry_base_delay`.

## Core & Architecture Improvements
- [ ] **Type Hinting**: Add comprehensive Python type hints (especially for variables initialized to `None`) to improve IDE autocomplete, static analysis, and code maintainability.
- [ ] **Asynchronous Remote OCR Service**: When the remote OCR source is enabled, start the service asynchronously. Disable the capture and multi-select buttons until the service port is successfully polled. Ensure that if the app starts the service, it correctly kills it upon exiting.
- [ ] **Application Initialization State**: Introduce a "Ready" popup indicating that initialization has finished. Prevent showing the control panel or accepting keyboard shortcuts until the application is fully loaded.

## UI/UX Enhancements
- [ ] **Popup Sizing Stability**: Fix the issue where small prompt popups dynamically change sizes (starting large and subsequently shrinking).
- [ ] **Large Output Scroll Position**: Maintain the user's scroll position when large chunks of text are streamed into the popup.
- [ ] **Audio Recording UI**: Improve visual feedback during audio recording with better indicators and controls.

## Processing & Integration
- [ ] **Text-to-Speech (TTS) Improvements**: Enhance the TTS feature to read one sentence at a time, and include UI controls (buttons) to skip forward or backward through the spoken sentences.
- [ ] **Grammar & Accuracy Corrections**: Introduce a dedicated feature/button to analyze and correct the grammar or factual accuracy of the extracted or generated text.
- [ ] **Local LLM Integration Tests**: Add robust integration tests that utilize a simple, small, local LLM model to verify the end-to-end processing pipeline offline.
- [ ] **Speech Recognition Enhancements**: Improve speech recognition accuracy with better noise cancellation and language detection.

## Audio & Speech Features
- [ ] **Multiple Language Support**: Add support for multiple languages in speech recognition and TTS.
- [ ] **Audio Level Visualization**: Add real-time audio level visualization during recording.
- [ ] **Fix Recording from Meetup Calls**: Investigate and fix issues with recording audio from Meetup/virtual meeting applications.
- [ ] **Dual Audio Channel Recording**: Listen to both microphone and speaker simultaneously and record them as separate sentences, enabling speaker-attributed transcription.

## Remote Control & Android Integration
- [ ] **Android Session Browsing**: Allow browsing sessions and retrieving response images directly in the Android app.
- [ ] **Touch Gestures**: Add pinch-to-zoom and multi-finger gestures on the Android touchpad.

## Session & Data Management
- [ ] **Elaborate Session Structure**: Create a richer session folder structure that includes:
    - Transcription with speaker name attribution
    - Captured OCR images
    - Response images
    - Prompts and response text
    - Organized in a clean folder hierarchy per session
    - Update the session browser UI to support browsing and displaying all of these artifacts.

## Testing & Quality Assurance
- [ ] **Cross-Platform Testing**: Improve testing coverage for different operating systems (Windows, macOS, Linux).
- [ ] **Error Recovery Testing**: Enhance testing for error recovery and fallback mechanisms.
- [ ] **Audio Device Compatibility**: Improve testing with various audio devices and configurations.

## Documentation
- [ ] **User Guide**: Create comprehensive user guide with screenshots and tutorials.
- [ ] **Troubleshooting Guide**: Expand troubleshooting section with common issues and solutions.