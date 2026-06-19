# Roadmap & Future Features

This document tracks planned features, enhancements, and known issues that need to be addressed in future updates.

## Recently Completed Features
- [x] **Optional Translation Language**: Configurable real-time translation of transcribed audio via WhisperLive. Target language selectable in config UI, control panel (audio mode), and CLI (`--translation-language`). Translated text displayed in subtitles; original transcription saved to session files.
- [x] **Session Timeline View**: Screenpipe-inspired visual timeline in the Session Browser with screenshot filmstrip, event markers (audio, OCR, multi-select, text, transcription), draggable playhead, time ruler, and clickable transcription context panel. Clicking transcription lines or event markers navigates the timeline bidirectionally.
- [x] **Summarize Audio Conversation**: Added the ability to automatically summarize an entire audio conversation when recording stops, appending a concise summary to the full transcription file.
- [x] **App & Window Name Tracking**: Records the active foreground application name, process name, and window title alongside each periodic screenshot as a JSON sidecar file. Displayed on the Session Timeline as coloured app spans with hover tooltips. Configurable via `track_active_window`.
- [x] **MCP Server**: Implemented a Model Context Protocol (MCP) server using FastMCP to expose SnapSolve session history, OCR texts, and transcriptions to external IDEs (Claude Desktop, Cursor).
- [x] **Webhook / Post-Session Actions**: After a session ends or a summary is generated, trigger configurable HTTP webhook actions (e.g., send summary to Slack, create Jira ticket). Also triggerable manually from the Session Browser.
- [x] **Audio Level Visualization**: Added a real-time audio volume progress bar to the control panel during audio recording. Configurable via Settings UI.
- [x] **Dual Audio Channel Recording** `[Screenpipe]`: Listen to both microphone and speaker simultaneously and record them as separate sentences, enabling speaker-attributed transcription.
- [x] **Speaker Diarization** `[Screenpipe]`: Add speaker identification to transcription segments beyond dual-channel recording. Use `pyannote-audio` or WhisperX for voice-profile-based diarization to label speakers by name.
- [x] **Real-time Speech Correction**: Mid-recording LLM feedback loop with fact-checking, grammar correction, and content suggestions. Configurable per-profile correction model, rolling window size, and editable prompts.

## Core & Architecture Improvements
- [ ] **Dynamic Configuration**: Change configs dynamically (especially audio input/output and profile)
- [ ] **Simultaneous Transcription**: Enable transcription simultaneously with OCR and text input (do not cancel recording when cycling source)
- [ ] **Type Hinting**: Add comprehensive Python type hints (especially for variables initialized to `None`) to improve IDE autocomplete, static analysis, and code maintainability.
- [ ] **Asynchronous Remote OCR Service**: When the remote OCR source is enabled, start the service asynchronously. Disable the capture and multi-select buttons until the service port is successfully polled. Ensure that if the app starts the service, it correctly kills it upon exiting.
- [ ] **Application Initialization State**: Introduce a "Ready" popup indicating that initialization has finished. Prevent showing the control panel or accepting keyboard shortcuts until the application is fully loaded.
- [ ] **Better Parsing of Verification Results**: Improve parsing and formatting of verification script (`verify.ps1`/`verify.sh`) output to provide clearer, more structured results.

## UI/UX Enhancements
- [ ] **Quick Context Switching**: Allow switching theme/context/session easily
- [ ] **Simplify Control Panel**: Hide control panel buttons that are not used frequently
- [ ] **Simplify Config UI**: Hide config UI options that are not used frequently
- [ ] **Popup Sizing Stability**: Fix the issue where small prompt popups dynamically change sizes (starting large and subsequently shrinking).
- [ ] **Large Output Scroll Position**: Maintain the user's scroll position when large chunks of text are streamed into the popup.
- [ ] **Audio Recording UI**: Improve visual feedback during audio recording with better indicators and controls.

## Processing & Integration
- [ ] **Text-to-Speech (TTS) Improvements**: Enhance the TTS feature to read one sentence at a time, and include UI controls (buttons) to skip forward or backward through the spoken sentences.
- [x] **Grammar & Accuracy Corrections**: Introduced a dedicated real-time correction feature that analyzes speech during recording with configurable fact-checking, grammar, and content suggestion types.
- [ ] **Personalized Answers**: Add personalized answer capabilities that tailor LLM responses based on user preferences or user profile.
- [ ] **Context & Integrations Architecture**: Implement a dual-path context injection system for LLMs:
    - [ ] **Bounded Context (Interviews)**: Add UI and `SessionManager` capability to attach local folders. Serialize folder contents directly into the LLM system prompt for zero-latency context loading.
    - [ ] **Agentic Context (Projects)**: Implement a Model Context Protocol (MCP) Client to enable lazy tool-calling.
    - [ ] **MCP Servers Setup**: Configure settings to connect to standard open-source MCP servers for Jira, Confluence, and large local filesystems.
    - [ ] **LLM Engine Updates**: Update LLM engines to support dynamic tool calling so models can query external data sources based on audio/OCR triggers.
    - [x] **Antigravity Integration**: `AntigravityEngine` communicates with a local FastAPI service that wraps the Google Antigravity SDK, enabling agentic coding with streaming SSE responses and project folder context.
- [ ] **Local LLM Integration Tests**: Add robust integration tests that utilize a simple, small, local LLM model to verify the end-to-end processing pipeline offline.

## Audio & Speech Features
- [ ] **Speech Recognition Enhancements**: Improve speech recognition accuracy with better noise cancellation and language detection.
- [ ] **Fix Recording from Meetup Calls**: Investigate and fix issues with recording audio from Meetup/virtual meeting applications.

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

## Screenpipe-Inspired Features

Features identified from a deep comparison with [Screenpipe](https://github.com/screenpipe/screenpipe), a complementary open-source 24/7 screen + audio recording tool. See [snapsolve_vs_screenpipe.md](../docs/snapsolve_vs_screenpipe.md) for the full analysis.

### Extensibility & API
- [ ] **Obsidian Integration**: Obsidian integration (read/write)
- [x] **REST API** `[Screenpipe]`: Added a lightweight local REST API (default `localhost:3031`) exposing session data and query endpoints (`GET /sessions`, `GET /sessions/{id}`, `GET /search`, `GET /tags`, `POST /action`, `GET /config`, `GET /health` with downstream status, `POST /response_image/ack`, `POST /config/transcription_language`). This unlocks third-party integrations without building each one manually, complete with Swagger UI.
- [x] **MCP Server** `[Screenpipe]`: Expose SnapSolve's session history, captured OCR text, and transcription data as an MCP server so external AI tools (Claude Desktop, Cursor, VS Code) can query past sessions.
- [ ] **Plugin System (Pipes-Inspired)** `[Screenpipe]`: Implement a plugin/extension framework for context providers and post-session actions. Screenpipe uses markdown-defined "Pipes" — SnapSolve could adopt a similar pattern for community-built extensions (e.g., Jira sync, Obsidian export, Notion push).
- [ ] **SDK for Integrations** `[Screenpipe]`: Provide a lightweight Python SDK or documented API contract that allows developers to build custom tools on top of SnapSolve's capture and session data.

### Capture & Context
- [ ] **Accessibility Tree Capture** `[Screenpipe]`: Use the OS accessibility tree (UI Automation on Windows) as a faster primary text extraction method, falling back to PaddleOCR when structured UI data is unavailable (e.g., images, remote desktops).
- [x] **App & Window Name Tracking** `[Screenpipe]`: Record the active application name and window title alongside each capture. Useful for session review, filtering, and analytics.
- [ ] **Browser URL Tracking** `[Screenpipe]`: Capture the current browser URL when performing screen capture from a browser window. Enables linking captures back to source pages.
- [x] **Session-Scoped Periodic Screenshots** `[Screenpipe]`: During active sessions, capture periodic full-screen screenshots (configurable interval, e.g., every 10–30 seconds) with optional keyboard/mouse activity triggers. Store in a `screenshots/` subfolder within the active session folder (`sessions/<uuid>/screenshots/`) with filenames including the date and time (e.g., `2026-06-06_10-30-15.png`). Configurable via config UI, CLI, control panel, and Android app.

### Privacy & Security
- [ ] **PII Filtering** `[Screenpipe]`: Add AI-based PII redaction (names, emails, phone numbers, SSNs) to OCR text and transcriptions before sending to cloud LLM APIs. Critical for SaaS trust and enterprise adoption.
- [ ] **Encryption at Rest** `[Screenpipe]`: Optionally encrypt session data (JSON files, images, transcriptions) stored on disk using a user-provided key or OS credential store.

### Search & Review
- [ ] **Timeline Summarization**: Summarize whole timeline and not just transcription
- [x] **Natural Language Session Search** `[Screenpipe]`: Enable semantic search across all session history using embeddings (e.g., Gemini `text-embedding-004`). Allow queries like "What did the interviewer ask about microservices?" across weeks of sessions.
- [x] **Session Timeline View** `[Screenpipe]`: Add a visual timeline for each session showing timestamped events (recording start, screenshots, OCR captures, LLM queries, responses) rendered in the Session Browser.
- [ ] **Auto-Summary on Session End** `[Screenpipe]`: Automatically generate a structured summary (key topics, questions asked, answers given, action items) when a session ends. Store as `session_summary.md` in the session folder.

## Meetily-Inspired Features

Features identified from a deep comparison with [Meetily](https://github.com/Zackriya-Solutions/meetily), a privacy-first AI meeting assistant built with Tauri/Rust. Meetily excels at professional audio processing, audio file import, and structured summary generation. See the [feature import analysis](../../.gemini/antigravity-ide/brain/bd693c78-d1de-4f41-9645-44d22c143576/analysis_results.md) for the full comparison.

### Audio Processing
- [ ] **Audio File Import & Re-transcription** `[Meetily]`: Import pre-recorded audio files (MP3, WAV, M4A, FLAC, OGG, etc.) as new sessions, similar to Meetily's `import.rs` pipeline. Decode → resample to 16kHz → VAD segmentation → WhisperLive transcription → save to session with progress tracking. Also allow re-processing an existing session's audio with a different transcription model or language, similar to Meetily's `retranscription.rs`. Use `pydub` or `ffmpeg` subprocess for decoding.
- [ ] **Audio Enhancement Pipeline** `[Meetily]`: Add a 3-stage real-time audio processing pipeline before sending microphone audio to WhisperLive, inspired by Meetily's `audio_processing.rs`. Stages: (1) high-pass filter at 80 Hz to remove low-frequency rumble/A/C hum using `scipy.signal`, (2) neural noise suppression (10-15 dB reduction) using `noisereduce` (Python equivalent of Meetily's RNNoise/`nnnoiseless`), (3) EBU R128 loudness normalization to -23 LUFS with true peak limiting using `pyloudnorm`. Apply in `SoundSource` in order: high-pass → denoise → normalize.
- [ ] **Audio Device Disconnect Detection** `[Meetily]`: Detect audio device disconnection (Bluetooth headphones dying, USB mic unplugged) during recording and report specific error types for graceful degradation, similar to Meetily's `AudioCapture.handle_stream_error()` with pattern-matched error strings for device unavailability, permission issues, and stream failures.
- [ ] **Incremental Audio Checkpoint Saving** `[Meetily]`: Periodically save audio recording checkpoints during active sessions so raw audio data isn't lost if the app crashes, similar to Meetily's `incremental_saver.rs`. Store checkpoint files in the session's folder alongside the existing transcription persistence.

### Summary & LLM
- [ ] **Summary Templates** `[Meetily]`: Add predefined summary template formats (meeting minutes, action items, key decisions, Q&A extraction, lecture notes, interview prep) selectable from a dropdown in the config UI, inspired by Meetily's `summary/templates/` system. Store templates in `config/summary_templates.json` with fields for `name`, `prompt`, `output_format`, and `use_case`. Substitute the selected template's prompt for the current `summary_prompt_prefix` in the auto-summarize flow.
- [ ] **Universal LLM Provider Support (LiteLLM)** `[Pipecat/Meetily]`: Both Meetily (Claude, Groq, OpenRouter, CustomOpenAI) and Pipecat (100+ service integrations) support far more LLMs than SnapSolve. Integrate [LiteLLM](https://github.com/BerriAI/litellm) to replace or supplement existing engines. LiteLLM uses the standard OpenAI API format to call Anthropic, Groq, Mistral, DeepSeek, AWS Bedrock, Azure, OpenRouter, and local OpenAI-compatible servers (vLLM, LM Studio). This requires creating a single `LiteLLMEngine` in `core/llm/` that takes a generic `model_string` (e.g., `anthropic/claude-3-opus-20240229`, `groq/llama3-70b-8192`, `openai/gpt-4o`) and handles routing, unifying all API access into one file.

## Pipecat-Inspired Features

Features and architectural patterns identified from [Pipecat](https://github.com/pipecat-ai/pipecat), an open-source Python framework for building real-time voice and multimodal conversational AI agents. Pipecat's strength is its composable pipeline architecture and multi-agent coordination. See the [feature import analysis](../../.gemini/antigravity-ide/brain/bd693c78-d1de-4f41-9645-44d22c143576/analysis_results.md) for the full comparison.

### Architecture
- [ ] **Composable Pipeline Architecture** `[Pipecat]`: Refactor the monolithic `process_pipeline()` in `core/pipeline/pipeline.py` into a composable, frame-based pipeline inspired by Pipecat's processor architecture. Define a `Processor` base class with a `process(frame) → frame` signature, frame types (`AudioFrame`, `TextFrame`, `ImageFrame`, `LLMResponseFrame`), and pipeline as a list of processors (e.g., `[Source, AudioEnhancer, STT, LLM, CorrectionProcessor, Sink]`). This would make adding new processing steps (PII filtering, translation, audio enhancement, routing) modular instead of requiring modifications to the pipeline monolith. The existing `ConcurrentSinkWrapper` already hints at this pattern.
- [ ] **Automatic Source-Based Routing** `[Pipecat]`: Instead of requiring manual profile switching, automatically route different input types to specialist prompts/models based on the active source, inspired by Pipecat's multi-agent specialist handoff pattern. OCR captures → a "code analysis" specialist prompt, audio transcriptions → a "meeting notes" specialist, text input → a "Q&A" specialist. Extends the existing profiles system with auto-selection rules.
- [ ] **Structured Conversation Flows** `[Pipecat]`: Implement a conversation state machine for structured interview workflows, inspired by [Pipecat Flows](https://github.com/pipecat-ai/pipecat-flows). Define a question flow (e.g., "Tell me about yourself" → capture answer → auto-follow-up → "Describe a challenge" → probe for details) that auto-advances through a predefined question list with dynamic follow-ups. Requires a flow state machine in `session_manager.py` and a flow editor in the config UI.

## Documentation
- [ ] **User Guide**: Create comprehensive user guide with screenshots and tutorials.
- [ ] **Troubleshooting Guide**: Expand troubleshooting section with common issues and solutions.