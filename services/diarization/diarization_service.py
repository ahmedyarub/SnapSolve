import logging
import os
import shutil
import tempfile
import warnings
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form

# Suppress annoying third-party warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote.audio.core.io")
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote.audio.models.blocks.pooling")
warnings.filterwarnings("ignore", message=".*Lightning automatically upgraded.*")
warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Suppress overly verbose third-party loggers
logging.getLogger("lightning.pytorch.utilities.upgrade_checkpoint").setLevel(logging.WARNING)
logging.getLogger("pytorch_lightning").setLevel(logging.WARNING)

# Determine device and compute type
try:
    import torch

    if torch.cuda.is_available():
        DEVICE = "cuda"
        COMPUTE_TYPE = "float16"
        logging.info("CUDA available. Using GPU (float16) for diarization.")
    else:
        DEVICE = "cpu"
        COMPUTE_TYPE = "int8"
        logging.info("CUDA not available. Falling back to CPU (int8).")
except ImportError:
    DEVICE = "cpu"
    COMPUTE_TYPE = "int8"
    logging.info("Torch not available. Falling back to CPU (int8).")


def diarize_mic(wav_path, speaker_name, model_name="base"):
    # Use faster-whisper to transcribe mic
    from faster_whisper import WhisperModel
    logging.info(f"Transcribing mic with faster-whisper ({model_name}) on {DEVICE}...")
    model = WhisperModel(model_name, device=DEVICE, compute_type=COMPUTE_TYPE)
    segments, info = model.transcribe(wav_path, beam_size=5)
    results = []
    for segment in segments:
        results.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
            "speaker": speaker_name
        })
    return results


def diarize_loopback(wav_path, model_name="base"):
    # Use whisperx to transcribe and diarize loopback
    import whisperx
    logging.info(f"Transcribing and diarizing loopback with whisperx ({model_name}) on {DEVICE}...")
    hf_token = os.environ.get("HF_TOKEN", False)

    model = whisperx.load_model(model_name, DEVICE, compute_type=COMPUTE_TYPE)
    audio = whisperx.load_audio(wav_path)
    result = model.transcribe(audio, batch_size=16)

    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=DEVICE)
    result = whisperx.align(result["segments"], model_a, metadata, audio, DEVICE, return_char_alignments=False)

    from whisperx.diarize import DiarizationPipeline
    diarize_model = DiarizationPipeline(token=hf_token, device=DEVICE)
    diarize_segments = diarize_model(audio)

    result = whisperx.assign_word_speakers(diarize_segments, result)

    output = []
    for segment in result["segments"]:
        output.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip(),
            "speaker": segment.get("speaker", "SPEAKER_UNKNOWN")
        })
    return output


app = FastAPI(title="Diarization Service")


@app.post("/diarize")
async def diarize(
        speaker_name: str = Form("You"),
        model: str = Form("base"),
        audio_mic: Optional[UploadFile] = File(None),
        audio_loopback: Optional[UploadFile] = File(None)
):
    logging.info("Received diarization request")

    temp_dir = tempfile.mkdtemp(prefix="diarize_svc_")
    all_segments = []

    try:
        if audio_mic and audio_mic.filename:
            mic_path = os.path.join(temp_dir, "audio_mic.wav")
            with open(mic_path, "wb") as buffer:
                shutil.copyfileobj(audio_mic.file, buffer)
            logging.info("Processing mic audio...")
            all_segments.extend(diarize_mic(mic_path, speaker_name, model))

        if audio_loopback and audio_loopback.filename:
            loopback_path = os.path.join(temp_dir, "audio_loopback.wav")
            with open(loopback_path, "wb") as buffer:
                shutil.copyfileobj(audio_loopback.file, buffer)
            logging.info("Processing loopback audio...")
            all_segments.extend(diarize_loopback(loopback_path, model))

    except Exception as e:
        logging.error(f"Error during diarization: {e}")
        return {"error": str(e)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    all_segments.sort(key=lambda x: x["start"])
    logging.info(f"Diarization complete. Found {len(all_segments)} segments.")
    return {"segments": all_segments}


if __name__ == "__main__":
    import signal
    import uvicorn


    def _handle_exit(_sig, _frame):
        os._exit(0)


    signal.signal(signal.SIGINT, _handle_exit)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _handle_exit)

    uvicorn.run(app, host="127.0.0.1", port=8001)
