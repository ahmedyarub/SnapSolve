# E2E Tests

End-to-end tests for SnapSolve application that verify core functionality through automated UI interaction.

## Overview

These tests simulate real user interactions with the SnapSolve application by:
- Launching the main application and OCR service
- Automating UI interactions using PyAutoGUI
- Testing text input, image capture, and audio input workflows
- Verifying TTS (Text-to-Speech) functionality
- Validating OCR service integration
- Testing speech recognition with audio recording

## Prerequisites

### Required Software
- Python 3.8+
- VB-Audio Virtual Cable (for TTS testing)
- Display with sufficient resolution (tests use coordinates up to 3500x1900)

### Python Dependencies
Install required packages:
```bash
pip install -r requirements.txt
```

### Audio Setup
For TTS and speech recognition tests, you need VB-Audio Virtual Cable installed:
- **CABLE Output (VB-Audio Virtual)** - Used as TTS input device
- **CABLE Input (VB-Audio Virtual C)** - Used as TTS output device
- **Microphone or virtual input device** - Used for speech recognition testing

## Test Structure

### Main Test File (`tests.py`)
Contains the primary test orchestration and test cases:
- `run_tests()` - Main entry point that initializes and runs all tests
- `test_text_source()` - Tests text input and TTS functionality
- `test_image_source()` - Tests image capture and OCR integration
- `test_audio_source()` - Tests audio input with speech recognition
- `test_capture()` - Tests single image capture workflow
- `test_multi_capture()` - Tests multi-select image capture workflow

### Utility Modules

#### `config.py`
Centralized configuration constants:
- Working directory and file paths
- UI button image paths
- Test coordinates and target words
- Test questions
- Audio device names
- Subprocess configuration

#### `ui_utils.py`
UI interaction utilities:
- `cycle_until()` - Cycles through UI until target button appears
- `poll_button()` - Polls for button visibility
- `find_text()` - Finds text on screen
- `click_button()` - Clicks UI buttons
- `minimize_all_windows()` - Minimizes all windows

#### `network_utils.py`
Network utilities:
- `check_port_in_use()` - Checks if a port is in use
- `poll_port()` - Polls for service availability

#### `audio_utils.py`
Audio recording utilities:
- `get_microphone_index()` - Finds microphone by name
- `record_audio_in_background()` - Records audio in background thread

#### `process_utils.py`
Process management utilities:
- `show_test_ui()` - Launches test UI
- `init_tests()` - Initializes test environment
- `cleanup()` - Cleans up processes
- `launch_service()` - Launches OCR service
- `launch_app()` - Launches main application

## How Tests Work

### Test Execution Flow

1. **Initialization**
   - Minimizes all windows
   - Launches OCR service (if not already running)
   - Launches main application
   - Waits for app initialization

2. **Text Source Test**
   - Starts background audio recording
   - Clicks on prompt position and pastes test question
   - Submits question and waits for response
   - Verifies target word appears in response
   - Stops recording and processes audio
   - Validates TTS output contains target word

3. **Image Source Test**
   - Checks OCR service availability
   - Cycles to image capture mode
   - Runs single capture test
   - Runs multi-capture test

4. **Audio Source Test**
   - Cycles to audio input mode
   - Starts audio recording
   - Records test audio input
   - Stops recording and processes transcription
   - Verifies speech recognition results contain target word

5. **Single Capture Test**
   - Launches test UI with sample text
   - Selects reselect mode
   - Drags to capture text region
   - Captures and processes image
   - Verifies OCR results contain target word

6. **Multi-Capture Test**
   - Launches test UI with multiple text regions
   - Captures first text region
   - Captures second text region
   - Ends multi-select mode
   - Verifies combined OCR results contain target word

7. **Cleanup**
   - Stops background recording
   - Terminates application and service processes

## Running Tests

### Basic Execution
```bash
cd tests/e2e
python tests.py
```

### Emergency Exit
Press `Ctrl+Shift+Alt+Q` at any time to stop tests and clean up processes.

## Configuration

### Test Coordinates
Edit `config.py` to adjust screen coordinates:
- `PROMPT_X, PROMPT_Y` - Position for text input (default: 1900, 1900)
- `POPUP_X, POPUP_Y` - Position for response verification (default: 3500, 1800)

### Test Questions
Modify test questions in `config.py`:
- `BASIC_QUESTION` - Basic geography question
- `PROGRAMMING_QUESTION1` - First programming question
- `PROGRAMMING_QUESTION2` - Second programming question

### Target Words
Expected answers in `config.py`:
- `TARGET_WORD_BASIC` - Expected answer for basic question (default: "Brazil")
- `TARGET_WORD_PROGRAMMING` - Expected answer for programming questions (default: "class")

### Audio Devices
Configure audio devices in `config.py`:
- `TTS_INPUT_DEVICE_NAME` - Virtual cable output device for TTS
- `TTS_OUTPUT_DEVICE_NAME` - Virtual cable input device for TTS
- `AUDIO_INPUT_DEVICE_NAME` - Input device for speech recognition testing

### Application Arguments
Modify `MAIN_SCRIPT_ARGS` in `config.py` to change application startup parameters.

## Test Images

UI button images are stored in the `images/` directory:
- `button_capture.png` - Capture button
- `button_cancel.png` - Cancel button
- `button_cycle_source.png` - Source cycling button
- `button_end_multiselect.png` - End multi-select button
- `button_record.png` - Start recording button
- `button_record_stop.png` - Stop recording button
- `button_reselect.png` - Reselect coordinates button
- `button_start_multiselect.png` - Start multi-select button

## Notes

- Tests are designed for high-resolution displays (coordinates up to 3500x1900)
- Background recording uses threading for non-blocking audio capture
- All processes are properly cleaned up on test completion or interruption
- Tests use image recognition with configurable confidence thresholds
- OCR service is reused if already running to avoid conflicts
- Speech recognition tests require audio input devices and may need test audio files
- Audio recording tests use virtual audio devices for TTS verification
