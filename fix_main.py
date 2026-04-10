with open('main.py', 'r') as f:
    content = f.read()

old_main = """    hotkeys = config.get('hotkeys', [])"""

new_main = """    # Initialize Engines (Only pre-init Ollama and PaddleOCR)
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
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'), status_callback=lambda msg: print(f"Init status: {msg}"))

    hotkeys = config.get('hotkeys', [])"""

content = content.replace(old_main, new_main)

with open('main.py', 'w') as f:
    f.write(content)
