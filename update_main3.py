import re

with open('main.py', 'r') as f:
    content = f.read()

# Replace multi capture extraction part
multi_ext_replacement = """            import tempfile
            from PIL import ImageGrab
            import os
            from core.sources import ScreenshotSource

            status_update("Capturing screen...")

            ocr = ocr_engine_instance
            if not ocr:
                from core.sources.ocr import PaddleOCREngine, NoOCREngine
                if ocr_type == "paddleocr":
                    ocr = PaddleOCREngine()
                else:
                    ocr = NoOCREngine()

            temp_source = ScreenshotSource(ocr)
            extracted_text = None
            try:
                extracted_text = temp_source.get_text(coords=coords, status_callback=status_update)
            except Exception as e:
                status_update(f"Error during OCR: {str(e)}")
            finally:
                temp_source.cleanup_all()"""

content = re.sub(r'            import tempfile\n            from PIL import ImageGrab\n            import os\n\n            status_update\("Capturing screen..."\).*?except OSError:\n                        pass', multi_ext_replacement.strip('\n'), content, flags=re.DOTALL)

with open('main.py', 'w') as f:
    f.write(content)
