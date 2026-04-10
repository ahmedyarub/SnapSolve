with open('processor.py', 'r') as f:
    content = f.read()

# Replace PaddleOCREngine
old_paddle = """class PaddleOCREngine(OCREngine):
    def extract_text(self, image_path: str, status_callback=None) -> str:
        if status_callback:
            status_callback("Running PaddleOCR...")

        try:
            import warnings
            # Silence C++ logs
            os.environ['GLOG_minloglevel'] = '2'
            from paddleocr import PaddleOCR
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            start_time = time.time()
            ocr = PaddleOCR(
                lang='en',
                use_textline_orientation=False,
                use_doc_unwarping=False,
            )

            results = ocr.ocr(image_path)"""

new_paddle = """class PaddleOCREngine(OCREngine):
    def __init__(self, status_callback=None):
        if status_callback:
            status_callback("Initializing PaddleOCR...")
        try:
            import warnings
            # Silence C++ logs
            os.environ['GLOG_minloglevel'] = '2'
            from paddleocr import PaddleOCR
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            self.ocr = PaddleOCR(
                lang='en',
                use_textline_orientation=False,
                use_doc_unwarping=False,
            )

            # Warmup
            if os.path.exists("test_image.png"):
                if status_callback:
                    status_callback("Warming up PaddleOCR...")
                self.ocr.ocr("test_image.png")
            else:
                from PIL import Image
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                img = Image.new('RGB', (100, 100), color = 'white')
                img.save(temp_file.name)
                self.ocr.ocr(temp_file.name)
                os.remove(temp_file.name)

        except ImportError:
            raise Exception("Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine.")
        except Exception as e:
            import traceback
            print(f"Error during OCR initialization:\\n{traceback.format_exc()}")
            raise Exception(f"Error during OCR initialization: {str(e)}")

    def extract_text(self, image_path: str, status_callback=None) -> str:
        if status_callback:
            status_callback("Running PaddleOCR...")

        try:
            start_time = time.time()

            results = self.ocr.ocr(image_path)"""

content = content.replace(old_paddle, new_paddle)


# Replace capture_and_process signature and logic
old_cap = """def capture_and_process(coords, model="gemini-2.5-flash-lite", llm_engine="gemini", ocr_engine="none", ollama_url="http://localhost:11434", google_genai_api_key="", status_callback=None):
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
        ocr = None
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
        llm = None
        if llm_engine == "ollama":
            llm = OllamaEngine(model, ollama_url)
        elif llm_engine == "google-genai":
            llm = GoogleGenAIEngine(model, google_genai_api_key)
        else:
            llm = GeminiCLIEngine(model)"""

new_cap = """def capture_and_process(coords, ocr_engine_instance=None, llm_engine_instance=None, status_callback=None):
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

content = content.replace(old_cap, new_cap)

# Handle the generation call replacement in capture_and_process
content = content.replace("ans = llm.generate_answer(prompt, temp_file_path, extracted_text, status_callback)", "ans = llm_engine_instance.generate_answer(prompt, temp_file_path, extracted_text, status_callback)")

with open('processor.py', 'w') as f:
    f.write(content)
