import re

with open('main.py', 'r') as f:
    content = f.read()

# Fix 1: handle_text_submit using a temporary TextSource and passing correct prompt_text
text_submit_replacement = """
            from core.sources import TextSource
            temp_source = TextSource()

            result = process_pipeline(
                source=temp_source,
                llm=llm_engine_instance,
                prompt_text=active_prompt_text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get('enable_stitching', True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None,
                text=text
            )"""

content = re.sub(
    r'            result = process_pipeline\(\n                source=active_source_instance,\n                llm=llm_engine_instance,\n                prompt_text=text,.*?text=text\n            \)',
    text_submit_replacement.strip('\n'),
    content,
    flags=re.DOTALL
)

# Fix 2: handle_cycle_source losing OCR
cycle_replacement = """def handle_cycle_source(config):
    global active_source_instance, ocr_engine_instance
    from core.sources import ScreenshotSource, TextSource
    if isinstance(active_source_instance, ScreenshotSource):
        active_source_instance = TextSource()
    else:
        active_source_instance = ScreenshotSource(ocr_engine_instance)"""
content = re.sub(
    r'def handle_cycle_source\(config\):\n    global active_source_instance\n    if isinstance\(active_source_instance, ScreenshotSource\):\n        active_source_instance = TextSource\(\)\n    else:\n        active_source_instance = ScreenshotSource\(None\)',
    cycle_replacement,
    content,
    flags=re.DOTALL
)

with open('main.py', 'w') as f:
    f.write(content)
