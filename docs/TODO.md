# Roadmap & Future Features

This document tracks planned features, enhancements, and known issues that need to be addressed in future updates.

## Recently Completed Features
- [x] **Audio Input Source**: Implemented speech recognition using Google Speech-to-Text for audio input.
- [x] **Multiple Input Sources**: Added support for text, image, and audio input sources with easy switching.
- [x] **Audio Device Configuration**: Added configurable audio input and output devices for speech recognition and TTS.
- [x] **Enhanced Hotkeys**: Expanded hotkey system to include multi-capture, panel toggle, session management, and more.
- [x] **Speech Recognition Warmup**: Implemented warmup functionality for speech recognition engine.
- [x] **E2E Audio Testing**: Added comprehensive E2E tests for audio recording and TTS functionality.
- [x] **Remote OCR Service**: Implemented remote PaddleOCR service for offloaded text extraction.
- [x] **Session Browser**: Full-featured session browser dialog with tree view, prompt/response panels, tag management, filtering, renaming, and multi-delete.
- [x] **Shiki Syntax Highlighting**: Migrated code highlighting from highlight.js to Shiki for superior theme support and language coverage.
- [x] **Mermaid Diagram Rendering**: Fixed Markdown renderer to correctly parse and display Mermaid diagrams inside the popup.
- [x] **Draggable & Resizable Popup**: Popup window can now be dragged and resized by the user with edge/corner handles.
- [x] **Hide/Unhide All Widgets**: Added a hotkey (`Ctrl+Alt+Shift+V`) to toggle visibility of all overlay widgets at once.
- [x] **Stealth Mode (Hide from Capture)**: Windows can be excluded from screen-capture APIs (OBS, video calls, Win+Shift+S) while remaining visible on the user's monitor.
- [x] **Remote Control Server (Android)**: WebSocket-based remote control server enabling an Android companion app to control mouse, trigger actions, and receive UI state updates over LAN.
- [x] **Android Companion App**: Kotlin/Gradle companion app with touchpad-style mouse control, action buttons synchronized with main app, auto-connect, and text input.
- [x] **Open Code in IDE**: Right-click any code block in the popup to open it directly in PyCharm or Antigravity IDE, with language-aware temp file creation.
- [x] **Response Image Sharing**: Capture and share response screenshots with the connected Android app.
- [x] **URL Input Popup**: Open any URL directly in the popup's web view via hotkey (`Ctrl+Alt+U`).
- [x] **Physical Mouse Blocking**: Block physical mouse input while Android remote control is active, allowing only injected (pyautogui) events through. Automatically re-enables after an idle timeout.
- [x] **WebSocket Migration**: Migrated remote control server from HTTP polling to WebSocket for lower latency, real-time state push, and message coalescing for high-frequency mouse events.
- [x] **Opacity Fix**: Fixed popup/panel opacity setting to correctly apply using `setWindowOpacity()`.
- [x] **Scrolling Fix**: Fixed scrolling issues in the popup web view.
- [x] **Quit App Hotkey**: Added `Ctrl+Alt+Shift+Q` hotkey for graceful application exit.

## Core & Architecture Improvements
- [ ] **Type Hinting**: Add comprehensive Python type hints (especially for variables initialized to `None`) to improve IDE autocomplete, static analysis, and code maintainability.
- [x] **Migrate to Qt**: Completed. The UI now uses PyQt6 with QWebEngineView, rendering Markdown via marked.js, LaTeX via KaTeX, and diagrams via Mermaid.js.
- [ ] **Asynchronous Remote OCR Service**: When the remote OCR source is enabled, start the service asynchronously. Disable the capture and multi-select buttons until the service port is successfully polled. Ensure that if the app starts the service, it correctly kills it upon exiting.
- [ ] **Application Initialization State**: Introduce a "Ready" popup indicating that initialization has finished. Prevent showing the control panel or accepting keyboard shortcuts until the application is fully loaded.

## UI/UX Enhancements
- [x] **Cancel Global Operation**: Implemented a unified "Cancel" action that interrupts both prompt processing and multi-select sequences.
- [ ] **Popup Sizing Stability**: Fix the issue where small prompt popups dynamically change sizes (starting large and subsequently shrinking).
- [ ] **Large Output Scroll Position**: Maintain the user's scroll position when large chunks of text are streamed into the popup.
- [ ] **Pre-allocate Space for Large Responses**: For large outputs, pre-allocate a configurable number of lines (e.g., 100) to allow smooth scrolling while text is actively streaming in.
- [ ] **Active Profile Placement**: Move the active profile selection setting to the main application tab for easier access.
- [x] **Opacity Setting Fix**: Fixed — uses `setWindowOpacity()` for correct translucency on both the popup and control panel.
- [x] **Mermaid Diagram Rendering**: Fixed — Mermaid blocks are now extracted before Markdown parsing, restored as `<div class="mermaid">`, and rendered by `mermaid.init()`.
- [ ] **Popup State Reset**: Ensure that consecutive LLM responses correctly clear and reset the popup text instead of appending to stale content.
- [ ] **Audio Recording UI**: Improve visual feedback during audio recording with better indicators and controls.

## Processing & Integration
- [ ] **LLM Retry Mechanism**: Implement an automatic retry mechanism (up to 3 times) with a 5-second timeout if the LLM provider returns a high-demand error (`code: 503, status: UNAVAILABLE`). This should apply when processing the main model, or the fallback model if the main model has not yet responded.
- [ ] **Large Text Extraction**: Automatically extract exceptionally large chunks of text (like raw HTML) into separate output files rather than crowding the main popup window.
- [ ] **Text-to-Speech (TTS) Improvements**: Enhance the TTS feature to read one sentence at a time, and include UI controls (buttons) to skip forward or backward through the spoken sentences.
- [ ] **Grammar & Accuracy Corrections**: Introduce a dedicated feature/button to analyze and correct the grammar or factual accuracy of the extracted or generated text.
- [ ] **Local LLM Integration Tests**: Add robust integration tests that utilize a simple, small, local LLM model to verify the end-to-end processing pipeline offline.
- [ ] **Speech Recognition Enhancements**: Improve speech recognition accuracy with better noise cancellation and language detection.

## Audio & Speech Features
- [ ] **Multiple Language Support**: Add support for multiple languages in speech recognition and TTS.
- [ ] **Audio Level Visualization**: Add real-time audio level visualization during recording.
- [ ] **Voice Activity Detection**: Implement voice activity detection to automatically start/stop recording.
- [ ] **Custom Wake Words**: Add support for custom wake words to trigger audio recording.

## Remote Control & Android Integration
- [ ] **Android App Response Viewer**: Display rendered Markdown responses directly in the Android app instead of relying on a screenshot image.
- [ ] **Multi-device Support**: Allow multiple Android clients to connect simultaneously with conflict resolution.
- [ ] **Android App Settings Sync**: Mirror relevant configuration settings from the main app to the Android companion.
- [ ] **Touch Gestures**: Add pinch-to-zoom and multi-finger gestures on the Android touchpad.

## Testing & Quality Assurance
- [ ] **Cross-Platform Testing**: Improve testing coverage for different operating systems (Windows, macOS, Linux).
- [ ] **Performance Benchmarking**: Add performance benchmarks for different components and configurations.
- [ ] **Error Recovery Testing**: Enhance testing for error recovery and fallback mechanisms.
- [ ] **Audio Device Compatibility**: Improve testing with various audio devices and configurations.

## Documentation
- [ ] **User Guide**: Create comprehensive user guide with screenshots and tutorials.
- [ ] **API Documentation**: Add API documentation for external integrations.
- [ ] **Troubleshooting Guide**: Expand troubleshooting section with common issues and solutions.
- [ ] **Configuration Examples**: Add more configuration examples for different use cases.