import os
import tempfile
import time
import threading
from .base import OCREngine


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

        except ImportError:
            raise ImportError(
                "Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine."
            )
        except Exception as e:
            import traceback

            print(f"Error during OCR initialization:\n{traceback.format_exc()}")
            raise RuntimeError(f"Error during OCR initialization: {str(e)}") from e

    def _parse_json_result(self, res, text_lines):
        data = res.json
        if "res" in data and "rec_texts" in data["res"]:
            for text, score in zip(data["res"]["rec_texts"], data["res"]["rec_scores"]):
                if score >= 0.5: text_lines.append(text)

    def _parse_list_result(self, res, text_lines):
        for line in res:
            text, confidence = line[1][0], line[1][1]
            if confidence >= 0.5: text_lines.append(text)

    def _parse_ocr_result(self, results):
        text_lines = []
        if results:
            for res in results:
                if not res: continue
                if hasattr(res, "json"): self._parse_json_result(res, text_lines)
                elif isinstance(res, list): self._parse_list_result(res, text_lines)
        return " ".join(text_lines) if text_lines else None

    def extract_text(self, image_path: str, status_callback=None, cancel_event: threading.Event = None) -> str:
        if cancel_event and cancel_event.is_set(): raise ValueError("OCR cancelled.")
        print("Using local PaddleOCR engine.")
        if status_callback: status_callback("Running PaddleOCR...")

        try:
            start_time = time.time()
            results = self.ocr.ocr(image_path)
            if cancel_event and cancel_event.is_set(): raise ValueError("OCR cancelled.")

            extracted_text = self._parse_ocr_result(results)

            if extracted_text: print(f"Extracted Text: {extracted_text}")
            else: print("PaddleOCR found no text.")

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"PaddleOCR took {elapsed_ms:.2f} ms")
            return extracted_text

        except ImportError:
            raise ImportError("Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine.")
        except Exception as e:
            if "cancelled" in str(e).lower(): raise
            import traceback
            print(f"Error during OCR execution:\n{traceback.format_exc()}")
            raise RuntimeError(f"Error during OCR execution: {str(e)}") from e
