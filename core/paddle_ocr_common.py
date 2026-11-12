"""PaddleOCR setup and result parsing shared by the local engine and the OCR service.

Kept free of app imports so ``services/ocr_service.py`` can load it without
pulling in the Qt/audio stack.
"""

import os
import warnings

MIN_CONFIDENCE = 0.5


def create_paddle_ocr():
    """Builds the PaddleOCR pipeline used for screenshots.

    PaddleOCR picks the GPU automatically when paddlepaddle-gpu sees CUDA, and
    falls back to the CPU otherwise. The document orientation, unwarping and
    text-line orientation models are turned off: screen captures are always
    upright and flat, and each of those models adds a GPU pass per image.
    """
    os.environ["GLOG_minloglevel"] = "2"  # noqa: SIM112  glog's own spelling
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _lines_from_json(data) -> list[str]:
    res = data.get("res", {})
    texts = res.get("rec_texts")
    if not texts:
        return []
    return [
        text
        for text, score in zip(texts, res["rec_scores"], strict=False)
        if score >= MIN_CONFIDENCE
    ]


def _lines_from_legacy_list(res) -> list[str]:
    return [line[1][0] for line in res if line[1][1] >= MIN_CONFIDENCE]


def parse_ocr_results(results) -> list[str]:
    """Returns the recognised lines above the confidence threshold."""
    lines: list[str] = []
    for res in results or []:
        if not res:
            continue
        if hasattr(res, "json"):
            lines.extend(_lines_from_json(res.json))
        elif isinstance(res, list):
            lines.extend(_lines_from_legacy_list(res))
    return lines
