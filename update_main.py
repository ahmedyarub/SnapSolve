import re

with open('main.py', 'r') as f:
    content = f.read()

# 1. Update imports
content = re.sub(
    r'from core\.processor import capture_and_process, PaddleOCREngine, OllamaEngine',
    'from core.pipeline import process_pipeline\nfrom core.sinks import PopupSink\nfrom core.sources.ocr import PaddleOCREngine, NoOCREngine\nfrom core.llm import OllamaEngine, GeminiCLIEngine, GoogleGenAIEngine',
    content
)
content = re.sub(
    r'from core\.source import ImageSource, TextSource',
    'from core.sources import ScreenshotSource, TextSource',
    content
)

# 2. Update set_active_source_ui check and source initializations
content = re.sub(
    r'isinstance\(active_source_instance, ImageSource\)',
    'isinstance(active_source_instance, ScreenshotSource)',
    content
)
content = re.sub(r'active_source_instance = ImageSource\(\)', 'active_source_instance = ScreenshotSource(ocr_engine_instance)', content)
content = re.sub(r'active_source_instance = TextSource\(\)', 'active_source_instance = TextSource()', content)


with open('main.py', 'w') as f:
    f.write(content)
