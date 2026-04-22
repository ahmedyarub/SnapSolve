import logging
import platform
import threading
import os
import wave # Import wave module

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
        # Warmup is now handled asynchronously from main.py, so no direct call here.

    def _speak(self, text: str):
        if not text.strip():
            logger.debug("AudioSink._speak called with empty text, skipping.")
            return

        try:
            from piper import PiperVoice
            # import wave # Already imported at the top
            # import os # Already imported at the top

            if not os.path.exists(self.piper_model):
                logger.warning(f"Piper model not found at {self.piper_model}. Audio TTS will be skipped.")
                return
            
            # Ensure the config file exists alongside the model
            piper_config_path = self.piper_model + ".json"
            if not os.path.exists(piper_config_path):
                logger.warning(f"Piper config file not found at {piper_config_path}. Audio TTS will be skipped.")
                return

            if not self.voice:
                logger.info("Loading Piper voice model for speaking...")
                self.voice = PiperVoice.load(self.piper_model, config_path=piper_config_path)
                logger.info("Piper voice model loaded.")

            logger.info(f"Synthesizing audio via Piper for text: '{text[:50]}...'")

            wav_file = "temp_output.wav"
            
            # Synthesize directly to a WAV file
            with wave.open(wav_file, "wb") as wav:
                self.voice.synthesize_wav(text, wav)

            logger.info(f"Audio synthesized to {wav_file}. Attempting playback.")

            # Play the audio
            if os.path.exists(wav_file):
                if platform.system() == 'Windows':
                    import winsound
                    winsound.PlaySound(wav_file, winsound.SND_FILENAME)
                elif platform.system() == 'Darwin':
                    import subprocess
                    subprocess.run(["afplay", wav_file])
                else: # Linux and other POSIX systems
                    import subprocess
                    subprocess.run(["aplay", wav_file])
                
                logger.info(f"Playback of {wav_file} completed.")
                # Cleanup - keep commented out for now as per debugging instructions
                # os.remove(wav_file)

        except ImportError:
            logger.error("piper-tts package not installed. Please install it using 'pip install piper-tts'")
        except Exception as e:
            logger.error(f"Failed to execute Piper TTS: {e}", exc_info=True) # Log full traceback

    def warmup(self):
        """Pre-loads the Piper voice model into memory."""
        try:
            from piper import PiperVoice
            # import os # Already imported at the top

            if not os.path.exists(self.piper_model):
                logger.warning(f"Piper model not found at {self.piper_model}. TTS warmup skipped.")
                return

            piper_config_path = self.piper_model + ".json"
            if not os.path.exists(piper_config_path):
                logger.warning(f"Piper config file not found at {piper_config_path}. TTS warmup skipped.")
                return

            if not self.voice:
                logger.info("Warming up Piper TTS model...")
                self.voice = PiperVoice.load(self.piper_model, config_path=piper_config_path)
                logger.info("Piper TTS warmup complete.")
                # Provide audible feedback that TTS is ready, asynchronously
                threading.Thread(target=self._speak, args=("Warming up TTS",), daemon=True).start()
        except ImportError:
            logger.error("piper-tts package not installed. Cannot warmup TTS.")
        except Exception as e:
            logger.error(f"Error warming up Piper TTS: {e}", exc_info=True) # Log full traceback

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if not self.enabled:
            logger.debug(f"AudioSink disabled, ignoring chunk: '{chunk[:50]}...'")
            return

        if self.cancel_event.is_set():
            logger.debug("AudioSink cancelled, ignoring chunk.")
            return

        logger.debug(f"AudioSink received chunk (main={is_main}, replace={replace}): '{chunk[:50]}...'")

        # If replace is True and the chunk is empty, it's likely a UI clear signal.
        # AudioSink should ignore this as it accumulates for a single final speech.
        if replace and not chunk.strip():
            logger.debug("AudioSink ignoring empty chunk with replace=True (likely UI clear signal).")
            return

        if replace: # If replace is true and chunk is NOT empty, then replace.
            self.accumulated_text = chunk
        else:
            self.accumulated_text += chunk

    def finish(self):
        """Called when the LLM stream is complete."""
        if not self.enabled or self.cancel_event.is_set():
            logger.debug("AudioSink finish called but disabled or cancelled.")
            return

        if self.accumulated_text:
            logger.debug(f"AudioSink finish called. Accumulated text: '{self.accumulated_text[:50]}...'")
            # Run speaking in a background thread so it doesn't block
            threading.Thread(target=self._speak, args=(self.accumulated_text,), daemon=True).start()
            self.accumulated_text = ""
        else:
            logger.debug("AudioSink finish called but no accumulated text to speak.")
