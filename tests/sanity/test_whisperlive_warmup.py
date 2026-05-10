def _start_whisperlive_if_needed():
    process = None
    if not is_whisperlive_service_online():
        print("Starting WhisperLive service...")
        process = start_whisperlive_service()
        time.sleep(10)
    if not is_whisperlive_service_online():
        print("Failed to start WhisperLive service.")
        if process: process.terminate()
        return False, process
    print("WhisperLive service is online.")
    return True, process

def _get_piper_model():
    piper_model = "en_US-lessac-medium.onnx"
    try:
        with open("config/config.json", "r") as f:
            config = json.load(f)
            piper_model = config.get("piper_model", piper_model)
    except Exception:
        pass
    return piper_model

def _send_audio_to_client(client_socket, test_wav):
    import wave, time, resampy, numpy as np
    print("Sending audio file...")
    with wave.open(test_wav, "rb") as wf:
        sample_rate = wf.getframerate()
        target_rate = 16000
        chunk_size = 4096
        data = wf.readframes(chunk_size)
        while data:
            audio_array = (np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0)
            if sample_rate != target_rate:
                audio_array = resampy.resample(audio_array, sample_rate, target_rate)
            client_socket.send_packet_to_server(audio_array.tobytes())
            time.sleep(len(audio_array) / target_rate)
            data = wf.readframes(chunk_size)

def _evaluate_transcription(test_text, transcription_result):
    final_transcription = " ".join(transcription_result)
    print(f"\nOriginal text: {test_text}")
    print(f"Transcribed text: {final_transcription}")

    test_words = set(test_text.lower().replace(".", "").split())
    transcribed_words = set(final_transcription.lower().replace(".", "").split())

    intersection = test_words.intersection(transcribed_words)
    match_ratio = len(intersection) / len(test_words) if test_words else 0
    print(f"Match ratio: {match_ratio:.2f}")

    success = match_ratio > 0.5
    if success: print("Warmup and test successful!")
    else: print("Warmup and test failed: Transcription mismatch.")
    return success

def _run_transcription_test(test_wav, test_text, process):
    from whisper_live.client import TranscriptionClient
    transcription_result = []

    def on_transcription(x, segments):
        if segments:
            for seg in segments:
                text = seg.get("text", "").strip()
                if text: transcription_result.append(text)

    print("Connecting to WhisperLive client...")
    client = TranscriptionClient(
        host="localhost", port=9090, lang="en", use_vad=True,
        transcription_callback=on_transcription,
    )

    c = client.client
    timeout = 15
    start_time = time.time()
    while not getattr(c, "recording", False):
        if time.time() - start_time > timeout:
            print("Timeout waiting for WhisperLive client.")
            break
        time.sleep(0.5)

    if not getattr(c, "recording", False):
        print("Failed to connect to WhisperLive client.")
        if process: process.terminate()
        return False

    _send_audio_to_client(c, test_wav)

    print("Finished sending audio. Waiting for final transcription...")
    c.send_packet_to_server("END_OF_AUDIO".encode("utf-8"))
    time.sleep(5)
    c.close_websocket()

    return _evaluate_transcription(test_text, transcription_result)

import json
import os
import sys
import time
import wave

# Add parent directories to sys.path to access core modules
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from core.sources.sound import start_whisperlive_service, is_whisperlive_service_online


def generate_audio_piper(text, output_wav, piper_model="en_US-lessac-medium.onnx"):
    try:
        from piper import PiperVoice

        config_path = piper_model + ".json"

        if not os.path.exists(piper_model):
            print(f"Error: Piper model not found at {piper_model}")
            return False

        voice = PiperVoice.load(piper_model, config_path=config_path)

        with wave.open(output_wav, "wb") as wav:
            voice.synthesize_wav(text, wav)

        print(f"Generated test audio: {output_wav}")
        return True
    except Exception as e:
        print(f"Error generating audio: {e}")
        return False


def test_whisperlive_warmup():
    print("Testing WhisperLive warmup process...")

    online, process = _start_whisperlive_if_needed()
    if not online: return False

    test_text = "This is a test of the whisper live real time transcription system."
    test_wav = "test_whisperlive_warmup.wav"

    if not generate_audio_piper(test_text, test_wav, _get_piper_model()):
        print("Failed to generate test audio.")
        if process: process.terminate()
        return False

    try:
        success = _run_transcription_test(test_wav, test_text, process)
        if os.path.exists(test_wav): os.remove(test_wav)
        if process: process.terminate()
        return success
    except Exception as e:
        print(f"Error during testing: {e}")
        if process: process.terminate()
        return False


if __name__ == "__main__":
    success = test_whisperlive_warmup()
    sys.exit(0 if success else 1)
