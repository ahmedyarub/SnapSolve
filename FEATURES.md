# Features Breakdown

The Screen Capture & QA application provides several customizable features organized by their role in the processing pipeline.

## Controls & Configuration

*   **Keyboard Shortcuts:** Customizable global hotkeys (e.g., `Ctrl+Alt+Shift+S`) trigger actions (like Capture, Reselect, Multi-select) without needing the app to be in focus.
*   **Control Panel:** An optional floating toolbar to visually trigger key actions and view status.
*   **Configuration UI:** A user-friendly settings dialog with tabs for modifying Application Settings, Profile Settings, and Keyboard Shortcuts without manually editing JSON files.
*   **Background Mode:** Run the application minimized to the system tray, freeing up taskbar space.
*   **Profiles:** Define and switch between distinct configurations (e.g., "Fast Image Processing", "Deep Text Analysis"). Each profile stores its specific `llm_engine`, model, `ocr_engine`, prompt, and fallback model settings.

## Source (Data Gathering)

*   **Fast Screen Capture:** Quickly grab a user-defined rectangular area of the screen.
*   **Coordinate Reselection:** Easily draw a new bounding box to update the capture area while the application is running.
*   **Multi-Select:** Capture multiple disparate areas of the screen and aggregate them into a single request.
*   **Text or Image Input:** Depending on the setup, the application can extract raw text (using OCR) or send the raw image directly to vision-capable engines.

## Prompt & Enrichment

*   **Chat Session History:** Maintains context over multiple queries. The conversation is saved locally, and the previous context is stitched into the prompt or passed via API (depending on the engine) to allow for conversational follow-ups.
*   **Custom Prompting:** Allows defining custom instructions (via `config/prompts.json`) to dictate how the LLM should format or structure its response.

## Engine (Processing)

*   **Multiple LLM Engines:**
    *   `gemini`: Uses the Google Gemini CLI.
    *   `google-genai`: Uses the official Python SDK for Google GenAI.
    *   `ollama`: Integrates with a local Ollama server, avoiding external network requests.
*   **Fallback Capability:** Configure a secondary model that runs concurrently with the main model. If the main model fails or takes too long, the application gracefully defaults to the fallback model to ensure a response is always generated.
*   **Local OCR (PaddleOCR):** For workflows requiring precise text extraction prior to LLM processing, PaddleOCR can be configured to process the screen capture entirely on your local machine.
*   **Remote OCR:** Offload OCR processing to a remote PaddleOCR service.
*   **Concurrent Execution & Warmup:** Models are pre-loaded (warmed up) during application startup.

## Sink (Output Generation)

*   **Popup Sink:** Displays responses in an unobtrusive, frameless window.
    *   Supports dynamic resizing based on text length.
    *   Renders rich Markdown, including bold, italics, lists, markdown tables, and syntax-highlighted code blocks.
*   **Audio Sink (TTS):** Uses local Text-to-Speech (`pyttsx3`) to read the answer aloud asynchronously, allowing you to hear the response without breaking your workflow.
