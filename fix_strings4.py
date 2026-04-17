with open('main.py', 'r') as f:
    content = f.read()

content = content.replace("ScreenshotSource(ocr_engine_instance)", "ScreenshotSource()")
content = content.replace(
"""    ocr_type = active_profile.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))""",
"""    ocr_type = active_profile.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))
    else:
        ocr_engine_instance = NoOCREngine()

    if isinstance(active_source_instance, ScreenshotSource):
        active_source_instance.ocr_engine = ocr_engine_instance""")

with open('main.py', 'w') as f:
    f.write(content)
