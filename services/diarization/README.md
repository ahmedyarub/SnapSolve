# Diarization Service

This service provides offline speaker diarization using `whisperx` and `faster-whisper`.
It runs independently of the main SnapSolve application to prevent dependency conflicts, specifically with `faster-whisper` and `torchaudio`.

## Setup Instructions

1. Navigate to this directory:

    ```bash
    cd services/diarization
    ```

2. Create a virtual environment:

    ```bash
    python -m venv .venv
    ```

3. Activate the virtual environment:
    - On Windows:
        ```bash
        .venv\Scripts\activate
        ```
    - On macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```

4. Install the requirements:
    ```bash
    pip install -r requirements.txt
    ```

Once installed, you must start the service manually. Make sure to set your `HF_TOKEN` environment variable first if you are using diarization, as Pyannote requires it:

- On Windows (Command Prompt):
    ```cmd
    set HF_TOKEN=your_huggingface_token
    uvicorn diarization_service:app --host 127.0.0.1 --port 8001
    ```
- On macOS/Linux/PowerShell:
    ```bash
    export HF_TOKEN="your_huggingface_token"
    uvicorn diarization_service:app --host 127.0.0.1 --port 8001
    ```

When "Post-Recording Speaker Diarization" is enabled in the SnapSolve UI, the main application will send an HTTP POST request to `http://127.0.0.1:8001/diarize` containing the captured audio.

### Troubleshooting

**"CUDA not available. Falling back to CPU (int8)."**
By default, `pip install -r requirements.txt` on Windows installs the CPU-only version of PyTorch. To enable hardware acceleration and use your NVIDIA GPU, uninstall the CPU version and install the CUDA version:

```bash
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129
```

**"Could not download Pipeline from pyannote/speaker-diarization-community-1" or "403 Client Error"**
This happens because the diarization models are gated. To fix this:

1. Create an account on Hugging Face.
2. Go to [pyannote/speaker-diarization-community-1](https://hf.co/pyannote/speaker-diarization-community-1) and accept the user conditions.
3. Go to [pyannote/segmentation-community-3.0](https://huggingface.co/pyannote/segmentation-community-3.0) and accept the conditions there too.
4. Go to [Hugging Face Tokens](https://hf.co/settings/tokens) and generate an access token.
5. Set it as the `HF_TOKEN` environment variable before running `uvicorn`.

