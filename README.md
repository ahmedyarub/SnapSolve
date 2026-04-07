# Screen Capture & Gemini QA

A very fast Windows-compatible application that captures a user-defined rectangular area of the screen, sends it directly to the Gemini CLI (to bypass local OCR for extreme speed), and provides a very short answer to the question in the image.

The answer is outputted via a frameless popup notification and/or local Text-to-Speech (TTS).

## Setup & Installation

1. Install Node.js (for `npx`)
2. Install the Gemini CLI:
   ```bash
   npx @google/gemini-cli
   ```
   *Note: Run the command `gemini` at least once from the terminal to log in using your browser.*
3. Install Python 3.8+
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

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
    "model": "gemini-2.5-flash-lite"
}
```

*Note: `voice_id` allows you to pick a specific TTS voice or OS playback device configuration installed on your system. You can pass the ID here, or omit it to use the system default.*

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
