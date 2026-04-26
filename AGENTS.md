# AI Agent Guidelines for Screen Capture & QA

Welcome! If you are an AI assistant working on this repository, please adhere to the following architectural guidelines
and codebase specific conventions to ensure your modifications are safe and performant.

## Code Organization & Architecture

This application relies on a strictly decoupled architecture:

1.  **`core/`**: The main business logic. Includes:
    *   `sources/`: For extracting text or images (Text, Screen capture, Audio/Sound).
    *   `llm/`: LLM Engines (`GoogleGenAIEngine`, `OllamaEngine`, `GeminiCLIEngine`).
    *   `sinks/`: Where data is sent (`PopupSink`, `AudioSink`, `CompositeSink`).
    *   `pipeline/`: Orchestrates the flow from Source -> LLM -> Sink.
2.  **`ui/`**: All Tkinter-related code. Do not mix heavy I/O or LLM requests directly inside UI event handlers.
3.  **`config/`**: Configuration parsing and profile management.
4.  `services/`: Service implementations like the remote OCR service.
5.  `sessions/`: Local storage for chat session history.
6.  `tests/`: Contains the tests.
    *   `e2e/`: Contains the end-to-end tests that should only run on the developer's machine. Don't run or modify the
      files inside without understanding the full test infrastructure.
    *   `sanity/`: Contains standalone sanity check scripts for component verification.

## Crucial Technical Constraints

### Tkinter & Thread Safety

* The Tkinter GUI uses a persistent background thread (`mainloop()`).
* **Global Hotkeys:** The `keyboard` module captures hotkeys in a blocking fashion. Any callback triggered by
  `keyboard.read_hotkey()` **must not** perform long-running blocking operations or attempt to update Tkinter UI
  elements directly.
* **UI Updates:** All updates to the UI from background threads (like LLM streaming chunks or hotkey callbacks) must be
  dispatched to the main UI thread using `root.after(0, lambda: ...)` or handled via thread-safe `queue.Queue`.

### Windows DPI & Coordinates

* Because the app uses `PIL.ImageGrab` alongside Tkinter overlays, Windows DPI scaling can cause coordinate mismatches.
* Ensure that DPI awareness is enabled (e.g., `ctypes.windll.shcore.SetProcessDpiAwareness(2)`) early in the application
  lifecycle before UI initialization so physical pixels match logical coordinates.

### Concurrent LLM Execution

* The app supports running a main model and a fallback model concurrently via `ConcurrentSinkWrapper`.
* When testing modifications to LLM engines or sinks, ensure that your changes handle the abrupt replacement of fallback
  text with main model text correctly.
* Engines implement a `warmup()` method. When dealing with engine instantiation, remember to call this method to
  pre-load models into memory.

### Audio Processing

* **Audio Recording:** The `SoundSource` uses background threading for audio recording to avoid blocking the UI.
* **Speech Recognition:** Google Speech-to-Text is used for transcription. Ensure proper error handling for network issues
  or unrecognized speech.
* **Audio Devices:** The application supports configurable audio input and output devices. Always validate device names
  and handle cases where specified devices are not available.
* **TTS Integration:** Piper TTS runs in a separate daemon thread. Ensure proper cleanup and resource management.

### File Handling & OCR

* On Windows, do not use `delete=True` with `tempfile.NamedTemporaryFile` if the file needs to be accessed by another
  process (like an external CLI or PaddleOCR). Use `delete=False`, close the handle immediately, and manually clean up
  the file using a robust `try...finally os.remove()` block.
* OCR extraction (`core/sources/ocr/`) should be executed only once per capture to save resources, even if multiple LLM
  engines are running.

### Output & Rendering

* The `PopupSink` features a custom, lightweight Markdown parser native to Tkinter's `Text` widget tags.
* If you need to add new markdown features (e.g., blockquotes), modify the parser in `core/output.py` or the sink
  directly, utilizing Tkinter text tags rather than pulling in external HTML rendering libraries.

## General Practices

* **Speed is critical:** Prioritize optimizations that reduce time-to-first-token.
* **Logging:** Use the existing logging structures. When popping up notifications, distinguish between "log" messages (
  auto-closing) and "result" messages (staying open).
* **Clean Code:** Always remove unused imports, variables, and function arguments. Optimize imports.
* **Types:** Always add type hints and annotations when practical. If using a `class | None` pattern, always assert that
  it is not `None` before use.
* **Instance Attributes:** **CRITICAL** - All instance attributes must be defined in the `__init__` method of every class.
  Never define instance attributes in other methods. This ensures:
  - All attributes are documented in one place
  - IDE autocomplete works correctly
  - Code is more maintainable and easier to understand
  - Prevents runtime errors from missing attributes
  - Follows Python best practices for class initialization
  Example:
  ```python
  class MyClass:
      def __init__(self):
          self.attribute1 = None  # Define all attributes here
          self.attribute2 = []
          self._private_attribute = None
      
      def some_method(self):
          # Use attributes, don't define new ones
          self.attribute1 = "value"
  ```
  **Why this matters:**
  - If an attribute is defined conditionally (e.g., inside a try/except block in __init__), it may not exist when accessed later, causing AttributeError
  - Defining attributes in __init__ with a default value (like None) ensures they always exist
  - This is especially important for attributes that are used in other methods or accessed externally
  - Makes the class interface clear and predictable
* **Pydantic Models:** When working with Pydantic models (v2+), use `model_dump_json()` instead of the deprecated `json()` method
  for serializing models to JSON strings. The `json()` method was deprecated in Pydantic v2 and will be removed in future versions.
* **Configuration:** Always update the sample configuration (`config/config.sample.json`) and configuration UI whenever
  you introduce new settings. **Important:** Any time a new Source, LLM engine, OCR engine, or Sink is added, you must remember to update `ui/config_ui.py` to allow the user to select them.
* **Profile Management:** When adding new configuration options, consider whether they should be profile-specific or
  global settings. Update `profiles.json` structure accordingly.
* **Hotkey Management:** New hotkeys should be added to the default configuration in `config/settings.py` and properly
  handled in the main application logic.
* Sanity Tests:
    *   The `tests/sanity/` folder contains standalone sanity check scripts (e.g. testing the microphone, testing the OCR without the full app).
    *   These files MUST be entirely self-contained. Do not import or reference logic modules from the main application codebase inside these scripts.
    *   NEVER run sanity tests autonomously. These are strictly for developer usage and manual testing only.

## Testing Guidelines

### E2E Tests
* E2E tests are designed for developer machines only and require specific setup (VB-Audio Virtual Cable, specific screen resolution).
* Tests use image recognition for UI interaction and require specific button images in `tests/e2e/images/`.
* Audio recording tests use virtual audio devices for TTS verification.
* Never modify E2E test files without understanding the full test infrastructure and requirements.

### Component Testing
* Sanity tests should be self-contained and not depend on the main application logic.
* Audio tests require proper device configuration and may need specific test files (e.g., `test_sound.wav`).
* Always test audio components with appropriate device configurations and error handling.