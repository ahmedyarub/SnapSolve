with open('main.py', 'r') as f:
    content = f.read()

content = content.replace(
    "ollama_url=config.get('ollama_url', 'http://localhost:11434'),",
    "ollama_url=config.get('ollama_url', 'http://localhost:11434'),\n                google_genai_api_key=config.get('google_genai_api_key', ''),"
)

with open('main.py', 'w') as f:
    f.write(content)
