import logging
import os
import threading
import time

import numpy as np

from core.paddle_ocr_common import create_paddle_ocr, parse_ocr_results

from .base import OCREngine
from .exceptions import (
    OCRCancelledError,
    OCRDependencyError,
    OCRExecutionError,
    OCRInitializationError,
)

logger = logging.getLogger(__name__)

_WARMUP_IMAGE = "test_image.png"


class LocalPaddleOCREngine(OCREngine):
    def __init__(self, status_callback=None, warmup=True):
        self.ocr = None
        if status_callback:
            status_callback("Initializing PaddleOCR...")
        try:
            self.ocr = create_paddle_ocr()
            if warmup:
                self._warmup(status_callback)
        except (OSError, RuntimeError) as e:
            logger.exception("Error during OCR initialization")
            raise OCRInitializationError(
                f"Error during OCR initialization: {e!s}"
            ) from e
        except ImportError as e:
            raise OCRDependencyError(
                "Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine."
            ) from e

    def _warmup(self, status_callback=None):
        """Runs one inference so the first real capture doesn't pay for model/CUDA init."""
        if status_callback:
            status_callback("Warming up PaddleOCR...")
        if os.path.exists(_WARMUP_IMAGE):
            self.ocr.ocr(_WARMUP_IMAGE)
        else:
            self.ocr.ocr(np.full((100, 100, 3), 255, dtype=np.uint8))

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None):
        """Check if operation is canceled."""
        if cancel_event and cancel_event.is_set():
            raise OCRCancelledError("OCR cancelled.")

    def extract_text(
        self,
        image_path: str,
        status_callback=None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        self._check_cancelled(cancel_event)

        logger.debug("Using local PaddleOCR engine.")
        if status_callback:
            status_callback("Running PaddleOCR...")

        try:
            start_time = time.perf_counter()
            results = self.ocr.ocr(image_path)
            self._check_cancelled(cancel_event)

            extracted_text = " ".join(parse_ocr_results(results))
            logger.info("PaddleOCR extracted %d characters", len(extracted_text))
            logger.info(
                "PaddleOCR took %.0f ms", (time.perf_counter() - start_time) * 1000
            )
            return extracted_text

        except (OSError, RuntimeError, ValueError, OCRCancelledError) as e:
            logger.exception("Error during OCR execution")
            raise OCRExecutionError(f"Error during OCR execution: {e!s}") from e
