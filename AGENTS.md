# AI Agent Guidelines for Screen Capture & QA

Welcome! If you are an AI assistant working on this repository, please adhere to the following architectural guidelines
and codebase specific conventions to ensure your modifications are safe and performant.

## Code Organization & Architecture

Layers, top to bottom. A layer may import from the layers below it, never above:
`app/` → `ui/` → `core/` → `config/`. (`core/` must not import `app/` or `ui/`; the app
registers callbacks in `core.ui.signals.app_callbacks` where core needs to reach up.)

1.  **`app/`**: The running application.
    *   `startup.py`: `main()` — Qt init, config, UI, API server, hotkeys, tray. The profile's
        engines load in the background; requests before `ctx.ready` get "Still starting up".
    *   `context.py`: `AppContext` — the one object handlers get: config, the **current** profile
        and prompt, engines, session manager, cancel event, multi-capture state.
        `try_start_processing()` / `finish_processing()` make sure only one request runs.
    *   `feedback.py`: `run_request(ctx, work, label)` (the standard way to run a request on a
        worker thread) and `show_status()` popups.
    *   `handlers/`: `handle_*(ctx, ...)` for capture, multi-capture, text, audio, source cycling,
        sessions, cancel, periodic screenshots, navigation.
    *   `profiles.py`: picking the active profile and `switch_profile()` at runtime (validated,
        engines rebuilt, saved). `engine_init.py` builds engines; `config_validation.py` has
        `profile_problems()`.
    *   `hotkeys.py`, `tray.py`, `lifecycle.py` (`exit_app()`: ordered shutdown, then `os._exit`).
2.  **`core/`**: Business logic.
    *   `sources/`: `TextSource`, `ScreenshotSource`, `SoundSource` (+ `whisperlive_manager.py`,
        which tracks the WhisperLive processes it starts and stops them on exit); `sources/ocr/`
        has the PaddleOCR engines.
    *   `llm/`: engines (`claude_code`, `google_genai`, `ollama`, `gemini_cli`, `antigravity`,
        `litellm`) on `LLMEngine` (`base.py`). Callers use `LLMEngine.generate()`, which raises
        `LLMError` (`errors.py`, with `retryable`); engines may still report errors as
        `"Error..."` strings, which `generate()` converts. `history_turns()` /
        `history_messages()` give the capped chat history (`history_max_turns`,
        `history_max_chars`); Google GenAI and LiteLLM send it as real multi-turn messages.
        `embeddings.py` raises `EmbeddingError` instead of returning zero vectors.
    *   `pipeline/`: `process_pipeline()` builds Source → prompt → LLM (with retry and an optional
        concurrent fallback) → sink → session save. The fallback gets a `LinkedCancel` that is set
        as soon as the main model has answered.
    *   `sinks/`: `PopupSink`, `AudioSink` (Piper TTS), `CompositeSink`.
    *   `sessions/`: `store.py` (paths, legacy migration, `update_session()` — every write is a
        locked read-modify-write, so concurrent writers never lose changes), `timeline.py`,
        `index.py` (background embedding index, merged re-index requests, cached reads),
        `export.py` (Markdown / JSON). `session_manager.py`: `SessionManager` for the *current*
        session on top of these.
    *   `ui/`: overlay widgets (`PopupWidget`, `PanelWidget`, `TextInputWidget`, `SubtitleWidget`,
        `selector.py`, `pairing_dialog.py`), `UIManager`, and `signals.py` (`ui_signals`,
        `app_callbacks`). `core/output.py` is a facade that re-exports `core.ui`.
    *   `api_server.py` (FastAPI: REST + `/ws` for the Android app), `remote_auth.py` (API key
        checks, secret redaction, pairing URI), `remote_control_server.py` (mouse/keyboard/action
        handlers; actions go through `app_callbacks`).
    *   `correction_engine.py`, `languagetool.py`: real-time corrections (LLM or LanguageTool).
    *   `languages.py`: transcription languages shared by the panel, config UI and Android app.
3.  **`ui/`**: PyQt6 dialogs above core: `config_ui.py` (settings, also opened from the panel's
    ⚙ Settings and the tray), `session_browser.py` (browse, search, tag, export),
    `context_manager_ui.py`, `timeline_widget.py`. Never do heavy I/O or LLM/embedding work on
    the GUI thread; use a worker thread and a signal back (see `config_ui.reindex_all_sessions`).
4.  **`config/`**: `settings.py` — `get_config()` returns an `AppConfig`: defaults
    (`_get_default_config()`, the single source of defaults) < `config.json` < command line.
    `save_config()` never writes unchanged command-line overrides; `update_config_file()` sets
    single keys. Values whose type differs from the default's are dropped with a warning.
    `profiles.json`, `prompts.json`, `llm_models.json` (`supports_ocr` = the model reads images).
5.  **`services/`**: `ocr_service.py` (remote PaddleOCR), `diarization/`, `antigravity/`
    (`127.0.0.1:8200`, `ANTIGRAVITY_HOST` / `ANTIGRAVITY_PORT` override), `mcp_server/`
    (reads sessions through `core.sessions.store`), `whisperlive/` (git submodule; ignore it).
6.  **`sessions/`**: Session data (`sessions/<id>/session.json`, images, screenshots,
    transcription, `embeddings.json`).
7.  **`tests/`**: Unit tests (`tests/test_*.py`, run by `pytest` and CI). `e2e/` and `sanity/` are
    manual developer scripts: never run them autonomously.
8.  **`scripts/`**:
    *   `verify.ps1` / `verify.sh`: Ruff lint + format (`ruff.toml`), pytest (`pytest.ini`), Qodana
        (`qodana.yaml`, interpreter built by `qodana_bootstrap.sh`), and SonarQube
        (`sonar-project.properties`, server started by `sonarqube_up.sh`, token from
        `SONAR_TOKEN`). The Android app is not linted by these scripts.
    *   Qodana runs through `scripts/qodana_scan.sh`, which scans a copy of our sources (without the
        WhisperLive submodule) in WSL's `~/.cache/snapsolve-qodana/src`. When Qodana indexes the
        submodule, its `python_requires=">=3.9"` makes it report valid code such as `str | None` as
        "Invalid type annotation" by the hundred, and that sticks in its cache: if it ever happens,
        delete everything in `~/.cache/snapsolve-qodana/cache` except `snapsolve-venv` and `pip`.
        Qodana 2026.2 needs `qodana.cloud` reachable at startup.
    *   WSL stops the distro a few seconds after the last `wsl.exe` process exits, and Docker
        containers inside (Qodana, SonarQube) stop with it. `verify.ps1` holds it open for the run;
        do the same when using SonarQube from Windows by hand (`wsl -e sleep 3600` in another window).
    *   `check_gpu.py` (GPU stack), `lock_requirements.py` (writes `requirements.lock` from the
        verified environment), `ci_requirements.py` (the lock without the GPU stack, for CI).
9.  **`android_remote_control/`**: Kotlin app. Pairs by scanning the desktop's QR code
    (`snapsolve://pair?host=&port=&key=`), sends the key as `Authorization` on HTTP and on `/ws`.
    Build with JDK 17+ (e.g. `JAVA_HOME=~/.jdks/corretto-21.*`): `gradlew assembleDebug`.
10. **`main.py`**: calls `app.startup.main()`.
11. **`.github/workflows/ci.yml`**: Ruff and the unit tests on Windows, without the GPU stack.

## Crucial Technical Constraints

### PyQt6 & Thread Safety

* The PyQt6 GUI runs on the **main thread** via `QApplication.exec()`. All UI widgets must be accessed from this thread.
* **Global Hotkeys:** The `keyboard` module captures hotkeys in a blocking fashion. Any callback triggered by
  `keyboard.read_hotkey()` **must not** perform long-running blocking operations or attempt to update PyQt6 UI
  elements directly.
* **UI Updates:** All updates to the UI from background threads (like LLM streaming chunks or hotkey callbacks) must be
  dispatched to the main UI thread using `ui_signals` (Qt signals/slots in `core/ui/signals.py`) or
  `QTimer.singleShot()`.
* **Requests:** start every user request with `run_request(ctx, work, label)` (`app/feedback.py`). It refuses a
  second request while one runs (atomically) and ends the busy state when `work` returns or raises. Never check
  `ctx.is_processing` and then claim it separately.
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
  `core/pipeline/pipeline.py`, not in `core/sinks/`). The fallback may use another provider
  (`fallback_llm_engine` in the profile) and is cancelled once the main model has answered.
* Failures are `LLMError`s; retries happen only when `retryable` is true. Don't add new `"Error..."` return
  strings to engines; raise `LLMError` instead.
* When testing modifications to LLM engines or sinks, ensure that your changes handle the abrupt replacement of fallback
  text with main model text correctly.
* Engines implement a `warmup()` method. When dealing with engine instantiation, remember to call this method to
  preload models into memory.

### Audio Processing

* **Audio Recording:** The `SoundSource` (`core/sources/sound.py`) uses background threading for audio
  recording to avoid blocking the UI.
* **Speech Recognition:** Google Speech-to-Text is used for transcription. Ensure proper error handling for network issues
  or unrecognized speech.
* **Real-time Transcription:** WhisperLive integration in `SoundSource` manages the server process lifecycle (health
  check, startup, warmup, cleanup) and streams audio to a local WhisperLive server for real-time subtitles via
  `SubtitleWidget` in `core/ui/subtitle_widget.py`.
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

* The `PopupSink` delegates rendering to `PopupWidget` in `core/ui/popup_widget.py`, which uses a PyQt6 `QWebEngineView`
  powered by `marked.js`, `KaTeX`, and `Mermaid.js`.
* This enables rich Markdown, LaTeX math, syntax-highlighted code blocks, and diagram rendering with streaming updates.
* If you need to add new rendering features, modify `core/ui/popup_widget.py` and its HTML/JS template
  (`core/web_assets/popup.html`). Do **not** introduce additional rendering libraries without good reason.

### Remote Control API

* The API server (`core/api_server.py`) can move the mouse and type, so it never runs without a key: startup
  generates `api_server_key` when it is empty. Every HTTP route uses `Depends(verify_api_key)` and `/ws` checks the
  key (header or `?key=`) before accepting. Add the dependency to any new route.
* `api_server_host` defaults to `127.0.0.1`; `0.0.0.0` is needed for the phone. `/config` masks every key whose
  name ends in `key`, `token`, `secret` or `password` (`core.remote_auth.redact_secrets`).
* Route handlers that block (pyautogui, keyboard, disk, embeddings) are plain `def` so FastAPI runs them in its
  thread pool; the WebSocket runs its handlers with `asyncio.to_thread`.

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
* **Logging:** Use `logging.getLogger(__name__)`; `print()` is rejected by Ruff (`T20`) outside scripts, tests and
  services. Never log prompts, answers, OCR text or transcripts; log sizes or counts instead. When popping up notifications, distinguish between "log" messages (
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
  - **Line Length:** 88 characters for Python (`ruff.toml`, enforced by `ruff format`)
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
* **Hotkey Management:** New hotkeys go in the default configuration in `config/settings.py` and in `_actions()` in
  `app/hotkeys.py` (a test checks that every configured action has a handler).
* Sanity Tests:
    *   The `tests/sanity/` folder contains standalone sanity check scripts (e.g. testing the microphone, testing the OCR without the full app).
    *   These files MUST be entirely self-contained. Do not import or reference logic modules from the main application codebase inside these scripts.
    *   NEVER run sanity tests autonomously. These are strictly for developer usage and manual testing only.
* **Documentation Tracking:**
    *   When implementing a new feature, **always** update `docs/FEATURES.md` to document it.
    *   Keep only the **10 most recent** completed tasks in the "Recently Completed Features" section of `docs/TODO.md`.
      Older completed items should be removed to keep the list concise. New completions go at the bottom of the list.
* **Security & Feature Limitations:**
    *   **NEVER** suggest or implement an "Accessibility Tree Capture" feature (like the one found in Screenpipe). This is strictly prohibited for security reasons.

## Testing Guidelines

### E2E Tests
* E2E tests are designed for developer machines only and require specific setup (VB-Audio Virtual Cable, specific screen resolution).
* Tests use image recognition for UI interaction and require specific button images in `tests/e2e/images/`.
* Audio recording tests use virtual audio devices for TTS verification.
* Never modify E2E test files without understanding the full test infrastructure and requirements.

### Unit Tests

* `tests/test_*.py` run with `pytest` (configured in `pytest.ini`) locally, in `scripts/verify.ps1`, and in CI.
  Add a test with every behaviour change; keep them free of real hardware, network and GPU.

### Component Testing
* Sanity tests should be self-contained and not depend on the main application logic.
* Audio tests require proper device configuration and may need specific test files (e.g., `test_sound.wav`).
* Always test audio components with appropriate device configurations and error handling.

## NVIDIA GPU stack

The target machine is an RTX 3060 (sm_86). PaddleOCR (`paddlepaddle-gpu`, CUDA 12.9) runs in the main process;
WhisperLive and the diarization service run faster-whisper on CUDA in their own `.venv`s.

* Pin changes to CUDA-sensitive packages in `constraints-gpu.txt`, and run `python scripts/check_gpu.py` after any
  install or upgrade. It must exit 0.
* Import order matters on Windows (measured 2026-11-12):
  * Without Qt loaded, importing `paddle` first makes a later `import torch` or `import ctranslate2` fail with
    `OSError: [WinError 127]`.
  * With PyQt6 WebEngine loaded, `import torch` **before** `paddleocr` segfaults the process.
  * The working order is the app's: `PyQt6.QtWebEngineWidgets` first (see `app/startup.py`), then PaddleOCR, then torch
    (lazily, for local embeddings). Keep the early `import PyQt6.QtWebEngineWidgets  # noqa: F401` lines; do not
    preload torch.
* `pytest-qt` breaks `QtWebEngineCore` loading, so `pytest.ini` disables it.
