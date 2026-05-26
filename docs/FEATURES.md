# Features Breakdown

The Screen Capture & QA application provides several customizable features organized by their role in the processing pipeline.

## Controls & Configuration

*   **Keyboard Shortcuts:** Customizable global hotkeys (e.g., `Ctrl+Alt+Shift+C`) trigger actions (like Capture, Reselect, Multi-select, Toggle Panel, New Session) without needing the app to be in focus.
*   **Control Panel:** An optional floating toolbar to visually trigger key actions and view status.
*   **Configuration UI:** A user-friendly settings dialog with tabs for modifying Application Settings, Profile Settings, and Keyboard Shortcuts without manually editing JSON files.
*   **Background Mode:** Run the application minimized to the system tray, freeing up taskbar space.
*   **Profiles:** Define and switch between distinct configurations (e.g., "Fast Image Processing", "Deep Text Analysis"). Each profile stores its specific `llm_engine`, model, `ocr_engine`, prompt, and fallback model settings.
*   **Audio Device Configuration:** Configure specific audio input devices for speech recognition and output devices for TTS.

## Source (Data Gathering)

*   **Multiple Input Sources:**
    *   **Text Input:** Direct text entry via the control panel for questions and queries.
    *   **Image Capture:** Fast screen capture of user-defined rectangular areas.
    *   **Audio Input:** Real-time audio recording with speech recognition using Google Speech-to-Text.
*   **Coordinate Reselection:** Easily draw a new bounding box to update the capture area while the application is running.
*   **Multi-Select:** Capture multiple disparate areas of the screen and aggregate them into a single request.
*   **Text or Image Input:** Depending on the setup, the application can extract raw text (using OCR) or send the raw image directly to vision-capable engines.
*   **Audio Recording:** Background audio recording with visual feedback and automatic transcription.

## Prompt & Enrichment

*   **Chat Session History:** Maintains context over multiple queries. The conversation is saved locally, and the previous context is stitched into the prompt or passed via API (depending on the engine) to allow for conversational follow-ups.
*   **Custom Prompting:** Allows defining custom instructions (via `config/prompts.json`) to dictate how the LLM should format or structure its response.
*   **Context Stitching:** Configurable option to include conversation context in prompts for follow-up questions.

## Engine (Processing)

*   **Multiple LLM Engines:**
    *   `gemini`: Uses the Google Gemini CLI.
    *   `google-genai`: Uses the official Python SDK for Google GenAI.
    *   `ollama`: Integrates with a local Ollama server, avoiding external network requests.
*   **Fallback Capability:** Configure a secondary model that runs concurrently with the main model. If the main model fails or takes too long, the application gracefully defaults to the fallback model to ensure a response is always generated.
*   **Local OCR (PaddleOCR):** For workflows requiring precise text extraction prior to LLM processing, PaddleOCR can be configured to process the screen capture entirely on your local machine.
*   **Remote OCR:** Offload OCR processing to a remote PaddleOCR service.
*   **Concurrent Execution & Warmup:** Models are preloaded (warmed up) during application startup for reduced latency.
*   **Speech Recognition:** Google Speech-to-Text integration for audio input processing with configurable warmup.

## Sink (Output Generation)

*   **Popup Sink:** Displays responses in an unobtrusive, frameless window.
    *   Supports dynamic resizing based on text length.
    *   Renders rich Markdown via QWebEngineView with marked.js, including bold, italics, lists, Markdown tables, syntax-highlighted code blocks, LaTeX math (KaTeX), and Mermaid diagrams.
    *   Configurable opacity for visual integration.
*   **Audio Sink (TTS):** Uses local Text-to-Speech (Piper) to read the answer aloud asynchronously, allowing you to hear the response without breaking your workflow.
    *   Support for multiple voice models (.onnx format).
    *   Configurable audio output devices.
    *   Model warmup for reduced latency.
*   **Composite Output:** Simultaneous popup and audio output with synchronized streaming.

## Performance & Reliability

*   **Engine Warmup:** Pre-loading of OCR, LLM, TTS, and speech recognition engines during startup.
*   **Concurrent Processing:** Parallel model execution for fallback scenarios and non-blocking operations.
*   **Error Handling:** Graceful degradation on component failures with user-friendly error messages.
*   **Thread Safety:** All UI updates from background threads are properly dispatched to the main thread.
*   **Resource Management:** Efficient resource utilization with proper cleanup and state management.

## Testing & Development

*   **End-to-End Testing:** Comprehensive E2E tests that verify core functionality through automated UI interaction.
*   **Sanity Tests:** Standalone test scripts for component verification (OCR, audio, etc.).
*   **Audio Testing:** Support for virtual audio devices for TTS and speech recognition testing.
*   **Automated UI Testing:** PyAutoGUI integration for automated UI interaction testing.