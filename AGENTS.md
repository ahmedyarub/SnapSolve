# AI Agent Guidelines for Screen Capture & QA

Welcome! If you are an AI assistant working on this repository, please adhere to the following architectural guidelines
and codebase specific conventions to ensure your modifications are safe and performant.

## Code Organization & Architecture

This application relies on a strictly decoupled architecture:

1.  **`core/`**: The main business logic.
    *   `sources/`: Input sources for extracting text or images.
        *   `text.py`: `TextSource` — direct text pass-through.
        *   `screenshot.py`: `ScreenshotSource` — screen capture via `PIL.ImageGrab` with OCR support.
        *   `sound.py`: `SoundSource` — audio recording with Google Speech-to-Text and WhisperLive real-time
          transcription, subtitle display, and server management.
        *   `manager.py`: Global active source singleton (`get_active_source_instance()`,
          `set_active_source_instance()`).
    *   `sources/ocr/`: OCR engine implementations.
        *   `paddleocr.py`: `LocalPaddleOCREngine` — local PaddleOCR with warmup and confidence filtering.
        *   `remote_paddle.py`: `RemotePaddleOCREngine` — remote PaddleOCR via HTTP POST.
        *   `none.py`: `NoOCREngine` — no-op OCR.
        *   `exceptions.py`: Custom exception hierarchy (`OCRError`, `OCRInitializationError`, etc.).
    *   `llm/`: LLM Engine implementations.
        *   `google_genai.py`: `GoogleGenAIEngine` — Google GenAI SDK with streaming and multi-turn history.
        *   `ollama.py`: `OllamaEngine` — Ollama REST API with base64 image encoding.
        *   `gemini_cli.py`: `GeminiCLIEngine` — wraps the `gemini` CLI tool via subprocess.
        *   `antigravity.py`: `AntigravityEngine` — HTTP+SSE client to the Antigravity SDK service.
          Streams tokens in real-time to the sink.
    *   `sinks/`: Output sinks for presenting results to the user.
        *   `popup.py`: `PopupSink` — accumulates text chunks, renders via `show_popup()` from `core/output.py`.
        *   `audio.py`: `AudioSink` — Piper TTS synthesis with Markdown stripping and configurable output device.
        *   `composite.py`: `CompositeSink` — fan-out to multiple sinks (e.g., popup + audio simultaneously).
    *   `pipeline/`: Pipeline orchestration.
        *   `pipeline.py`: `process_pipeline()` orchestrates Source → LLM → Sink. Also contains
          `ConcurrentSinkWrapper` for main + fallback model concurrency.
    *   `output.py`: **Central UI module** (928 lines) — contains `PopupWidget`, `PanelWidget`,
      `TextInputWidget`, `SubtitleWidget`, `RecordButton`, `UIManager`, and `UISignals` for thread-safe
      signal-based communication. This is the largest single file in the project.
    *   `session_manager.py`: `SessionManager` — chat session persistence, history management, transcription
      file storage.
    *   `remote_control_server.py`: WebSocket server for Android remote control — mouse control, app action dispatch,
      UI state synchronization.
2.  **`ui/`**: PyQt6 dialog and overlay components. Do not mix heavy I/O or LLM requests directly inside UI event
    handlers.
    *   `config_ui.py`: `ConfigUI(QDialog)` — full configuration dialog with tabs for settings, profiles,
      shortcuts, warmup, and remote control.
    *   `context_manager_ui.py`: `ContextManagerDialog(QDialog)` — per-session context configuration with
      category toggles (transcribed text, questions, answers), project folder selection with autocomplete
      from recent paths, and session context import.
    *   `selector.py`: `CoordinateSelector(QWidget)` — screen region selector overlay with DPI-aware coordinates.
    *   `session_browser.py`: `SessionBrowserDialog(QDialog)` — maximized session browser with tree view,
      prompt/response panels, tag management, and filtering. Reuses `popup.html` for Markdown rendering.
3.  **`config/`**: Configuration parsing and profile management.
    *   `settings.py`: Config loading/saving, profile management, argument parsing, audio device helpers.
    *   `config.json` / `config.sample.json`: Active and sample configuration files.
    *   `profiles.json`: Named profiles with engine, model, OCR, and prompt settings.
    *   `prompts.json`: System prompt definitions.
    *   `llm_models.json`: Model registry with capability flags (e.g., `supports_ocr`).
4.  **`services/`**: External services.
    *   `ocr_service.py`: FastAPI microservice for remote PaddleOCR (POST `/ocr` endpoint).
    *   `whisperlive/`: Git submodule — WhisperLive real-time transcription server.
    *   `antigravity/`: Antigravity SDK service — FastAPI app that wraps the `google-antigravity`
      Python SDK. Exposes `POST /chat` with SSE streaming and `GET /health` on port 8200.
5.  **`sessions/`**: Local storage for chat session history (JSON files), captured images, and transcriptions.
6.  **`tests/`**: Contains the tests.
    *   `e2e/`: End-to-end tests with image-recognition-based UI automation. Only run on the developer's machine.
      Don't run or modify the files inside without understanding the full test infrastructure.
    *   `sanity/`: Standalone sanity check scripts (OCR, audio, WhisperLive warmup) for component verification.
7.  **`scripts/`**: Verification scripts.
    *   `verify.ps1` / `verify.sh`: Linting (Ruff), formatting, Qodana, SonarQube, and Kotlin/Android lint.
8.  **`android_remote_control/`**: Companion Android app (Kotlin/Gradle) for remote control via WebSocket.
9.  **`docs/`**: Additional documentation (architecture, features, setup guides, roadmap).
10. **`main.py`**: Application entry point and orchestrator (1359 lines) — initializes Qt, config, engines, UI,
    hotkeys, and runs the event loop. Contains all handler functions (`handle_capture()`, `handle_text_submit()`,
    `handle_start_record()`, etc.) and global state management.

## Crucial Technical Constraints

### PyQt6 & Thread Safety

* The PyQt6 GUI runs on the **main thread** via `QApplication.exec()`. All UI widgets must be accessed from this thread.
* **Global Hotkeys:** The `keyboard` module captures hotkeys in a blocking fashion. Any callback triggered by
  `keyboard.read_hotkey()` **must not** perform long-running blocking operations or attempt to update PyQt6 UI
  elements directly.
* **UI Updates:** All updates to the UI from background threads (like LLM streaming chunks or hotkey callbacks) must be
  dispatched to the main UI thread using `UISignals` (Qt signals/slots defined in `core/output.py`) or
  `QTimer.singleShot()`.
* **Qt Event Handlers:** When implementing Qt event handlers (e.g., `mousePressEvent`, `keyPressEvent`, `paintEvent`, etc.),
  you must add `# noinspection PyPep8Naming` before the method definition. Qt requires camelCase naming for
  event handlers, which conflicts with PEP 8 naming conventions. Example:
  ```python
  # noinspection PyPep8Naming
  def mousePressEvent(self, event):
      # Event handler implementation
      pass
  ```

### Windows DPI & Coordinates

* Because the app uses `PIL.ImageGrab` alongside PyQt6 overlays, Windows DPI scaling can cause coordinate mismatches.
* Ensure that DPI awareness is enabled (e.g., `ctypes.windll.shcore.SetProcessDpiAwareness(2)`) early in the application
  lifecycle before UI initialization so physical pixels match logical coordinates.

### Concurrent LLM Execution

* The app supports running a main model and a fallback model concurrently via `ConcurrentSinkWrapper` (located in
  `core/pipeline/pipeline.py`, not in `core/sinks/`).
* When testing modifications to LLM engines or sinks, ensure that your changes handle the abrupt replacement of fallback
  text with main model text correctly.
* Engines implement a `warmup()` method. When dealing with engine instantiation, remember to call this method to
  preload models into memory.

### Audio Processing

* **Audio Recording:** The `SoundSource` (`core/sources/sound.py`, 489 lines) uses background threading for audio
  recording to avoid blocking the UI.
* **Speech Recognition:** Google Speech-to-Text is used for transcription. Ensure proper error handling for network issues
  or unrecognized speech.
* **Real-time Transcription:** WhisperLive integration in `SoundSource` manages the server process lifecycle (health
  check, startup, warmup, cleanup) and streams audio to a local WhisperLive server for real-time subtitles via
  `SubtitleWidget` in `core/output.py`.
* **Audio Devices:** The application supports configurable audio input and output devices. Always validate device names
  and handle cases where specified devices are not available.
* **TTS Integration:** Piper TTS (`AudioSink` in `core/sinks/audio.py`) runs in a separate daemon thread. It strips
  Markdown from text via `clean_text()` before synthesis. Ensure proper cleanup and resource management.

### File Handling & OCR

* On Windows, do not use `delete=True` with `tempfile.NamedTemporaryFile` if the file needs to be accessed by another
  process (like an external CLI or PaddleOCR). Use `delete=False`, close the handle immediately, and manually clean up
  the file using a robust `try...finally os.remove()` block.
* OCR extraction (`core/sources/ocr/`) should be executed only once per capture to save resources, even if multiple LLM
  engines are running.

### Output & Rendering

* The `PopupSink` delegates rendering to `PopupWidget` in `core/output.py`, which uses a PyQt6 `QWebEngineView`
  powered by `marked.js`, `KaTeX`, and `Mermaid.js`.
* This enables rich Markdown, LaTeX math, syntax-highlighted code blocks, and diagram rendering with streaming updates.
* If you need to add new rendering features, modify `core/output.py` (specifically the `PopupWidget` class and its
  HTML/JS template). Do **not** introduce additional rendering libraries without good reason.

### Antigravity Service

* The `google-antigravity` Python SDK is available on all platforms (Windows, Linux, macOS).
  The SDK is hosted behind a lightweight FastAPI service (`services/antigravity/`) for HTTP access.
* **Architecture:** The `AntigravityEngine` (`core/llm/antigravity.py`) sends HTTP POST requests to the
  service (`http://localhost:8200/chat`) and reads the response as a **Server-Sent Events (SSE)** stream.
  Each `data:` line contains a text token that is forwarded to the sink in real-time.
* **Starting the Service:** The service must be started manually before using the Antigravity engine:
  ```bash
  pip install -r services/antigravity/requirements.txt
  python services/antigravity/antigravity_service.py
  ```
* **Working Directory / Project Folder:** The `cwd` field in the chat request tells the agent which project
  directory to operate on.
* **API Key:** The service reads `GEMINI_API_KEY` from the environment. Set it before starting the service.

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
* **Code Formatting:** **CRITICAL** - Always respect the `.editorconfig` file settings for code formatting:
  - **Indentation:** Use 4 spaces for indentation (no tabs)
  - **Line Length:** Maximum line length of 120 characters
  - **Line Endings:** Use CRLF (`\r\n`) line endings on Windows
  - **Final Newlines:** Do not insert final newlines at end of files
  - **File Encoding:** Use UTF-8 encoding
  - **Python-specific:** Follow Python formatting rules (blank lines around classes/methods, etc.)
  - **JSON-specific:** Use 2 spaces for JSON files
  - **Markdown-specific:** Follow Markdown formatting rules for consistent documentation
  - **Why this matters:**
    - Ensures consistent code style across all contributors and AI agents
    - Prevents unnecessary diff noise and merge conflicts
    - Maintains code readability and maintainability
    - Follows project-specific conventions that may differ from general Python standards
    - IDEs and editors automatically apply these settings when .editorconfig is respected
* **Pydantic Models:** When working with Pydantic models (v2+), use `model_dump_json()` instead of the deprecated `json()` method
  for serializing models to JSON strings. The `json()` method was deprecated in Pydantic v2 and will be removed in future versions.
* **Configuration:** Always update the sample configuration (`config/config.sample.json`) and configuration UI (`ui/config_ui.py`) whenever
  you introduce new settings. **Every** new configuration key must have a corresponding widget in `ui/config_ui.py` so users can
  modify it without editing JSON files. Additionally, any time a new Source, LLM engine, OCR engine, or Sink is added, you must
  update `ui/config_ui.py` to allow the user to select them.
* **Profile Management:** When adding new configuration options, consider whether they should be profile-specific or
  global settings. Update `profiles.json` structure accordingly.
* **Hotkey Management:** New hotkeys should be added to the default configuration in `config/settings.py` and properly
  handled in the main application logic.
* Sanity Tests:
    *   The `tests/sanity/` folder contains standalone sanity check scripts (e.g. testing the microphone, testing the OCR without the full app).
    *   These files MUST be entirely self-contained. Do not import or reference logic modules from the main application codebase inside these scripts.
    *   NEVER run sanity tests autonomously. These are strictly for developer usage and manual testing only.
* **Documentation Tracking:**
    *   When implementing a new feature, **always** update `docs/FEATURES.md` to document it.
    *   Keep only the **10 most recent** completed tasks in the "Recently Completed Features" section of `docs/TODO.md`.
      Older completed items should be removed to keep the list concise. New completions go at the bottom of the list.

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