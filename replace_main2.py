with open('main.py', 'r') as f:
    content = f.read()

old_init = """    # Initialize Engines
    print("Initializing engines...")
    global ocr_engine_instance, llm_engine_instance
    ocr_type = config.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))
    else:
        ocr_engine_instance = NoOCREngine()

    llm_type = config.get('llm_engine', 'gemini')
    model = config.get('model', 'gemini-2.5-flash-lite')
    if llm_type == "ollama":
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'))
    elif llm_type == "google-genai":
        llm_engine_instance = GoogleGenAIEngine(model, config.get('google_genai_api_key', ''))
    else:
        llm_engine_instance = GeminiCLIEngine(model)
    print("Engines initialized.")"""

new_init = """    # Initialize Engines (Only pre-init Ollama and PaddleOCR)
    print("Checking engine pre-initialization...")
    global ocr_engine_instance, llm_engine_instance
    ocr_type = config.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))

    llm_type = config.get('llm_engine', 'gemini')
    model = config.get('model', 'gemini-2.5-flash-lite')
    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'))"""

content = content.replace(old_init, new_init)


old_call = """            global ocr_engine_instance, llm_engine_instance
            result = capture_and_process(
                config.get('coordinates'),
                ocr_engine_instance=ocr_engine_instance,
                llm_engine_instance=llm_engine_instance,
                status_callback=status_update
            )"""

new_call = """            global ocr_engine_instance, llm_engine_instance
            result = capture_and_process(
                config.get('coordinates'),
                model=config.get('model', 'gemini-2.5-flash-lite'),
                llm_engine=config.get('llm_engine', 'gemini'),
                ocr_engine=config.get('ocr_engine', 'none'),
                ollama_url=config.get('ollama_url', 'http://localhost:11434'),
                google_genai_api_key=config.get('google_genai_api_key', ''),
                ocr_engine_instance=ocr_engine_instance,
                llm_engine_instance=llm_engine_instance,
                status_callback=status_update
            )"""
content = content.replace(old_call, new_call)

with open('main.py', 'w') as f:
    f.write(content)
