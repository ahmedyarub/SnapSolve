with open('processor.py', 'r') as f:
    content = f.read()

old_cap = """def capture_and_process(coords, ocr_engine_instance=None, llm_engine_instance=None, status_callback=None):
    if not coords or len(coords) != 4:
        return "Error: Invalid coordinates. Please run coordinate selection again."

    if not ocr_engine_instance or not llm_engine_instance:
         return "Error: Engines not initialized properly."

    # Unpack coordinates (x1, y1, x2, y2)
    bbox = tuple(coords)

    if status_callback:
        status_callback("Capturing screen...")

    try:
        # Capture screen region
        img = ImageGrab.grab(bbox=bbox)
    except Exception as e:
        return f"Error capturing screen: {str(e)}"

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    temp_file_path = temp_file.name
    temp_file.close()

    try:
        # Save image to temporary file
        img.save(temp_file_path)

        extracted_text = None
        try:
            extracted_text = ocr_engine_instance.extract_text(temp_file_path, status_callback)
        except Exception as e:
            return str(e)"""

new_cap = """def capture_and_process(coords, model="gemini-2.5-flash-lite", llm_engine="gemini", ocr_engine="none", ollama_url="http://localhost:11434", google_genai_api_key="", ocr_engine_instance=None, llm_engine_instance=None, status_callback=None):
    if not coords or len(coords) != 4:
        return "Error: Invalid coordinates. Please run coordinate selection again."

    # Unpack coordinates (x1, y1, x2, y2)
    bbox = tuple(coords)

    if status_callback:
        status_callback("Capturing screen...")

    try:
        # Capture screen region
        img = ImageGrab.grab(bbox=bbox)
    except Exception as e:
        return f"Error capturing screen: {str(e)}"

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    temp_file_path = temp_file.name
    temp_file.close()

    try:
        # Save image to temporary file
        img.save(temp_file_path)

        # Setup OCR engine
        ocr = ocr_engine_instance
        if not ocr:
            if ocr_engine == "paddleocr":
                ocr = PaddleOCREngine()
            else:
                ocr = NoOCREngine()

        extracted_text = None
        try:
            extracted_text = ocr.extract_text(temp_file_path, status_callback)
        except Exception as e:
            return str(e)

        # Setup LLM engine
        llm = llm_engine_instance
        if not llm:
            if llm_engine == "ollama":
                llm = OllamaEngine(model, ollama_url)
            elif llm_engine == "google-genai":
                llm = GoogleGenAIEngine(model, google_genai_api_key)
            else:
                llm = GeminiCLIEngine(model)"""

content = content.replace(old_cap, new_cap)

content = content.replace(
    "ans = llm_engine_instance.generate_answer(prompt, temp_file_path, extracted_text, status_callback)",
    "ans = llm.generate_answer(prompt, temp_file_path, extracted_text, status_callback)"
)

with open('processor.py', 'w') as f:
    f.write(content)
