# Real-Time Transcription Feature

## Overview

The real-time transcription feature provides live subtitle display during audio recording. When you record audio, the system automatically detects pauses in speech and transcribes the audio segments, displaying them as subtitles that fade over time.

## Features

- **Automatic Pause Detection**: Detects pauses in speech (configurable threshold, default 1 second)
- **Live Subtitle Display**: Shows transcriptions as subtitles at the bottom of the screen
- **Fading Effects**: Older subtitles gradually fade as new ones appear
- **Automatic Cleanup**: Removes old subtitles automatically to prevent screen clutter
- **Configurable**: Can be enabled/disabled via configuration or command-line arguments

## Configuration

### Configuration File

Add these settings to your `config/config.json`:

```json
{
  "realtime_transcription": true,
  "transcription_pause_threshold": 1.0
}
```

- `realtime_transcription`: Enable/disable real-time transcription (default: `true`)
- `transcription_pause_threshold`: Pause detection threshold in seconds (default: `1.0`)

### Command-Line Arguments

```bash
# Disable real-time transcription
python main.py --disable-realtime-transcription

# Set custom pause threshold (e.g., 1.5 seconds)
python main.py --transcription-pause-threshold 1.5

# Combine with other options
python main.py --default-source audio --disable-realtime-transcription
```

## Usage

1. **Start the application** with audio as the default source:
   ```bash
   python main.py --default-source audio
   ```

2. **Start recording** by clicking the "🎙️ Record" button or using the configured hotkey

3. **Speak naturally** - the system will detect pauses and transcribe segments automatically

4. **View subtitles** - transcriptions appear at the bottom center of the screen with fading effects

5. **Stop recording** - subtitles are automatically cleared when recording stops

## How It Works

### Pause Detection

The system continuously monitors audio input and detects pauses based on the configured threshold:

- When audio is detected, it's buffered for transcription
- When a pause is detected (no audio for `transcription_pause_threshold` seconds), the buffered audio is transcribed
- The transcription is displayed as a subtitle
- The process repeats for each speech segment

### Subtitle Display

Subtitles are displayed with the following characteristics:

- **Position**: Bottom center of the screen
- **Maximum lines**: 5 subtitle lines shown simultaneously
- **Fading**: Older subtitles fade based on age and position
- **Duration**: Subtitles fade out over 3 seconds (configurable in code)
- **Cleanup**: Very old subtitles are removed automatically

### Technical Implementation

The feature consists of several components:

1. **SubtitleWidget** (`core/output.py`): PyQt widget for displaying subtitles
2. **SoundSource** (`core/sources/sound.py`): Enhanced audio recording with real-time transcription
3. **Configuration** (`config/settings.py`): Configuration options and CLI arguments
4. **UI Integration** (`core/output.py`): Signal-based communication between components

## Requirements

- Python 3.8+
- PyQt6
- SpeechRecognition
- PyAudio
- NumPy

## Troubleshooting

### Subtitles Not Appearing

1. Check if real-time transcription is enabled:
   ```bash
   # Check config file
   cat config/config.json | grep realtime_transcription
   ```

2. Verify audio input device is working:
   ```bash
   # Test audio recording
   python main.py --default-source audio
   ```

3. Check logs for transcription errors:
   - Look for "Real-time transcription error" messages
   - Verify Google Speech Recognition API is accessible

### Poor Transcription Quality

1. **Adjust pause threshold**: Increase `transcription_pause_threshold` for longer segments
2. **Check audio quality**: Ensure microphone is working properly
3. **Reduce background noise**: Record in a quiet environment

### Performance Issues

1. **Disable real-time transcription**: Use `--disable-realtime-transcription` flag
2. **Increase pause threshold**: Longer segments reduce processing frequency
3. **Check system resources**: Ensure sufficient CPU and memory available

## Examples

### Basic Usage

```bash
# Start with audio source and real-time transcription enabled
python main.py --default-source audio
```

### Custom Configuration

```bash
# Start with 2-second pause threshold
python main.py --default-source audio --transcription-pause-threshold 2.0
```

### Disable Feature

```bash
# Start with real-time transcription disabled
python main.py --default-source audio --disable-realtime-transcription
```

## Integration with Existing Features

The real-time transcription feature integrates seamlessly with existing SnapSolve features:

- **Control Panel**: Works with the existing control panel UI
- **Hotkeys**: Compatible with all existing hotkey configurations
- **Audio Recording**: Enhances the existing audio recording functionality
- **Text Processing**: Transcribed text can be processed by the LLM pipeline

## Future Enhancements

Potential improvements for future versions:

- Support for multiple transcription engines (local vs cloud)
- Customizable subtitle appearance (fonts, colors, positions)
- Transcription history and export
- Multi-language support
- Confidence score display
- Real-time editing of transcriptions

## Credits

This feature uses:
- Google Speech Recognition API for transcription
- PyQt6 for subtitle display
- Existing SnapSolve architecture for integration