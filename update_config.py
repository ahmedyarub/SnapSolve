with open('config.py', 'r') as f:
    content = f.read()

# Update the default config dictionary
content = content.replace(
    "'ollama_url': 'http://localhost:11434'",
    "'ollama_url': 'http://localhost:11434',\n        'google_genai_api_key': ''"
)

# Update llm_engine choices
content = content.replace(
    "choices=['gemini', 'ollama']",
    "choices=['gemini', 'ollama', 'google-genai']"
)

content = content.replace(
    "parser.add_argument('--ollama-url', type=str, help='Ollama API URL (default: http://localhost:11434)')",
    "parser.add_argument('--ollama-url', type=str, help='Ollama API URL (default: http://localhost:11434)')\n    parser.add_argument('--google-genai-api-key', type=str, help='Google GenAI API Key')"
)

content = content.replace(
    "if args.ollama_url:\n        config['ollama_url'] = args.ollama_url\n\n    return config",
    "if args.ollama_url:\n        config['ollama_url'] = args.ollama_url\n\n    if args.google_genai_api_key:\n        config['google_genai_api_key'] = args.google_genai_api_key\n\n    return config"
)

with open('config.py', 'w') as f:
    f.write(content)
