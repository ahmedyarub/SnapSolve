# AI Agent Guidelines for Screen Capture & QA

Welcome! If you are an AI assistant working on this repository, please adhere to the following architectural guidelines and codebase specific conventions to ensure your modifications are safe and performant.

## Code Organization & Architecture

This application relies on a strictly decoupled architecture:
1.  **`core/`**: The main business logic. Includes:
    *   `sources/`: For extracting text or images (Screen capture, OCR).
    *   `llm/`: LLM Engines (`GoogleGenAIEngine`, `OllamaEngine`, etc.).
    *   `sinks/`: Where data is sent (`PopupSink`, `AudioSink`).
    *   `pipeline/`: Orchestrates the flow from Source -> LLM -> Sink.
2.  **`ui/`**: All Tkinter-related code. Do not mix heavy I/O or LLM requests directly inside UI event handlers.
3.  **`config/`**: Configuration parsing and profile management.
4.  **`sessions/`**: Local storage for chat session history.

## Crucial Technical Constraints

### Tkinter & Thread Safety
*   The Tkinter GUI uses a persistent background thread (`mainloop()`).
*   **Global Hotkeys:** The `keyboard` module captures hotkeys in a blocking fashion. Any callback triggered by `keyboard.read_hotkey()` **must not** perform long-running blocking operations or attempt to update Tkinter UI elements directly.
*   **UI Updates:** All updates to the UI from background threads (like LLM streaming chunks or hotkey callbacks) must be dispatched to the main UI thread using `root.after(0, lambda: ...)` or handled via thread-safe `queue.Queue`.

### Windows DPI & Coordinates
*   Because the app uses `PIL.ImageGrab` alongside Tkinter overlays, Windows DPI scaling can cause coordinate mismatches.
*   Ensure that DPI awareness is enabled (e.g., `ctypes.windll.shcore.SetProcessDpiAwareness(2)`) early in the application lifecycle before UI initialization so physical pixels match logical coordinates.

### Concurrent LLM Execution
*   The app supports running a main model and a fallback model concurrently via `ConcurrentSinkWrapper`.
*   When testing modifications to LLM engines or sinks, ensure that your changes handle the abrupt replacement of fallback text with main model text correctly.
*   Engines implement a `warmup()` method. When dealing with engine instantiation, remember to call this method to pre-load models into memory.

### File Handling & OCR
*   On Windows, do not use `delete=True` with `tempfile.NamedTemporaryFile` if the file needs to be accessed by another process (like an external CLI or PaddleOCR). Use `delete=False`, close the handle immediately, and manually clean up the file using a robust `try...finally os.remove()` block.
*   OCR extraction (`core/sources/ocr/`) should be executed only once per capture to save resources, even if multiple LLM engines are running.

### Output & Rendering
*   The `PopupSink` features a custom, lightweight Markdown parser native to Tkinter's `Text` widget tags.
*   If you need to add new markdown features (e.g., blockquotes), modify the parser in `core/output.py` or the sink directly, utilizing Tkinter text tags rather than pulling in external HTML rendering libraries.

## General Practices
*   **Speed is critical:** Prioritize optimizations that reduce time-to-first-token.
*   **Logging:** Use the existing logging structures. When popping up notifications, distinguish between "log" messages (auto-closing) and "result" messages (staying open).
## Testing
* Whenever we have a new class of one of the four pipeline components (Source, LLM Engine, Sink, OCR Engine), an additional e2e test should be created in `tests/test_e2e.py`.
