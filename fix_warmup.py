import re

with open('core/llm/base.py', 'r') as f:
    content = f.read()

# Add warmup abstraction
if 'def warmup(' not in content:
    content = content.replace(
        '    def supports_images(self) -> bool:\n        pass',
        '    def supports_images(self) -> bool:\n        pass\n\n    @abc.abstractmethod\n    def warmup(self, status_callback=None) -> bool:\n        """Warms up the engine. Returns True if successful."""\n        pass'
    )
    with open('core/llm/base.py', 'w') as f:
        f.write(content)

with open('core/llm/ollama.py', 'r') as f:
    content = f.read()

# Refactor Ollama warmup into a method
if 'def warmup(' not in content:
    content = re.sub(
        r'        # Warmup.*?print\(f"Ollama warmup failed: \{str\(e\)\}"\)',
        '',
        content,
        flags=re.DOTALL
    )

    warmup_method = """
    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Ollama (loading model into memory)...")
        try:
            payload = {
                "model": self.model,
                "prompt": "Hello",
                "stream": False
            }
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                _ = response.read()
            if status_callback:
                status_callback("Ollama warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Ollama warmup failed: {str(e)}")
            print(f"Ollama warmup failed: {str(e)}")
            return False
            """
    content = content.replace('    @property\n    def supports_images', warmup_method.strip('\n') + '\n\n    @property\n    def supports_images')
    with open('core/llm/ollama.py', 'w') as f:
        f.write(content)

with open('core/llm/gemini_cli.py', 'r') as f:
    content = f.read()
if 'def warmup(' not in content:
    warmup_method = """
    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Gemini CLI...")
        try:
            gemini_cmd = shutil.which("gemini")
            if not gemini_cmd:
                return False
            cmd_args = [gemini_cmd, "-p", '"Hello"', "-o", "json", "-m", self.model]
            subprocess.run(cmd_args, capture_output=True, text=True, check=True)
            if status_callback:
                status_callback("Gemini CLI warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Gemini CLI warmup failed: {str(e)}")
            return False
            """
    content = content.replace('    @property\n    def supports_images', warmup_method.strip('\n') + '\n\n    @property\n    def supports_images')
    with open('core/llm/gemini_cli.py', 'w') as f:
        f.write(content)

with open('core/llm/google_genai.py', 'r') as f:
    content = f.read()
if 'def warmup(' not in content:
    warmup_method = """
    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Google GenAI...")
        if not self.api_key:
            return False
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.api_key)
            contents = [types.Content(role="user", parts=[types.Part.from_text(text="Hello")])]
            response_stream = client.models.generate_content_stream(model=self.model, contents=contents)
            for chunk in response_stream:
                pass # Just consume it
            if status_callback:
                status_callback("Google GenAI warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Google GenAI warmup failed: {str(e)}")
            return False
            """
    content = content.replace('    @property\n    def supports_images', warmup_method.strip('\n') + '\n\n    @property\n    def supports_images')
    with open('core/llm/google_genai.py', 'w') as f:
        f.write(content)
