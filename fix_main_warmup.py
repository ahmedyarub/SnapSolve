import re

with open('main.py', 'r') as f:
    content = f.read()

warmup_replacement = """    llm_type = active_profile.get('llm_engine', 'gemini')
    model = active_profile.get('model', 'gemini-2.5-flash-lite')
    fallback_model = active_profile.get('fallback_model', 'None')

    # Initialize Engines
    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'))
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine (with warmup)...")
            fallback_llm_engine_instance = OllamaEngine(fallback_model, config.get('ollama_url', 'http://localhost:11434'))
    elif llm_type == "google-genai":
        llm_engine_instance = GoogleGenAIEngine(model, config.get('google_genai_api_key', ''))
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GoogleGenAIEngine(fallback_model, config.get('google_genai_api_key', ''))
    else:
        llm_engine_instance = GeminiCLIEngine(model)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GeminiCLIEngine(fallback_model)

    # Perform Warmup: fallback first, then main if fallback fails or doesn't exist
    warmup_status_cb = lambda msg: print(f"Init status: {msg}")
    warmup_success = False
    if fallback_model and fallback_model != "None" and 'fallback_llm_engine_instance' in globals():
        warmup_success = fallback_llm_engine_instance.warmup(status_callback=warmup_status_cb)

    if not warmup_success and llm_engine_instance:
        llm_engine_instance.warmup(status_callback=warmup_status_cb)
"""

content = re.sub(
    r'    llm_type = active_profile.get\(\'llm_engine\', \'gemini\'\).*?            fallback_llm_engine_instance = GeminiCLIEngine\(fallback_model\)',
    warmup_replacement.strip('\n'),
    content,
    flags=re.DOTALL
)

with open('main.py', 'w') as f:
    f.write(content)
