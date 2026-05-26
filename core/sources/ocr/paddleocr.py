import os
import tempfile
import time
import threading
from typing import Optional
from .base import OCREngine
from .exceptions import (
    OCRInitializationError,
    OCRDependencyError,
    OCRCancelledError,
    OCRExecutionError,
)


class LocalPaddleOCREngine(OCREngine):
    def __init__(self, status_callback=None, warmup=True):
        self.ocr = None
        if status_callback:
            status_callback("Initializing PaddleOCR...")
        try:
            import warnings

            # Silence C++ logs
            os.environ["GLOG_minloglevel"] = "2"
            from paddleocr import PaddleOCR

            warnings.filterwarnings("ignore", category=DeprecationWarning)

            self.ocr = PaddleOCR(
                lang="en",
                use_textline_orientation=False,
                use_doc_unwarping=False,
            )

            # Warmup
            if warmup:
                self._warmup(status_callback)

        except (OSError, RuntimeError) as e:
            import traceback

            print(f"Error during OCR initialization:\n{traceback.format_exc()}")
            raise OCRInitializationError(
                f"Error during OCR initialization: {str(e)}"
            ) from e
        except ImportError:
            raise OCRDependencyError(
                "Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine."
            )

    def _warmup(self, status_callback=None):
        """Warm up the OCR engine."""
        if os.path.exists("test_image.png"):
            if status_callback:
                status_callback("Warming up PaddleOCR...")
            self.ocr.ocr("test_image.png")
        else:
            from PIL import Image

            temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img = Image.new("RGB", (100, 100), color="white")
            img.save(temp_file.name)
            self.ocr.ocr(temp_file.name)

    @staticmethod
    def _check_cancelled(cancel_event: Optional[threading.Event]):
        """Check if operation is canceled."""
        if cancel_event and cancel_event.is_set():
            raise OCRCancelledError("OCR cancelled.")

    @staticmethod
    def _process_json_result(data):
        """Process JSON result format."""
        text_lines = []
        if "res" in data and "rec_texts" in data["res"]:
            texts = data["res"]["rec_texts"]
            scores = data["res"]["rec_scores"]

            for text, score in zip(texts, scores):
                if score >= 0.5:
                    text_lines.append(text)
        return text_lines

    @staticmethod
    def _process_list_result(res):
        """Process list result format."""
        text_lines = []
        for line in res:
            text = line[1][0]
            confidence = line[1][1]
            if confidence >= 0.5:
                text_lines.append(text)
        return text_lines

    def _process_ocr_results(self, results):
        """Process OCR results and extract text lines."""
        text_lines = []
        if not results:
            return text_lines

        for res in results:
            if not res:
                continue

            if hasattr(res, "json"):
                data = res.json
                text_lines.extend(self._process_json_result(data))
            elif isinstance(res, list):
                text_lines.extend(self._process_list_result(res))

        return text_lines

    @staticmethod
    def _extract_text_from_results(text_lines):
        """Extract final text from text lines."""
        if text_lines:
            extracted_text = " ".join(text_lines)
            print(f"Extracted Text: {extracted_text}")
            return extracted_text
        else:
            print("PaddleOCR found no text.")
            return ""

    def extract_text(
        self,
        image_path: str,
        status_callback=None,
        cancel_event: Optional[threading.Event] = None,
    ) -> str:
        self._check_cancelled(cancel_event)

        print("Using local PaddleOCR engine.")
        if status_callback:
            status_callback("Running PaddleOCR...")

        try:
            start_time = time.time()

            results = self.ocr.ocr(image_path)

            self._check_cancelled(cancel_event)

            text_lines = self._process_ocr_results(results)
            extracted_text = self._extract_text_from_results(text_lines)

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"PaddleOCR took {elapsed_ms:.2f} ms")

            return extracted_text

        except (OSError, RuntimeError, ValueError, OCRCancelledError) as e:
            import traceback

            print(f"Error during OCR execution:\n{traceback.format_exc()}")
            raise OCRExecutionError(f"Error during OCR execution: {str(e)}") from e
