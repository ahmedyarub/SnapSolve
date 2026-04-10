with open('main.py', 'r') as f:
    content = f.read()

old_init = """    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'))"""

new_init = """    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'), status_callback=lambda msg: print(f"Init status: {msg}"))"""

content = content.replace(old_init, new_init)

with open('main.py', 'w') as f:
    f.write(content)
