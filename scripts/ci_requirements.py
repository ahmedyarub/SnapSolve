"""Print requirements.lock without the GPU / ML-model stack, for CI.

The unit tests never load PaddleOCR, Whisper, Torch or the CUDA wheels, and
paddlepaddle-gpu is not on PyPI at all, so CI installs everything else at the
locked versions:  python scripts/ci_requirements.py > ci-requirements.txt
"""

import re
from pathlib import Path

LOCK = Path(__file__).resolve().parent.parent / "requirements.lock"

# Packages (and families) the unit tests do not need on a CPU-only runner.
GPU_STACK = re.compile(
    r"^(paddlepaddle-gpu|paddleocr|paddlex|nvidia-.*|torch|torchvision|torchaudio"
    r"|ctranslate2|faster-whisper|onnxruntime(-gpu)?|sentence-transformers"
    r"|transformers|tokenizers|safetensors|huggingface-hub|triton)==",
    re.IGNORECASE,
)


def main() -> None:
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and not GPU_STACK.match(line):
            print(line)


if __name__ == "__main__":
    main()
