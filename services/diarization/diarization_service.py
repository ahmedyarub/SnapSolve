import functools
import logging
import os
import shutil
import tempfile
import warnings

from fastapi import FastAPI, File, Form, UploadFile

# Suppress annoying third-party warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote.audio.core.io")
warnings.filterwarnings(
    "ignore", category=UserWarning, module="pyannote.audio.models.blocks.pooling"
)
warnings.filterwarnings("ignore", message=".*Lightning automatically upgraded.*")
warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Suppress overly verbose third-party loggers
logging.getLogger("lightning.pytorch.utilities.upgrade_checkpoint").setLevel(
    logging.WARNING
)
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


# Models stay loaded between requests: loading them onto the GPU takes seconds.
# maxsize bounds VRAM when the client switches models.
@functools.lru_cache(maxsize=2)
def _whisper_model(model_name):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=DEVICE, compute_type=COMPUTE_TYPE)


@functools.lru_cache(maxsize=2)
def _whisperx_model(model_name):
    import whisperx

    return whisperx.load_model(model_name, DEVICE, compute_type=COMPUTE_TYPE)


@functools.lru_cache(maxsize=4)
def _align_model(language_code):
    import whisperx

    return whisperx.load_align_model(language_code=language_code, device=DEVICE)


@functools.lru_cache(maxsize=1)
def _diarization_pipeline(hf_token):
    from whisperx.diarize import DiarizationPipeline

    return DiarizationPipeline(token=hf_token, device=DEVICE)


def diarize_mic(wav_path, speaker_name, model_name="base"):
    # Use faster-whisper to transcribe mic
    logging.info(f"Transcribing mic with faster-whisper ({model_name}) on {DEVICE}...")
    segments, _info = _whisper_model(model_name).transcribe(wav_path, beam_size=5)
    results = []
    for segment in segments:
        results.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "speaker": speaker_name,
            }
        )
    return results


def diarize_loopback(wav_path, model_name="base"):
    # Use whisperx to transcribe and diarize loopback
    import whisperx

    logging.info(
        f"Transcribing and diarizing loopback with whisperx ({model_name}) on {DEVICE}..."
    )
    hf_token = os.environ.get("HF_TOKEN", False)

    audio = whisperx.load_audio(wav_path)
    result = _whisperx_model(model_name).transcribe(audio, batch_size=16)

    model_a, metadata = _align_model(result["language"])
    result = whisperx.align(
        result["segments"],
        model_a,
        metadata,
        audio,
        DEVICE,
        return_char_alignments=False,
    )

    diarize_segments = _diarization_pipeline(hf_token)(audio)

    result = whisperx.assign_word_speakers(diarize_segments, result)

    output = []
    for segment in result["segments"]:
        output.append(
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip(),
                "speaker": segment.get("speaker", "SPEAKER_UNKNOWN"),
            }
        )
    return output


app = FastAPI(title="Diarization Service")


@app.post("/diarize")
async def diarize(
    speaker_name: str = Form("You"),
    model: str = Form("base"),
    audio_mic: UploadFile | None = File(None),
    audio_loopback: UploadFile | None = File(None),
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
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit)

    uvicorn.run(app, host="127.0.0.1", port=8001)
