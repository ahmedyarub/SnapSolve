import re

with open('main.py', 'r') as f:
    content = f.read()

warmup_replacement = """    llm_type = active_profile.get('llm_engine', 'gemini')
    model = active_profile.get('model', 'gemini-2.5-flash-lite')
    fallback_model = active_profile.get('fallback_model', 'None')

    # Initialize Engines
    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine (with warmup)...")
            fallback_llm_engine_instance = OllamaEngine(fallback_model,
                                                        config.get('ollama_url', 'http://localhost:11434'),
                                                        status_callback=lambda msg: print(f"Init status: {msg}"))
            llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'))
        else:
            llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'),
                                           status_callback=lambda msg: print(f"Init status: {msg}"))
    elif llm_type == "google-genai":
        llm_engine_instance = GoogleGenAIEngine(model, config.get('google_genai_api_key', ''))
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GoogleGenAIEngine(fallback_model, config.get('google_genai_api_key', ''))
    else:
        llm_engine_instance = GeminiCLIEngine(model)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GeminiCLIEngine(fallback_model)"""

content = re.sub(r'    llm_type = active_profile.get\(\'llm_engine\', \'gemini\'\)\n    model = active_profile.get\(\'model\', \'gemini-2.5-flash-lite\'\)\n    fallback_model = active_profile.get\(\'fallback_model\', \'None\'\)\n.*?status_callback=lambda msg: print\(f"Init status: \{msg\}"\)\)', warmup_replacement, content, flags=re.DOTALL)

with open('main.py', 'w') as f:
    f.write(content)
