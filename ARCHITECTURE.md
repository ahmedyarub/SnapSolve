# Architecture Overview

This project is structured around a flexible, decoupled pipeline that flows from data extraction to text generation and finally to user presentation.

The primary pipeline follows this sequence: **Source -> Enrich Prompt -> LLM Engine -> Response Sink**.

## 1. Source (`core/sources/`)
The Source is responsible for capturing the initial raw data.
*   The primary source is screen capture (`PIL.ImageGrab`).
*   **OCR Integration (`core/sources/ocr/`):** If a local OCR engine (like PaddleOCR) is configured, the pipeline attempts to extract text via the source's `get_text()` method.
*   If OCR is disabled or fails, the pipeline falls back to capturing the raw image (`get_image()`), provided the downstream LLM engine supports multimodal inputs.
*   Image OCR extraction is optimized to run only once, regardless of how many LLM models are running concurrently.

## 2. Enrich Prompt
Before sending data to the LLM, the application enriches the prompt:
*   **System Prompts:** Specific instructions dictating the structure and tone of the response are appended (configured via `config/prompts.json`).
*   **Chat Session History:** Context from previous queries is retrieved (via `core.session_manager.SessionManager`) and injected. Depending on the engine, this is either stitched directly into the user prompt string (e.g., Ollama) or passed as structured context objects (e.g., Google GenAI API).

## 3. LLM Engine (`core/llm/`)
The Engine layer handles communication with the AI models.
*   **Supported Engines:** `GoogleGenAIEngine`, `GeminiCLIEngine`, and `OllamaEngine`.
*   **Concurrency (`ConcurrentSinkWrapper`):** The architecture supports running a primary model and a fallback model concurrently using threading.
    *   Both models are warmed up upon application startup.
    *   If the fallback model begins generating first, its output is streamed to the user.
    *   If and when the main model responds, the fallback's output is abruptly replaced by the primary model's superior response.
*   **Streaming:** Engines process responses in chunks, yielding them to the Sink layer line-by-line to enable real-time UI updates.

## 4. Response Sink (`core/sinks/`)
The Sink layer is responsible for taking the generated text and presenting it to the user.
*   **Popup Sink:** Streams the text directly into a Tkinter Text widget (`ui/`). It implements a lightweight Markdown parser to natively render bold text, bullet points, markdown tables, and syntax-highlighted code blocks dynamically as chunks arrive.
*   **Audio Sink:** A separate daemon thread runs `pyttsx3` to read the completed response aloud without blocking the UI.

## Directory Structure
*   `core/`: Contains the main logic, including the pipeline orchestrator, sources, llm engines, and sinks.
*   `ui/`: Contains the Tkinter GUI logic, control panels, configuration UI, popup notifications, and coordinate selection overlays.
*   `config/`: Manages configuration files (`config.json`, `profiles.json`, `prompts.json`), dynamic profile switching, and prompt definitions.
*   `sessions/`: Stores serialized JSON files representing the chat history of previous sessions.

## Threading & UI State
*   **Tkinter Mainloop:** The UI runs in a persistent background thread (`mainloop()`).
*   **Thread Safety:** Because global hotkeys (via the `keyboard` module) run in their own threads, all UI updates triggered by hotkeys or incoming LLM streams are dispatched safely back to the main UI thread using `root.after()` or thread-safe `queue.Queue` communication.