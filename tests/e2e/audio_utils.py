import numpy as np
import pyaudio
import speech_recognition as sr
from piper import PiperVoice


def get_microphone_index(target_name: str) -> int | None:
    """
    Searches available microphones for a given name and returns its index.
    """
    mic_list = sr.Microphone.list_microphone_names()

    for index, name in enumerate(mic_list):
        if target_name.lower() in name.lower():
            print(f"Matched: [{index}] {name}")
            return index

    print(f"Error: No device matching '{target_name}' was found.")
    print("Available devices:", mic_list)
    return None


def record_audio_in_background(stop_event, audio_queue, device_index):
    """Records audio continuously in the background."""
    frames = []
    try:
        print("[Recorder] Background audio recording started.")
        with sr.Microphone(device_index=device_index) as source:
            stream = source.stream

            if stream is None:
                print("[Recorder] No audio stream found.")
                return

            while not stop_event.is_set():
                try:
                    data = stream.read(source.CHUNK)
                    frames.append(data)
                except Exception as e:
                    print(f"[Recorder] Error reading audio stream: {e}")
                    break

            if frames:
                audio_data = sr.AudioData(
                    b"".join(frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH
                )
                audio_queue.put(audio_data)
            print("[Recorder] Background audio recording stopped.")
    except Exception as e:
        print(f"[Recorder] Error during background recording setup or execution: {e}")


def speak(text: str, output_device: str):
    voice = PiperVoice.load(
        "../en_US-lessac-high.onnx", config_path="../en_US-lessac-high.onnx.json"
    )

    print(f"Synthesizing audio via Piper for text: '{text[:50]}...'")

    # Stream audio directly without creating a .wav file
    p = pyaudio.PyAudio()

    target_device_index: int | None = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        host_api_name = p.get_host_api_info_by_index(int(info["hostApi"]))["name"]

        # Hardcode "MME" for comparison
        if info["name"] == output_device and host_api_name == "MME":
            target_device_index = int(info["index"])
            print(
                f"Found configured audio device: {output_device} (MME) at index {target_device_index}"
            )
            break
    if target_device_index is None:
        print(
            f"Configured audio device '{output_device}' (MME) not found. Attempting playback with default device."
        )

    # Get the first chunk to determine audio format
    first_chunk = None
    for chunk in voice.synthesize(text):
        first_chunk = chunk
        break

    if first_chunk is None:
        print("No audio chunks generated.")
        p.terminate()
        return

    # Open stream with the audio format from the first chunk
    stream = p.open(
        format=p.get_format_from_width(first_chunk.sample_width),
        channels=first_chunk.sample_channels,
        rate=first_chunk.sample_rate,
        output=True,
        output_device_index=target_device_index,
    )
    device_name = output_device if target_device_index is not None else 'Default Device'
    print(f"Playing audio on {device_name}")

    # Stream all audio chunks
    for chunk in voice.synthesize(text):
        # Convert float array to bytes for PyAudio
        audio_bytes = chunk.audio_float_array.astype(np.int16).tobytes()
        stream.write(audio_bytes)

    stream.stop_stream()
    stream.close()
    p.terminate()

    print("Audio playback completed.")
