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
            raise Exception(
                "Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine."
            )
        except Exception as e:
            import traceback

            print(f"Error during OCR initialization:\n{traceback.format_exc()}")
            raise Exception(f"Error during OCR initialization: {str(e)}")

    def extract_text(
        self,
        image_path: str,
        status_callback=None,
        cancel_event: threading.Event = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            raise ValueError("OCR cancelled.")

        print("Using local PaddleOCR engine.")
        if status_callback:
            status_callback("Running PaddleOCR...")

        try:
            start_time = time.time()

            results = self.ocr.ocr(image_path)

            if cancel_event and cancel_event.is_set():
                raise ValueError("OCR cancelled.")

            text_lines = []
            if results:
                for res in results:
                    if not res:
                        continue
                    if hasattr(res, "json"):
                        data = res.json
                        if "res" in data and "rec_texts" in data["res"]:
                            texts = data["res"]["rec_texts"]
                            scores = data["res"]["rec_scores"]

                            for text, score in zip(texts, scores):
                                if score >= 0.5:
                                    text_lines.append(text)

                    elif isinstance(res, list):
                        for line in res:
                            text = line[1][0]
                            confidence = line[1][1]
                            if confidence >= 0.5:
                                text_lines.append(text)

            extracted_text = None
            if text_lines:
                extracted_text = " ".join(text_lines)
                print(f"Extracted Text: {extracted_text}")
            else:
                print("PaddleOCR found no text.")

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"PaddleOCR took {elapsed_ms:.2f} ms")

            return extracted_text

        except ImportError:
            raise Exception(
                "Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine."
            )
        except Exception as e:
            if "cancelled" in str(e).lower():
                raise
            import traceback

            print(f"Error during OCR execution:\n{traceback.format_exc()}")
            raise Exception(f"Error during OCR execution: {str(e)}")
