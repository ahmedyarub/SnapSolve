# Transcription Test Implementation Details

## Overview

The Transcription Test feature in `tests/sanity/test_sound.py` provides real-time speech-to-text transcription using a WhisperLive server. This test automatically plays the text from the "Text to Speak" field through the audio output, records the audio from the input device, and streams it to a transcription server for real-time processing.

## Architecture

### Components

1. **TranscriptionClient**: WebSocket client for communicating with WhisperLive server
2. **SoundTestApp**: Main PyQt6 application with UI and test orchestration
3. **WorkerSignals**: Qt signals for thread-safe communication between background threads and UI

### Data Flow

```
Text to Speak → Piper TTS → Audio Output → Microphone Input → 
TranscriptionClient → WhisperLive Server → Real-time Transcription → 
UI Display → Comparison with Original Text
```

## TranscriptionClient Class

### Purpose

Handles WebSocket communication with the WhisperLive transcription server and manages real-time audio streaming.

### Key Features

- **WebSocket Connection**: Establishes persistent connection to `ws://localhost:9090`
- **Configuration**: Sends language, model, and VAD settings to server
- **Audio Streaming**: Sends audio packets in real-time for processing
- **Segment Processing**: Handles transcription segments as they arrive
- **Callback System**: Provides real-time transcription results via callback

### Initialization

```python
TranscriptionClient(
    host="localhost",           # WhisperLive server address
    port=9090,                 # WhisperLive server port
    lang="en",                 # Language for transcription
    model="small",             # Whisper model size
    use_vad=True,              # Voice Activity Detection
    transcription_callback=None  # Callback for real-time results
)
```

### Connection Lifecycle

1. **Connection Setup**: WebSocket connection established in background thread
2. **Configuration**: Client sends configuration message with UID, language, task, model, and VAD settings
3. **Server Ready**: Waits for `SERVER_READY` message from server
4. **Audio Streaming**: Sends audio packets as binary WebSocket messages
5. **Segment Processing**: Receives and processes transcription segments
6. **Cleanup**: Sends `END_OF_AUDIO` signal and closes connection

### Message Protocol

#### Client → Server

**Configuration Message** (sent on connection):
```json
{
    "uid": "unique-client-id",
    "language": "en",
    "task": "transcribe",
    "model": "small",
    "use_vad": true
}
```

**Audio Packets**: Binary audio data sent as WebSocket binary frames

**End Signal**: `END_OF_AUDIO` string as binary message

#### Server → Client

**Status Messages**:
- `WAIT`: Server is full, estimated wait time provided
- `ERROR`: Server error occurred
- `WARNING`: Server warning message
- `SERVER_READY`: Server ready to receive audio
- `DISCONNECT`: Server disconnected due to timeout

**Transcription Segments**:
```json
{
    "segments": [
        {
            "text": "transcribed text",
            "start": 0.0,
            "end": 1.5,
            "completed": true
        }
    ]
}
```

### Audio Processing

**Audio Format Requirements**:
- Sample Rate: 16000 Hz
- Channels: 1 (mono)
- Format: 16-bit PCM (int16)
- Chunk Size: 4096 samples

**Conversion Process**:
1. Record audio as int16 PCM from PyAudio
2. Convert to float32: `audio_array.astype(np.float32) / 32768.0`
3. Send as binary: `audio_array.tobytes()`

### Segment Processing

The `process_segments` method handles incoming transcription segments:

1. **Deduplication**: Filters out duplicate text segments
2. **Completion Tracking**: Tracks incomplete vs. completed segments
3. **Transcript Building**: Maintains ordered list of completed segments
4. **Callback Invocation**: Calls transcription callback with new text

**Segment States**:
- **Incomplete**: Last segment in response, may be updated
- **Completed**: Finalized segment, added to transcript

### Error Handling

- **Connection Errors**: Caught and logged, sets `server_error` flag
- **Timeout**: 30-second timeout for server readiness
- **Packet Send Errors**: Logged but don't stop recording
- **Callback Errors**: Caught and logged, don't affect transcription

## SoundTestApp Integration

### UI Components

**New Elements**:
- `transcription_btn`: "Transcription Test" button
- `append_heard` signal: For real-time text updates
- `transcription_finished` signal: Indicates test completion

**Existing Elements Used**:
- `speak_text`: Text to be spoken and transcribed
- `heard_text`: Real-time transcription display
- `volume_bar`: Microphone volume visualization
- `log_text`: Test progress and results

### Test Flow

#### 1. Test Initialization (`start_transcription_test`)

```python
def start_transcription_test(self):
    # Disable buttons
    # Clear UI elements
    # Get device indices and text
    # Set transcription state
    # Start playback thread
    # Start transcription thread
```

**Key Actions**:
- Disables both test buttons to prevent concurrent tests
- Clears previous results and logs
- Validates device selection
- Initializes transcription state variables
- Launches parallel threads for playback and transcription

#### 2. Audio Playback (`play_audio`)

**Process**:
1. Load Piper voice model
2. Synthesize text to WAV file
3. Play WAV through selected output device
4. Emit `playback_finished` signal when done

**Synchronization**: The transcription thread waits for `playback_done` flag to know when to stop recording.

#### 3. Transcription Execution (`run_transcription`)

**Main Orchestration Method** - broken into helper methods:

##### a. Server Connection (`_wait_for_transcription_server`)

```python
def _wait_for_transcription_server(self):
    # Create TranscriptionClient
    # Wait for SERVER_READY message
    # Handle errors and timeouts
    # Return success/failure
```

**Timeout Handling**: 30-second timeout with periodic checks for:
- Server waiting status
- Server errors
- Connection establishment

##### b. Audio Recording and Streaming (`_record_and_stream_audio`)

```python
def _record_and_stream_audio(self, device_index):
    # Open PyAudio stream (16kHz, mono, int16)
    # Record while playback is active
    # Calculate and display volume
    # Convert audio to float32
    # Stream to transcription server
    # Send END_OF_AUDIO signal
    # Wait for final processing
    # Close connection
```

**Recording Loop**:
```python
while self.is_transcribing and not self.playback_done:
    data = stream.read(chunk, exception_on_overflow=False)
    # Calculate volume
    # Convert to float32
    # Send to server
```

**Volume Calculation**:
```python
audio_data = np.frombuffer(data, dtype=np.int16)
vol = np.abs(audio_data).mean()
scaled_vol = min(100, int((vol / 32768.0) * 500))
```

##### c. Result Comparison (`_compare_transcription_results`)

```python
def _compare_transcription_results(self):
    # Get original and transcribed text
    # Compare for exact match
    # Check for partial match (word overlap)
    # Calculate match ratio
    # Log results
```

**Comparison Logic**:
1. **Exact Match**: One text contains the other
2. **Partial Match**: Calculate word overlap ratio
3. **Failure**: No common words

**Match Ratio Calculation**:
```python
words_original = set(original_text.split())
words_transcribed = set(transcribed_text.split())
common_words = words_original & words_transcribed
match_ratio = len(common_words) / max(len(words_original), len(words_transcribed))
```

##### d. Cleanup (`_cleanup_transcription`)

```python
def _cleanup_transcription(self):
    # Reset volume bar
    # Reset transcription state
    # Re-enable buttons
    # Emit finished signal
```

#### 4. Real-time Updates (`on_transcription_result`)

```python
def on_transcription_result(self, text, segments):
    # Update transcription text
    # Append to UI display
    # Log transcription
```

**UI Update**: Uses `append_heard` signal to update UI in real-time without blocking.

### Thread Safety

**Qt Signal Mechanism**:
- All UI updates use Qt signals for thread safety
- Background threads emit signals, UI thread handles updates
- Prevents race conditions and UI freezing

**Key Signals**:
- `log_message`: Log messages to UI
- `update_volume`: Update volume bar
- `append_heard`: Append transcription text
- `transcription_finished`: Test completion notification

**Button Re-enabling**:
```python
QtCore.QMetaObject.invokeMethod(
    self.transcription_btn,
    "setEnabled",
    QtCore.Qt.ConnectionType.QueuedConnection,
    QtCore.Q_ARG(bool, True),
)
```

## Comparison with Recording Test

### Recording Test

- **Purpose**: Test audio input/output and Google Speech Recognition
- **Method**: Record entire audio, then process with Google API
- **Timing**: Post-processing after recording completes
- **Recognition**: Google Cloud Speech-to-Text API
- **Result**: Single final transcription

### Transcription Test

- **Purpose**: Test real-time transcription with WhisperLive
- **Method**: Stream audio while recording, process in real-time
- **Timing**: Real-time updates during recording
- **Recognition**: Local WhisperLive server (Whisper model)
- **Result**: Progressive transcription updates

### Key Differences

| Aspect | Recording Test | Transcription Test |
|--------|---------------|-------------------|
| Recognition Service | Google Cloud API | Local WhisperLive |
| Processing Mode | Batch (post-recording) | Streaming (real-time) |
| Updates | Single final result | Progressive updates |
| Network Dependency | Required (Google API) | Optional (local server) |
| Latency | Higher (upload + processing) | Lower (local processing) |
| Privacy | Cloud processing | Local processing |

## Technical Requirements

### Dependencies

**Required Packages**:
- `websocket-client`: WebSocket communication
- `pyaudio`: Audio recording/playback
- `numpy`: Audio data processing
- `PyQt6`: UI framework

**External Services**:
- WhisperLive server running on `localhost:9090`
- Piper voice model for TTS

### System Requirements

**Audio Hardware**:
- Microphone (input device)
- Speakers/audio output (for playback)

**Network**:
- Local network access for WhisperLive server
- Internet access (optional, for Google API in recording test)

**Performance**:
- CPU: Modern processor for real-time audio processing
- Memory: Sufficient for audio buffers and model loading
- Latency: Low audio latency for real-time transcription

## Configuration

### WhisperLive Server

**Default Configuration**:
- Host: `localhost`
- Port: `9090`
- Model: `small`
- Language: `en`
- VAD: Enabled

**Server Startup** (typical):
```bash
python -m whisper_live.server --port 9090 --model small
```

### Audio Settings

**Recording Parameters**:
- Sample Rate: 16000 Hz
- Channels: 1 (mono)
- Bit Depth: 16-bit
- Buffer Size: 4096 samples

**Playback Parameters**:
- Sample Rate: Determined by Piper model
- Channels: Determined by Piper model
- Bit Depth: 16-bit

## Error Handling

### Common Issues

**1. Server Connection Failed**
- **Symptom**: "Failed to connect to transcription server"
- **Cause**: WhisperLive server not running
- **Solution**: Start WhisperLive server on localhost:9090

**2. Timeout Waiting for Server**
- **Symptom**: "Timeout waiting for transcription server"
- **Cause**: Server overloaded or network issues
- **Solution**: Check server status, restart if needed

**3. Audio Device Errors**
- **Symptom**: "Recording error" or "Playback error"
- **Cause**: Device in use or not available
- **Solution**: Select different audio device, close other apps

**4. Poor Transcription Quality**
- **Symptom**: Low match ratio or incorrect transcription
- **Cause**: Background noise, poor audio quality, wrong language
- **Solution**: Improve audio environment, check language settings

### Error Recovery

**Automatic Recovery**:
- Connection errors: Logged, test stops gracefully
- Audio errors: Logged, recording continues if possible
- Callback errors: Logged, transcription continues

**Manual Recovery**:
- Restart WhisperLive server
- Select different audio devices
- Adjust audio levels
- Check network connectivity

## Performance Considerations

### Latency

**Factors Affecting Latency**:
- Audio buffer size (4096 samples = ~256ms at 16kHz)
- Network latency (if using remote server)
- Model inference time (depends on model size)
- UI thread responsiveness

**Optimization Tips**:
- Use smaller buffer sizes for lower latency (may increase CPU usage)
- Use local WhisperLive server for minimal network latency
- Use smaller Whisper models for faster inference

### Resource Usage

**Memory**:
- Audio buffers: ~8KB per chunk (4096 samples × 2 bytes)
- Transcription history: Grows with test duration
- Model loading: Depends on Whisper model size

**CPU**:
- Audio processing: Minimal
- WebSocket communication: Low
- Transcription: Depends on model and server load

**Network**:
- Bandwidth: ~256 kbps for audio streaming
- Latency: Critical for real-time performance

## Testing and Validation

### Manual Testing

**Test Procedure**:
1. Start WhisperLive server
2. Launch test_sound application
3. Select input/output devices
4. Enter test text in "Text to Speak" field
5. Click "Transcription Test"
6. Observe real-time transcription updates
7. Review final comparison results

**Expected Results**:
- Audio plays through output device
- Real-time transcription appears in "Text Heard" field
- Volume bar shows microphone activity
- Log shows progress and final results
- Comparison shows match quality

### Automated Testing

**Test Scenarios**:
1. **Basic Test**: Simple text transcription
2. **Long Text**: Extended text transcription
3. **Noise Test**: Transcription with background noise
4. **Speed Test**: Rapid speech transcription
5. **Accuracy Test**: Known text for accuracy validation

**Validation Criteria**:
- Connection established successfully
- Audio recorded without errors
- Transcription updates in real-time
- Final comparison completes
- Match ratio meets expectations

## Future Enhancements

### Potential Improvements

**1. Multiple Language Support**
- Add language selection dropdown
- Support multi-language transcription
- Language detection

**2. Advanced Audio Processing**
- Noise cancellation
- Echo cancellation
- Audio normalization

**3. Enhanced UI**
- Real-time waveform visualization
- Confidence scores display
- Segment timing visualization

**4. Configuration Options**
- Custom server host/port
- Model selection (tiny, base, small, medium, large)
- VAD sensitivity adjustment
- Timeout configuration

**5. Export Features**
- Save transcription to file
- Export audio with timestamps
- Generate SRT subtitle files

**6. Performance Monitoring**
- Latency measurement
- Resource usage tracking
- Quality metrics

## Troubleshooting Guide

### Debug Mode

Enable detailed logging:
```python
logging.basicConfig(level=logging.DEBUG)
```

### Common Debugging Steps

1. **Check Server Status**:
   ```bash
   # Verify WhisperLive is running
   curl http://localhost:9090/health
   ```

2. **Test Audio Devices**:
   ```python
   # List available devices
   import pyaudio
   p = pyaudio.PyAudio()
   for i in range(p.get_device_count()):
       print(p.get_device_info_by_index(i))
   ```

3. **Monitor WebSocket Traffic**:
   ```bash
   # Use WebSocket debugging tools
   # Check connection establishment
   # Monitor message flow
   ```

4. **Profile Performance**:
   ```python
   # Add timing measurements
   import time
   start = time.time()
   # ... operation ...
   elapsed = time.time() - start
   print(f"Operation took {elapsed:.3f}s")
   ```

## Conclusion

The Transcription Test feature provides a comprehensive real-time speech-to-text testing capability integrated with the existing sound testing framework. It leverages WhisperLive for accurate, low-latency transcription while maintaining the same user experience as the Recording Test.

The implementation demonstrates proper threading, signal handling, error management, and UI integration patterns that can be extended for additional audio processing features.