### VB-Audio Virtual Audio Cable

VB-Audio Virtual Audio Cable is a virtual audio device that allows you to route audio between applications. This is particularly useful for:

- **Testing TTS output** without hearing it through your speakers
- **Recording system audio** for testing purposes
- **Audio routing between applications** without physical cables

**Installation:**

1. Download VB-Audio Virtual Audio Cable from [vb-audio.com](https://vb-audio.com/Cable/)
2. Run the installer and follow the on-screen instructions
3. Restart your computer after installation
4. You should see two new audio devices in your Windows sound settings:
   - **CABLE Input (VB-Audio Virtual Cable)** - This acts as a virtual microphone
   - **CABLE Output (VB-Audio Virtual Cable)** - This acts as a virtual speaker

**Configuration:**

1. Open Windows Sound Settings (`Win + I` → System → Sound)
2. Under "Input", you can select "CABLE Input (VB-Audio Virtual Cable)" as your recording device
3. Under "Output", you can select "CABLE Output (VB-Audio Virtual Cable)" as your playback device

**How the App Uses VB-Audio:**

The application uses VB-Audio in two ways:

1. **TTS Output (CABLE Output):**
   - When you enable audio output in `config.json` with `"output_mode": ["popup", "audio"]`
   - The app sends TTS audio to the configured output device
   - If you set `"tts_output_device_name": "CABLE Output (VB-Audio Virtual Cable)"`, the TTS audio will be sent to the virtual cable instead of your speakers
   - This allows you to route the audio to other applications (like recording software) without hearing it yourself

2. **Audio Input (CABLE Input):**
   - When using audio input with `"default_source": "audio"`
   - The app can record from the virtual cable input
   - If you set `"audio_input_device_name": "CABLE Input (VB-Audio Virtual Cable)"`, the app will record audio sent to the virtual cable
   - This is useful for recording system audio or audio from other applications

**Example Configuration:**

```json
{
  "output_mode": ["popup", "audio"],
  "tts_output_device_name": "CABLE Output (VB-Audio Virtual Cable)",
  "audio_input_device_name": "CABLE Input (VB-Audio Virtual Cable)",
  "piper_model": "en_US-lessac-medium.onnx"
}
```

**How Tests Use VB-Audio:**

The test suite uses VB-Audio for automated audio testing:

1. **TTS Testing:**
   - Tests send TTS output to CABLE Output to avoid playing audio during test runs
   - This allows tests to verify TTS functionality without disturbing the user
   - The test configuration typically uses: `"tts_output_device_name": "CABLE Output (VB-Audio Virtual Cable)"`

2. **Audio Recording Testing:**
   - Tests can record from CABLE Input to verify audio capture functionality
   - This allows tests to verify speech recognition without requiring actual microphone input
   - The test configuration typically uses: `"audio_input_device_name": "CABLE Input (VB-Audio Virtual Cable)"`

3. **End-to-End Audio Testing:**
   - Some tests route audio from CABLE Output to CABLE Input to create a complete audio loop
   - This allows testing of the entire audio pipeline (TTS → recording → speech recognition) without external audio hardware
   - This is particularly useful for CI/CD environments and automated testing

**Benefits for Development and Testing:**

- **Silent Testing:** Run audio tests without hearing TTS output
- **Automated Testing:** Enable audio testing in CI/CD environments without physical audio hardware
- **Audio Routing:** Route audio between applications for complex workflows
- **System Audio Recording:** Record audio from any application that can output to CABLE Output

**Troubleshooting:**

- If you don't see the VB-Audio devices, try restarting your computer after installation
- Make sure the VB-Audio driver is properly installed in Windows Device Manager
- If audio isn't routing correctly, check that the correct VB-Audio device is selected in both Windows sound settings and the app configuration
- For testing purposes, you may need to configure your recording software to use CABLE Input as its input source
