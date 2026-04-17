with open('main.py', 'r') as f:
    content = f.read()

# Remove global declaration in main, put it at top of main
content = content.replace('    global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance, session_manager', '')
content = content.replace('    global is_running, active_source_instance', '    global is_running, active_source_instance, ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance, session_manager')

with open('main.py', 'w') as f:
    f.write(content)
