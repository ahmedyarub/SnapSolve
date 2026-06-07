# Features Breakdown

The Screen Capture & QA application provides several customizable features organized by their role in the processing pipeline.

## Controls & Configuration

*   **Keyboard Shortcuts:** Customizable global hotkeys (e.g., `Ctrl+Alt+Shift+C`) trigger actions (like Capture, Reselect, Multi-select, Toggle Panel, New Session, Open URL, Session Browser, Quit) without needing the app to be in focus.
*   **Control Panel:** An optional floating toolbar to visually trigger key actions and view status.
*   **Configuration UI:** A user-friendly settings dialog with tabs for modifying Application Settings, Profile Settings, Keyboard Shortcuts, Warmup Settings, and Remote Control settings without manually editing JSON files.
*   **Active Profile Placement:** The active profile selector is placed on the main application tab for quick access.
*   **Background Mode:** Run the application minimized to the system tray, freeing up taskbar space.
*   **Profiles:** Define and switch between distinct configurations (e.g., "Fast Image Processing", "Deep Text Analysis"). Each profile stores its specific `llm_engine`, model, `ocr_engine`, prompt, and fallback model settings.
*   **Audio Device Configuration:** Configure specific audio input devices for speech recognition and output devices for TTS.
*   **Session Browser:** A full-featured dialog to browse past sessions, view prompts and formatted responses, rename sessions, and add tags for filtering. Accessible via hotkey (`Ctrl+Alt+Shift+B`) or from the control panel.
*   **Quit App:** Graceful application exit via hotkey (`Ctrl+Alt+Shift+Q`) or system tray menu.

## Source (Data Gathering)

*   **Multiple Input Sources:**
    *   **Text Input:** Direct text entry via the control panel for questions and queries. Supports browsing previously submitted prompts with Up/Down arrow keys. Consecutive duplicate prompts are automatically deduplicated. History is persisted across sessions in `config/prompt_history.json`.
    *   **Image Capture:** Fast screen capture of user-defined rectangular areas.
    *   **Audio Input:** Real-time audio recording with speech recognition using Google Speech-to-Text.
*   **Coordinate Reselection:** Easily draw a new bounding box to update the capture area while the application is running.
*   **Multi-Select:** Capture multiple disparate areas of the screen and aggregate them into a single request.
*   **OCR-to-Text-Box (Autosubmit):** An "Autosubmit" checkbox on the control panel (visible in image/OCR mode, enabled by default) controls how OCR'd text is handled. When **enabled**, captured text is sent directly to the LLM as before. When **disabled**, OCR'd text is placed into the text input box for review and editing before manual submission. In multi-capture mode with Autosubmit off, each capture incrementally appends text to the text box, and "End Multi" leaves the accumulated text for the user to review — it does not submit automatically. The text box appears on first OCR capture and disappears after submission or manual close.
*   **Text or Image Input:** Depending on the setup, the application can extract raw text (using OCR) or send the raw image directly to vision-capable engines.
*   **Audio Recording:** Background audio recording with visual feedback and automatic transcription.
*   **Voice Activity Detection:** Automatic start/stop of recording based on detected voice activity.
*   **Real-time Transcription:** WhisperLive integration for live subtitle display during recording, with configurable pause threshold and subtitle double-click to submit.
*   **Session-Scoped Periodic Screenshots:** Automatic full-screen screenshot capture during active sessions, stored in `sessions/<uuid>/screenshots/` with timestamped filenames (e.g., `2026-06-06_10-30-15.png`). Supports two capture triggers: time-based (configurable interval, default 15s) and activity-based (keyboard/mouse events with configurable minimum delay, default 5s). Toggleable at runtime via control panel button, Android app, CLI (`--enable-periodic-screenshots`), and config UI.
*   **App & Window Name Tracking:** Records the active foreground application name, process name, and window title alongside each periodic screenshot as a JSON sidecar file (`<timestamp>.json`). The Session Timeline displays this data as coloured app spans in a dedicated track between the filmstrip and event markers, making it easy to see which application was in use at each moment. Hover to see the full window title. Enabled by default when periodic screenshots are active; configurable via Settings UI (`track_active_window`).
*   **Transcription Language Selection:** Configurable transcription language (27 languages + auto-detect) exposed in config UI, control panel (audio mode), Android app, and CLI (`--transcription-language`). Passed to both WhisperLive and Google Speech Recognition.
*   **TTS Language Selection:** Separate text-to-speech language setting available in config UI, CLI (`--tts-language`), and test_sound sanity test. Maps to Piper TTS voice models per language.
*   **Translation Language:** Optional real-time translation of transcribed audio into a configurable target language. When enabled, WhisperLive translates completed segments and subtitles display the translated text. Configurable via config UI (`Translation Language` dropdown), control panel (audio mode), and CLI (`--translation-language`). Set to empty/"None" to disable.

## Prompt & Enrichment

*   **Chat Session History:** Maintains context over multiple queries. The conversation is saved locally, and the previous context is stitched into the prompt or passed via API (depending on the engine) to allow for conversational follow-ups.
*   **Custom Prompting:** Allows defining custom instructions (via `config/prompts.json`) to dictate how the LLM should format or structure its response.
*   **Context Chat Sessions:** Configurable option to include conversation context in prompts for follow-up questions. Can be toggled at runtime via hotkey.

## Session Management

*   **Per-Session Folder Structure:** Each session is stored in its own folder (`sessions/<uuid>/`) containing:
    *   `session.json` — session metadata and interaction history
    *   `images/` — captured OCR images named by interaction index
    *   `transcription.txt` — speaker-attributed transcription log
*   **Speaker Name Attribution:** Transcription segments are prefixed with the configured speaker name (e.g., `[interviewer] Hello world`). The speaker name is configurable via the Settings UI and stored per-session and per-interaction.
*   **Image Saving:** Captured images are automatically saved to the session's `images/` folder (enabled by default, configurable via Settings UI).
*   **Legacy Session Migration:** Existing flat-file sessions (`sessions/<uuid>.json`) are transparently migrated to the new folder structure on first access.
*   **Session Browser:** Browse all past sessions in a tree view with source-type icons (🎤 audio, 🖼️ image, 💬 text). Click any prompt to view its full text with speaker attribution, source type, and attached image indicators, plus the formatted response rendered with Markdown, KaTeX, Shiki syntax highlighting, and Mermaid diagrams.
*   **Session Renaming:** Right-click a session to rename it for easier identification.
*   **Session Tagging:** Add comma-separated tags to sessions for categorization and future filtering.
*   **Natural Language Semantic Search:** Search across all sessions using local (sentence-transformers) or remote (Gemini) embeddings. Filter by prompt, response, transcription, app name, and summary. Navigates between results using next/previous buttons.
*   **Tag Filtering:** Use the filter bar to search sessions by name, title, or tags.
*   **Session Deletion:** Delete one or multiple sessions (with multi-select) via right-click menu or the Delete key. The entire session folder is removed.
*   **Empty Session Filtering:** Empty sessions (with no interactions) are automatically excluded from the browser.
*   **Session Timeline View:** Screenpipe-inspired visual timeline in the Session Browser showing periodic screenshots as a scrollable filmstrip, event markers for different interaction types (🎤 audio, 🖼️ OCR, 📐 multi-select, 💬 text, 📝 transcription) with a time ruler. Features a draggable playhead that updates the screenshot preview and shows nearby transcription context. Clicking a transcription line jumps the timeline to that moment; clicking an event marker selects the corresponding prompt in the tree. Collapsible for space efficiency.
*   **Transcription Persistence:** Audio transcriptions are saved to per-session transcription files with speaker attribution.
*   **Auto-Summarize Transcription:** Automatically generate and save a summary of the entire audio conversation to the transcription file when recording stops. Configurable with a custom prompt prefix via the Configuration UI.
*   **Context Manager:** Per-session context configuration dialog with:
    *   **Category Toggles:** Enable/disable inclusion of transcribed text, previous questions, and previous answers in the LLM prompt context. All categories are disabled by default.
    *   **Project Folder:** Set a local project directory for the session (used by the Antigravity engine for agentic coding). The text field autocompletes from recently used folder paths.
    *   **Session Import:** Import context categories from a previous session into the current one.

## Engine (Processing)

*   **Multiple LLM Engines:**
    *   `gemini`: Uses the Google Gemini CLI.
    *   `google-genai`: Uses the official Python SDK for Google GenAI with streaming and multi-turn history.
    *   `ollama`: Integrates with a local Ollama server, avoiding external network requests.
    *   `antigravity`: Uses the Google Antigravity SDK via a local FastAPI service. Provides agentic coding capabilities with full project context, streaming SSE responses, and multi-turn conversation support.
*   **Fallback Capability:** Configure a secondary model that runs concurrently with the main model. If the main model fails or takes too long, the application gracefully defaults to the fallback model to ensure a response is always generated.
*   **Local OCR (PaddleOCR):** For workflows requiring precise text extraction prior to LLM processing, PaddleOCR can be configured to process the screen capture entirely on your local machine.
*   **Remote OCR:** Offload OCR processing to a remote PaddleOCR FastAPI service.
*   **Concurrent Execution & Warmup:** Models are preloaded (warmed up) during application startup for reduced latency. Configurable warmup for OCR, LLM, TTS, speech recognition, and real-time transcription.
*   **Speech Recognition:** Google Speech-to-Text integration for audio input processing with configurable warmup.
*   **Automatic LLM Retry:** Automatic retry with exponential backoff (up to 3 attempts, configurable) when LLM providers return transient errors such as `503 UNAVAILABLE`, rate limits, or connection failures. Retries are cancellable and show status updates in the popup.

## Sink (Output Generation)

*   **Popup Sink:** Displays responses in an unobtrusive, frameless window.
    *   Supports dynamic resizing based on text length.
    *   Renders rich Markdown via QWebEngineView with marked.js, including bold, italics, lists, Markdown tables, LaTeX math (KaTeX), and Mermaid diagrams.
    *   Syntax-highlighted code blocks via Shiki with dark theme integration.
    *   Configurable opacity for visual integration.
    *   Draggable via title bar and resizable via edge/corner handles.
    *   "Open in IDE" context menu — right-click any code block to open it in PyCharm or Antigravity IDE. The user's prompt is automatically prepended as a language-appropriate block comment so AI agents in the IDE know what was generated.
    *   Proper state reset between consecutive LLM responses.
*   **Audio Sink (TTS):** Uses local Text-to-Speech (Piper) to read the answer aloud asynchronously, allowing you to hear the response without breaking your workflow.
    *   Support for multiple voice models (.onnx format).
    *   Configurable audio output devices.
    *   Model warmup for reduced latency.
    *   Markdown stripping before synthesis.
*   **Composite Output:** Simultaneous popup and audio output with synchronized streaming.

## UI Features

*   **Draggable Windows:** All overlay windows (popup, control panel, subtitles) can be dragged to any position on screen.
*   **Resizable Popup:** The popup window supports edge and corner resizing with minimum size constraints.
*   **Hide/Unhide All Widgets:** Toggle visibility of all overlay widgets at once via hotkey (`Ctrl+Alt+Shift+V`).
*   **Stealth Mode (Hide from Capture):** Configurable option to exclude all SnapSolve windows from screen-capture APIs (OBS, video calls, Win+Shift+S, etc.) while remaining visible on the user's monitor. Uses `SetWindowDisplayAffinity` on Windows 10 2004+ and `NSWindow.setSharingType` on macOS (requires `pyobjc-framework-Cocoa`). Not supported on Linux (no universal X11/Wayland API).
*   **URL Viewer:** Open any URL directly in the popup's web view via hotkey (`Ctrl+Alt+U`), allowing quick reference without switching windows.
*   **Real-time Subtitles:** WhisperLive-powered subtitle widget with fading effects, positioned at the bottom of the screen during audio recording.

## API, Remote Control & Android Integration

*   **Unified API Server:** A local FastAPI-based server (`http://0.0.0.0:3031`) exposing both REST endpoints (Screenpipe-inspired endpoints like `/sessions`, `/search`, `/health`, `/config` and Android parity endpoints like `/response_image/ack`, `/config/transcription_language`) and a legacy WebSocket endpoint (`/ws`) for the Android companion app. Supports optional API key authentication and includes a Swagger UI at the root (`/`).
*   **Mouse Control:** Relative mouse movement, click (left/right/middle), double-click, drag (start/end), and scroll via REST endpoints or the Android touchpad.
*   **Physical Mouse Blocking:** Blocks physical mouse input while Android remote control is active using a `WH_MOUSE_LL` hook. Injected (pyautogui) events pass through. Automatically re-enables after a configurable idle timeout.
*   **Action Dispatch:** Trigger any SnapSolve action (capture, reselect, multi-capture, cancel, cycle source, toggle panel, new session, etc.) from the Android app.
*   **Button State Sync:** Real-time button visibility and state synchronization between the main app and the Android companion.
*   **Text Input:** Type and submit text directly from the Android app via the `keyboard_type` message.
*   **Response Image Sharing:** Capture and share response screenshots with the connected Android app over HTTP.
*   **Android Response Viewer:** View rendered Markdown responses directly in the Android app without relying on screenshots.
*   **Configurable Mouse Sensitivity:** Adjustable mouse sensitivity for remote control touchpad.
*   **Android Companion App:** Kotlin/Gradle companion app with touchpad-style mouse control, synchronized action buttons, auto-connect, and text input.

## Performance & Reliability

*   **Engine Warmup:** Pre-loading of OCR, LLM, TTS, speech recognition, and real-time transcription engines during startup, each independently configurable.
*   **Concurrent Processing:** Parallel model execution for fallback scenarios and non-blocking operations.
*   **Error Handling:** Graceful degradation on component failures with user-friendly error messages.
*   **Thread Safety:** All UI updates from background threads are properly dispatched to the main thread via Qt signals/slots.
*   **Resource Management:** Efficient resource utilization with proper cleanup and state management.
*   **DPI Awareness:** Windows DPI awareness enabled early in lifecycle to prevent coordinate mismatches between screen capture and UI overlays.
*   **WebSocket Message Coalescing:** High-frequency mouse-move events are coalesced to process only the latest position, preventing backlog during remote control.

## Testing & Development

*   **End-to-End Testing:** Comprehensive E2E tests that verify core functionality through automated UI interaction with image recognition.
*   **Sanity Tests:** Standalone test scripts for component verification (OCR, audio, WhisperLive warmup, etc.).
*   **Audio Testing:** Support for virtual audio devices (VB-Audio Virtual Cable) for TTS and speech recognition testing.
*   **Automated UI Testing:** PyAutoGUI integration for automated UI interaction testing.
*   **Static Analysis:** Ruff linting, Qodana, SonarQube, and Kotlin/Android lint via verification scripts.