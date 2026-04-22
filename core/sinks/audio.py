import logging
import platform
import threading

from .base import Sink

logger = logging.getLogger(__name__)


class AudioSink(Sink):
    """
    A Sink that plays audio using the piper-tts Python package.
    """

    def __init__(self, config, cancel_event: threading.Event = None):
        super().__init__(cancel_event)
        self.config = config
        self.enabled = 'audio' in self.config.get('output_mode', ['popup'])
        self.accumulated_text = ""
        self.piper_model = self.config.get('piper_model', 'en_US-lessac-medium.onnx')

        self.voice = None
        if self.enabled and self.config.get('warmup_tts', False):
            self.warmup()

    def _speak(self, text: str):
        if not text.strip():
            return

        try:
            from piper import PiperVoice
            import wave
            import os

            if not os.path.exists(self.piper_model):
                logger.warning(f"Piper model not found at {self.piper_model}. Audio TTS will be skipped.")
                return

            if not self.voice:
                self.voice = PiperVoice.load(self.piper_model, self.piper_model + ".json")

            logger.info(f"Synthesizing audio via Piper...")

            wav_file = "temp_output.wav"

            # Synthesize directly to a WAV file
            with wave.open(wav_file, "wb") as wav:
                self.voice.synthesize_wav(text, wav)

            # Play the audio
            if os.path.exists(wav_file):
                if platform.system() == 'Windows':
                    import winsound
                    winsound.PlaySound(wav_file, winsound.SND_FILENAME)
                elif platform.system() == 'Darwin':
                    import subprocess
                    subprocess.run(["afplay", wav_file])
                else:
                    import subprocess
                    subprocess.run(["aplay", wav_file])

                # Cleanup
                os.remove(wav_file)

        except ImportError:
            logger.error("piper-tts package not installed. Please install it using 'pip install piper-tts'")
        except Exception as e:
            logger.error(f"Failed to execute Piper TTS: {e}")

    def warmup(self):
        """Pre-loads the Piper voice model into memory."""
        try:
            from piper import PiperVoice
            import os

            if not os.path.exists(self.piper_model):
                logger.warning(f"Piper model not found at {self.piper_model}. TTS warmup skipped.")
                return

            if not self.voice:
                logger.info("Warming up Piper TTS model...")
                self.voice = PiperVoice.load(self.piper_model)
                logger.info("Piper TTS warmup complete.")

            self._speak("Warming up Piper TTS model...")
        except ImportError:
            logger.error("piper-tts package not installed. Cannot warmup TTS.")
        except Exception as e:
            logger.error(f"Error warming up Piper TTS: {e}")

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if not self.enabled:
            return

        if self.cancel_event.is_set():
            return

        if replace:
            self.accumulated_text = chunk
        else:
            self.accumulated_text += chunk

    def finish(self):
        """Called when the LLM stream is complete."""
        if not self.enabled or self.cancel_event.is_set():
            return

        if self.accumulated_text:
            # Run speaking in a background thread so it doesn't block
            threading.Thread(target=self._speak, args=(self.accumulated_text,), daemon=True).start()
            self.accumulated_text = ""
