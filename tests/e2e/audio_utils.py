import speech_recognition as sr


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
                audio_data = sr.AudioData(b''.join(frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH)
                audio_queue.put(audio_data)
            print("[Recorder] Background audio recording stopped.")
    except Exception as e:
        print(f"[Recorder] Error during background recording setup or execution: {e}")
