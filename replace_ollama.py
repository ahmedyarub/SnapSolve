with open('processor.py', 'r') as f:
    content = f.read()

old_ollama = """class OllamaEngine(LLMEngine):
    def __init__(self, model: str, ollama_url: str):
        super().__init__(model)
        self.ollama_url = ollama_url

    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None) -> str:"""

new_ollama = """class OllamaEngine(LLMEngine):
    def __init__(self, model: str, ollama_url: str, status_callback=None):
        super().__init__(model)
        self.ollama_url = ollama_url

        # Warmup
        if status_callback:
            status_callback("Warming up Ollama (loading model into memory)...")
        try:
            payload = {
                "model": self.model,
                "prompt": "What is the largest country in the world?",
                "stream": False
            }
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                # Just read the response to ensure it completed
                _ = response.read()
            if status_callback:
                status_callback("Ollama warmup complete.")
        except Exception as e:
            if status_callback:
                status_callback(f"Ollama warmup failed: {str(e)}")
            print(f"Ollama warmup failed: {str(e)}")

    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None) -> str:"""

content = content.replace(old_ollama, new_ollama)

with open('processor.py', 'w') as f:
    f.write(content)
