with open('README.md', 'r') as f:
    content = f.read()

# Replace config options section
old_config = """*   `llm_engine`: Can be `"gemini"` or `"ollama"`.
*   `ocr_engine`: Can be `"none"` (to send image directly to the LLM) or `"paddleocr"` (to extract text locally before sending to the LLM).
*   `ollama_url`: The URL to your Ollama API."""

new_config = """*   `llm_engine`: Can be `"gemini"`, `"ollama"`, or `"google-genai"`.
*   `ocr_engine`: Can be `"none"` (to send image directly to the LLM) or `"paddleocr"` (to extract text locally before sending to the LLM).
*   `ollama_url`: The URL to your Ollama API.
*   `google_genai_api_key`: Your API key for the Google GenAI SDK (only needed if `llm_engine` is `"google-genai"`)."""
content = content.replace(old_config, new_config)

# Add Google GenAI as an option
old_options = """### Option 2: Local LLM with Ollama
1. Install [Ollama](https://ollama.com/).
2. Start your local Ollama server and pull a model (e.g., `ollama run llama3`)."""

new_options = """### Option 2: Local LLM with Ollama
1. Install [Ollama](https://ollama.com/).
2. Start your local Ollama server and pull a model (e.g., `ollama run llama3`).

### Option 3: Google GenAI Python SDK
Instead of the CLI, you can use the official Python SDK directly.
1. Make sure `google-genai` is installed (it's in `requirements.txt`).
2. Add your API key to `config.json` under `google_genai_api_key`."""
content = content.replace(old_options, new_options)

# Adjust Option 3 to Option 4
content = content.replace("### Option 3: Local OCR with PaddleOCR", "### Option 4: Local OCR with PaddleOCR")

# Add summary list of options
list_of_options = """## Supported Engines

**LLM Engines (`llm_engine`):**
*   `gemini` - Uses the Google Gemini CLI. Sends multimodal (image + text) directly or text-only if OCR is used.
*   `ollama` - Uses a local Ollama server. Can process both images and text-only depending on the model.
*   `google-genai` - Uses the official Python SDK for Google GenAI. Requires an API key. Supports both image and text inputs.

**OCR Engines (`ocr_engine`):**
*   `none` - Does not perform local OCR. The full image is sent directly to the LLM.
*   `paddleocr` - Uses local PaddleOCR to extract text from the image, sending only the extracted text to the LLM."""

content = content.replace("## Configuration", list_of_options + "\n\n## Configuration")

# Add missing config fields in the config.json example block
old_json = """"ollama_url": "http://localhost:11434"
}"""
new_json = """"ollama_url": "http://localhost:11434",
    "google_genai_api_key": ""
}"""
content = content.replace(old_json, new_json)

with open('README.md', 'w') as f:
    f.write(content)
