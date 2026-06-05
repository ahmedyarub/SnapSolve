# Screen Capture & QA

A very fast and simple application that captures user-defined input (text, images, or audio), processes it to generate
answers, and provides responses via frameless popup notifications and/or local Text-to-Speech (TTS).

## Features Overview

* **Multiple Input Sources:** Support for text input, screen capture (images), and audio input with speech recognition.
* **Fast Screen Capture:** Capture user-defined areas with minimal overhead.
* **Multiple LLM Backends:** Use Gemini (via CLI or Python SDK), Google GenAI API, or a local Ollama server.
* **Concurrent Fallback Model:** Process requests on multiple models simultaneously to ensure reliability and speed.
* **Chat History:** Maintain conversational context over multiple queries with session management.
* **Session Browser:** Browse past sessions, view prompts and formatted responses, rename sessions, and add tags for filtering.
* **Configurable Profiles:** Seamlessly switch between different models, prompts, and settings.
* **Advanced OCR:** Optional PaddleOCR integration for reliable text extraction before prompting.
* **Flexible Output Sinks:** Render rich Markdown answers in a floating popup and/or read them aloud via TTS.
* **Background Mode:** Run the app seamlessly from your system tray.
* **Multi-Capture Support:** Capture multiple screen regions in sequence for combined processing.
* **Audio Input:** Record and transcribe audio input using speech recognition. Real-time transcription is also available using WhisperLive.
* **Remote OCR Service:** Offload OCR processing to a remote server.

For a full, detailed breakdown of all features, see [FEATURES.md](docs/FEATURES.md).
For technical details regarding how data flows through the application, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).
For details regarding the real-time transcription feature, see [REALTIME_TRANSCRIPTION.md](REALTIME_TRANSCRIPTION.md).
For details on the session browser, see [SESSION_BROWSER.md](docs/SESSION_BROWSER.md).

## Setup & Installation

1. Install Python 3.10+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Option 1: Gemini CLI (Default)

To use the default Gemini CLI:

1. Install Node.js (for `npx`)
2. Install the Gemini CLI:
   ```bash
   npx @google/gemini-cli
   ```
   *Note: Run the command `gemini` at least once from the terminal to log in using your browser.*

### Option 2: Local LLM with Ollama

1. Install [Ollama](https://ollama.com/).
2. Start your local Ollama server and pull a model (e.g., `ollama run llama3`).

### Option 3: Google GenAI Python SDK

Instead of the CLI, you can use the official Python SDK directly.

1. Make sure `google-genai` is installed (it's in `requirements.txt`).
2. Add your API key to `config.json` under `gemini_api_key`.

### Option 4: Local OCR with PaddleOCR

If you want to use PaddleOCR to extract text locally before sending it to an LLM:

Setting up PaddleOCR with CUDA on Windows is straightforward, provided your NVIDIA environment is properly configured.
Because PaddleOCR separates the underlying engine (PaddlePaddle) from the OCR logic, you must install them in a specific
order.

**1. Prerequisites (The NVIDIA Stack)**
Before touching Python, ensure your host machine has the following configured:

* **CUDA Toolkit**: Install a compatible version of the NVIDIA CUDA Toolkit (11.8, 12.6, or 12.9 are standard targets).
* **cuDNN**: Download the cuDNN library that matches your CUDA version. Extract it and ensure the `bin` folder
  containing the `.dll` files is added to your Windows system PATH environment variable.
* **Visual C++ Redistributable**: Ensure the latest Microsoft Visual C++ Redistributable is installed (required for the
  C++ backend of the Python bindings).

**2. Installation Commands**
Open your terminal (PowerShell, CMD, or your IDE's terminal) and set up your Python environment.

**Step A: Install the GPU Engine**
It is highly recommended to use the official Baidu mirror to get the correctly compiled Windows CUDA wheels. The default
PyPI package can sometimes fail to link against Windows CUDA binaries properly.

```bash
python -m pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
pip install "paddlex[base]"
paddlex --install PaddleOCR PaddleClas
```

**Step B: Install the OCR Toolkit**
Once the underlying GPU engine is installed, install the PaddleOCR package itself:

```bash
pip install timm
pip install torch
pip install paddleocr
```

### Option 5: Remote OCR Service

You can offload the OCR processing to a remote server running the PaddleOCR service.
This is useful if you want to run the main application on a low-end device while leveraging a more powerful machine for
text extraction.

1. Ensure the remote machine has the necessary dependencies installed (similar to Option 4).
2. Start the FastAPI service on the remote machine:
   ```bash
   uvicorn services.ocr_service:app --host 0.0.0.0 --port 8000
   ```
3. Update your `config.json` to point to the remote service using the `ocr_config` property.

### Option 6: Local TTS with Piper

If you want to use the high-quality local Text-to-Speech (TTS) feature:

1. Install the Piper TTS Python package (already included in `requirements.txt`).
2. Download a Piper voice model (`.onnx` and `.onnx.json` files). You can browse high-quality English
   voices [here](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US). A great default is
   `en_US-lessac-medium.onnx`.
3. Update your `config.json` to enable audio output and point to your Piper model:
   ```json
   {
   "output_mode": ["popup", "audio"],
   "piper_model": "path/to/en_US-lessac-medium.onnx",
   "warmup_tts": false
   }
   ```
    * `warmup_tts`: Set to `true` to preload the Piper model on application startup, reducing the delay for the first
      spoken output.

### Option 7: Real-time Transcription with WhisperLive

If you want to use real-time transcription via WhisperLive:

For setup instructions, please refer to the [Setup & Installation section in REALTIME_TRANSCRIPTION.md](REALTIME_TRANSCRIPTION.md#setup--installation).

### Option 8: Syntax Highlighting (No Setup Required)

The application uses **Shiki** for high-quality, VS Code-like syntax highlighting in its Markdown popups.
The Shiki engine and 32 common languages are pre-bundled into a local file (`core/web_assets/shiki.bundle.js`), meaning **no Node.js installation or setup is required to run the app**.
If you wish to add new languages, change the theme, or rebuild the bundle, see [docs/syntax-highlighting.md](docs/syntax-highlighting.md).

## Supported Engines

**LLM Engines (`llm_engine`):**

* `gemini` - Uses the Google Gemini CLI. Sends multimodal (image + text) directly or text-only if OCR is used.
* `ollama` - Uses a local Ollama server. Can process both images and text-only depending on the model.
* `google-genai` - Uses the official Python SDK for Google GenAI. Requires an API key. Supports both image and text
  inputs.
* `antigravity` - Uses the Google Antigravity SDK via a local FastAPI service. See [services/antigravity/README.md](services/antigravity/README.md).

**Input Sources (`default_source`):**

* `text` - Direct text input via the control panel.
* `image` - Screen capture using coordinate selection.
* `audio` - Audio recording with speech recognition.

**OCR Engines (`ocr_engine`):**

* `none` - Does not perform local OCR. The full image is sent directly to the LLM.
* `paddleocr` - Uses local PaddleOCR to extract text from the image, sending only the extracted text to the LLM.
* `remote_paddle` - Offloads OCR to a remote PaddleOCR service.

## Configuration

You can configure the application in two ways: command-line arguments or via a `config.json` file.

### Option 1: Using `config.json`

Create a file named `config.json` in the same directory as the script. Example:

```json
{
  "output_mode": [
    "popup",
    "audio"
  ],
  "hotkeys": [
    {
      "action": "capture",
      "key": "ctrl+alt+shift+c"
    },
    {
      "action": "reselect",
      "key": "ctrl+alt+shift+s"
    },
    {
      "action": "multi_capture",
      "key": "ctrl+alt+shift+m"
    },
    {
      "action": "end_multi_capture",
      "key": "ctrl+alt+shift+n"
    },
    {
      "action": "toggle_panel",
      "key": "ctrl+alt+shift+p"
    },
    {
      "action": "new_chat_session",
      "key": "ctrl+alt+shift+h"
    },
    {
      "action": "toggle_chat_sessions",
      "key": "ctrl+alt+shift+i"
    }
  ],
  "coordinates": null,
  "background": false,
  "piper_model": "en_US-lessac-medium.onnx",
  "active_profile_id": "programming",
  "ollama_url": "http://localhost:11434",
  "gemini_api_key": "",
  "auto_close_results": false,
  "popup_opacity": 0.9,
  "show_control_panel": false,
  "default_source": "text",
  "warmup_ocr": false,
  "warmup_llm": false,
  "warmup_tts": false,
  "warmup_speech_recognition": true,
  "tts_output_device_name": null,
  "audio_input_device_name": null,
  "ocr_config": {
    "remote_ocr_host": "127.0.0.1",
    "port": 8000
  }
}
```

* `output_mode`: Controls where the response is sent. Add `"audio"` to enable Piper TTS.
* `piper_model`: Path to the downloaded Piper `.onnx` voice model.
* `warmup_tts`: Set to `true` to preload the Piper model on application startup.
* `warmup_ocr`: Set to `true` to preload the OCR engine on application startup.
* `warmup_llm`: Set to `true` to preload the LLM engine on application startup.
* `warmup_speech_recognition`: Set to `true` to preload the speech recognition engine on application startup.
* `default_source`: Default input source (`"text"`, `"image"`, or `"audio"`).
* `tts_output_device_name`: Name of the audio device for TTS output (optional).
* `audio_input_device_name`: Name of the audio device for audio input/speech recognition (optional).
* `show_control_panel`: Set to `true` to show the control panel on startup.
* `active_profile_id`: ID of the profile to use from `profiles.json`.
* `ocr_config`: Configuration for remote OCR service (host and port).
* Profile-specific settings are managed in `profiles.json`, including `llm_engine`, `model`, `ocr_engine`, `prompt_id`,
  and `enable_chat_sessions`.

### Example Combinations

**Gemini Vision (Default)**
Sends the image directly to the Gemini API.

```json
{
  "active_profile_id": "default"
}
```

With corresponding profile in `profiles.json`:

```json
{
  "id": "default",
  "name": "Default Profile",
  "llm_engine": "gemini",
  "model": "gemini-2.5-flash-lite",
  "ocr_engine": "none",
  "prompt_id": "default",
  "enable_chat_sessions": true
}
```

**PaddleOCR + Ollama**
Extracts text locally, then asks a local LLM to answer the question.

```json
{
  "active_profile_id": "local-ocr"
}
```

With corresponding profile in `profiles.json`:

```json
{
  "id": "local-ocr",
  "name": "Local OCR with Ollama",
  "llm_engine": "ollama",
  "model": "llama3",
  "ocr_engine": "paddleocr",
  "prompt_id": "default",
  "enable_chat_sessions": true
}
```

**Audio Input with Speech Recognition**
Use audio input with speech recognition.

```json
{
  "default_source": "audio",
  "audio_input_device_name": "Microphone (Realtek Audio)"
}
```

### Option 2: Command Line Arguments

You can pass arguments directly when running the application. These will override the `config.json` settings:

```bash
python main.py --output-mode both --hotkey-capture "ctrl+shift+x" --hotkey-reselect "ctrl+shift+r" --piper-model "path/to/your/model.onnx" --warmup-tts --default-source audio --audio-input-device-name "Microphone (Realtek Audio)"
```

**Available Command Line Arguments:**

* `--output-mode`: Output mode (`popup`, `audio`, `both`)
* `--hotkey-capture`: Keyboard shortcut for capture
* `--hotkey-reselect`: Keyboard shortcut for reselect coordinates
* `--coords`: Capture coordinates (X1 Y1 X2 Y2)
* `--background`: Run in background (system tray)
* `--foreground`: Force run in foreground
* `--piper-model`: Path to Piper .onnx model
* `--active-profile`: Active profile ID
* `--ollama-url`: Ollama API URL
* `--gemini-api-key`: Gemini API Key
* `--auto-close-results`: Auto close result popups
* `--no-auto-close-results`: Do not auto close result popups
* `--popup-opacity`: Opacity of the popup (0.0 to 1.0)
* `--fallback-language`: Fallback language for code blocks
* `--show-control-panel`: Show the control panel overlay
* `--hide-control-panel`: Hide the control panel overlay
* `--continue-last`: Continue the last chat session
* `--continue-session`: Continue a specific chat session by ID
* `--default-source`: Default source (`text`, `image`, `audio`)
* `--disable-warmup-ocr`: Disable OCR engine warmup
* `--disable-warmup-llm`: Disable LLM engine warmup
* `--disable-warmup-tts`: Disable TTS engine warmup
* `--disable-warmup-speech-recognition`: Disable Speech Recognition warmup
* `--tts-output-device-name`: Name of the audio device for TTS output
* `--audio-input-device-name`: Name of the audio device for audio input

## Usage

1. Run the application:
   ```bash
   python main.py
   ```
2. **First Run (Coordinate Selection):** If you haven't set `coordinates` in your configuration, and you're using image
   capture, the screen will turn slightly gray. Click and drag your mouse to draw a rectangle over the area where your
   questions will appear. The application will save these coordinates to `config.json` automatically.
3. Once running, you can:
    - **Text Input:** Type your question directly in the control panel and press Enter or click Submit.
    - **Image Capture:** Press the capture hotkey (default: `Ctrl + Alt + Shift + C`) to capture the configured screen
      region.
    - **Audio Input:** Switch to audio source and press the capture hotkey to start/stop recording.
    - **Multi-Capture:** Press the multi-capture hotkey (default: `Ctrl + Alt + Shift + M`) to capture multiple regions
      in sequence.
4. If you need to **reselect coordinates** while the app is running, press the reselect hotkey (default:
   `Ctrl + Alt + Shift + S`).
5. Use the **control panel** to switch between input sources, change profiles, and manage sessions.
6. Use the **Context Manager** to configure per-session context: toggle which categories (transcriptions, questions,
   answers) are included in the prompt, set a project folder for agentic coding, or import context from previous sessions.

## Hotkeys

Default hotkeys (configurable in `config.json`):

* `Ctrl + Alt + Shift + C` - Capture (text/image/audio depending on active source)
* `Ctrl + Alt + Shift + S` - Reselect coordinates
* `Ctrl + Alt + Shift + M` - Start multi-capture mode
* `Ctrl + Alt + Shift + N` - End multi-capture mode
* `Ctrl + Alt + Shift + T` - Cancel multi-capture mode
* `Ctrl + Alt + Shift + P` - Toggle control panel
* `Ctrl + Alt + Shift + H` - New chat session
* `Ctrl + Alt + Shift + I` - Toggle context chat_sessions
* `Ctrl + Alt + Shift + V` - Toggle all widget visibility
* `Ctrl + Alt + U` - Open URL input
* `Ctrl + Alt + Shift + B` - Open session browser

## Background Mode

You can run the application minimized to your system tray by adding the `--background` flag or setting
`"background": true` in `config.json`. To exit, right-click the system tray icon and select "Exit".

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).