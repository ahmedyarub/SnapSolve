# Screen Capture & QA

A very fast and simple application that captures a user-defined rectangular area of the screen, processes it to extract text and generate answers, and provides a very short answer to the question in the image.

The answer is outputted via a frameless popup notification and/or local Text-to-Speech (TTS).

## Features Overview
*   **Fast Screen Capture:** Capture user-defined areas with minimal overhead.
*   **Multiple LLM Backends:** Use Gemini (via CLI or API), or a local Ollama server.
*   **Concurrent Fallback Model:** Process requests on multiple models simultaneously to ensure reliability and speed.
*   **Chat History:** Maintain conversational context over multiple queries.
*   **Configurable Profiles:** Seamlessly switch between different models, prompts, and settings.
*   **Advanced OCR:** Optional PaddleOCR integration for reliable text extraction before prompting.
*   **Flexible Output Sinks:** Render rich markdown answers in a floating popup and/or read them aloud via TTS.
*   **Background Mode:** Run the app seamlessly from your system tray.

For a full, detailed breakdown of all features, see [FEATURES.md](FEATURES.md).
For technical details regarding how data flows through the application, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Setup & Installation

1. Install Python 3.8+
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
2. Add your API key to `config.json` under `google_genai_api_key`.

### Option 4: Local OCR with PaddleOCR
If you want to use PaddleOCR to extract text locally before sending it to an LLM:

Setting up PaddleOCR with CUDA on Windows is straightforward, provided your NVIDIA environment is properly configured. Because PaddleOCR separates the underlying engine (PaddlePaddle) from the OCR logic, you must install them in a specific order.

**1. Prerequisites (The NVIDIA Stack)**
Before touching Python, ensure your host machine has the following configured:
*   **CUDA Toolkit**: Install a compatible version of the NVIDIA CUDA Toolkit (11.8, 12.6, or 12.9 are standard targets).
*   **cuDNN**: Download the cuDNN library that matches your CUDA version. Extract it and ensure the `bin` folder containing the `.dll` files is added to your Windows system PATH environment variable.
*   **Visual C++ Redistributable**: Ensure the latest Microsoft Visual C++ Redistributable is installed (required for the C++ backend of the Python bindings).

**2. Installation Commands**
Open your terminal (PowerShell, CMD, or your IDE's terminal) and set up your Python environment.

**Step A: Install the GPU Engine**
It is highly recommended to use the official Baidu mirror to get the correctly compiled Windows CUDA wheels. The default PyPI package can sometimes fail to link against Windows CUDA binaries properly.
```bash
python -m pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
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

## Supported Engines

**LLM Engines (`llm_engine`):**
*   `gemini` - Uses the Google Gemini CLI. Sends multimodal (image + text) directly or text-only if OCR is used.
*   `ollama` - Uses a local Ollama server. Can process both images and text-only depending on the model.
*   `google-genai` - Uses the official Python SDK for Google GenAI. Requires an API key. Supports both image and text inputs.

**OCR Engines (`ocr_engine`):**
*   `none` - Does not perform local OCR. The full image is sent directly to the LLM.
*   `paddleocr` - Uses local PaddleOCR to extract text from the image, sending only the extracted text to the LLM.

## Configuration

You can configure the application in two ways: command-line arguments or via a `config.json` file.

### Option 1: Using `config.json`

Create a file named `config.json` in the same directory as the script. Example:

```json
{
    "output_mode": ["popup", "audio"],
    "hotkeys": [
        {
            "action": "capture",
            "key": "ctrl+alt+shift+s"
        },
        {
            "action": "reselect",
            "key": "ctrl+alt+shift+r"
        }
    ],
    "background": false,
    "voice_id": null,
    "model": "gemini-2.5-flash-lite",
    "llm_engine": "gemini",
    "ocr_engine": "none",
    "ollama_url": "http://localhost:11434",
    "google_genai_api_key": ""
}
```

*   `voice_id`: Allows you to pick a specific TTS voice or OS playback device configuration installed on your system. You can pass the ID here, or omit it to use the system default.
*   `llm_engine`: Can be `"gemini"`, `"ollama"`, or `"google-genai"`.
*   `ocr_engine`: Can be `"none"` (to send image directly to the LLM) or `"paddleocr"` (to extract text locally before sending to the LLM).
*   `ollama_url`: The URL to your Ollama API.
*   `google_genai_api_key`: Your API key for the Google GenAI SDK (only needed if `llm_engine` is `"google-genai"`).

### Example Combinations
**Gemini Vision (Default)**
Sends the image directly to the Gemini API.
```json
"model": "gemini-2.5-flash-lite",
"llm_engine": "gemini",
"ocr_engine": "none"
```

**PaddleOCR + Ollama**
Extracts text locally, then asks a local LLM to answer the question.
```json
"model": "llama3",
"llm_engine": "ollama",
"ocr_engine": "paddleocr",
"ollama_url": "http://localhost:11434"
```

### Option 2: Command Line Arguments

You can pass arguments directly when running the application. These will override the `config.json` settings:

```bash
python main.py --model gemini-2.5-flash --output-mode both --hotkey-capture "ctrl+shift+x" --hotkey-reselect "ctrl+shift+r" --voice-id "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\TTS_MS_EN-US_DAVID_11.0"
```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```
2. **First Run (Coordinate Selection):** If you haven't set `coordinates` in your configuration, the screen will turn slightly gray. Click and drag your mouse to draw a rectangle over the area where your questions will appear. The application will save these coordinates to `config.json` automatically.
3. Once running, press the capture hotkey (default: `Ctrl + Alt + Shift + S`). The application will capture the region, send it to Gemini, and output the short answer using your chosen methods.
4. If you need to **reselect coordinates** while the app is running, press the reselect hotkey (default: `Ctrl + Alt + Shift + R`).

## Background Mode

You can run the application minimized to your system tray by adding the `--background` flag or setting `"background": true` in `config.json`. To exit, right-click the system tray icon and select "Exit".

## Testing
To run the end-to-end GUI tests locally, you need the test dependencies and a Google GenAI API key. Note that because `pytest-qt` is required to interact with the UI components, it must be installed.

```bash
# 1. Install test requirements
pip install -r requirements-test.txt

# 2. Set your Google GenAI API key for the LLM requests
export GOOGLE_GENAI_API_KEY="your-api-key"

# 3. Run the GUI E2E tests
pytest tests/test_e2e_gui.py
```
*Note for AI Agents:* Whenever we have a new class of one of the four pipeline components, an additional e2e test should be created. Since the application relies on Qt overlays and visual capture, use `pytest-qt` and realistic event simulation where possible.
