"""Reports whether each GPU-capable backend in this environment can use the NVIDIA card.

Run after installing or upgrading packages:
    python scripts/check_gpu.py

Exits non-zero if PaddleOCR or CTranslate2 (faster-whisper) cannot reach CUDA,
since those are the backends the app relies on the GPU for.
"""

import os
import subprocess
import sys

os.environ.setdefault("GLOG_minloglevel", "2")

REQUIRED = ("paddle", "ctranslate2")


def _nvidia_smi() -> str:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,compute_cap,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return out.stdout.strip() or out.stderr.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"nvidia-smi unavailable: {e}"


def _check_paddle():
    import paddle

    ok = paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
    detail = f"paddle {paddle.__version__}, CUDA {paddle.version.cuda()}, cuDNN {paddle.version.cudnn()}"
    if ok:
        x = paddle.to_tensor([1.0, 2.0], place=paddle.CUDAPlace(0))
        ok = abs(float((x * 2).sum()) - 6.0) < 1e-6
    return ok, detail


def _check_ctranslate2():
    import ctranslate2

    count = ctranslate2.get_cuda_device_count()
    types = sorted(ctranslate2.get_supported_compute_types("cuda")) if count else []
    return (
        count > 0 and "float16" in types,
        f"ctranslate2 {ctranslate2.__version__}, compute types {types}",
    )


def _check_torch():
    import torch

    ok = torch.cuda.is_available()
    return ok, f"torch {torch.__version__} (CUDA build: {torch.version.cuda})"


def _check_onnxruntime():
    import onnxruntime

    providers = onnxruntime.get_available_providers()
    return (
        "CUDAExecutionProvider" in providers,
        f"onnxruntime {onnxruntime.__version__}, {providers}",
    )


# Paddle goes last. In a bare interpreter, importing it first makes later torch
# and ctranslate2 imports fail with WinError 127. The app is not affected
# because PyQt6 WebEngine is loaded first; _check_app_import_order covers that.
CHECKS = {
    "torch": ("local embeddings", _check_torch),
    "ctranslate2": ("faster-whisper", _check_ctranslate2),
    "onnxruntime": ("Piper TTS", _check_onnxruntime),
    "paddle": ("PaddleOCR", _check_paddle),
}


def _check_app_import_order() -> tuple[bool, str]:
    """Imports in the app's order (Qt WebEngine, PaddleOCR, then torch) in a fresh interpreter.

    Loading torch *before* PaddleOCR with Qt WebEngine present segfaults, so the
    app must keep this order.
    """
    code = "import PyQt6.QtWebEngineWidgets, paddleocr, torch; print('ok')"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300
    )
    ok = out.returncode == 0 and out.stdout.strip().endswith("ok")
    if ok:
        return ok, "Qt WebEngine, PaddleOCR, torch in one process"
    return (
        ok,
        f"exit {out.returncode}: {(out.stderr.strip().splitlines() or ['no output'])[-1]}",
    )


def main() -> int:
    print(f"GPU: {_nvidia_smi()}")
    failed = []
    for key, (used_by, check) in CHECKS.items():
        try:
            ok, detail = check()
        except Exception as e:  # report any import/runtime failure for this backend
            ok, detail = False, f"{type(e).__name__}: {e}"
        mark = "GPU" if ok else "CPU"
        need = "required" if key in REQUIRED else "optional"
        print(f"[{mark}] {key:<12} ({used_by}, {need}) {detail}")
        if not ok and key in REQUIRED:
            failed.append(key)
    ok, detail = _check_app_import_order()
    print(f"[{'OK ' if ok else 'BAD'}] import order ({detail})")
    if not ok:
        failed.append("import order")
    if failed:
        print(f"FAIL: {', '.join(failed)}")
        return 1
    print("OK: required GPU backends use CUDA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
