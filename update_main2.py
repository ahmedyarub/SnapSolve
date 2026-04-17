import re

with open('main.py', 'r') as f:
    content = f.read()

# Replace _process function in handle_text_submit
process_text_replacement = """
    def _process():
        try:
            global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance, active_source_instance

            show_headers = False
            fallback_model = active_profile.get('fallback_model', 'None')
            main_model = active_profile.get('model', 'gemini-2.5-flash-lite')
            prompt_id = active_profile.get('prompt_id', 'default')

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            sink = PopupSink(config, show_headers, main_model, fallback_model)

            result = process_pipeline(
                source=active_source_instance,
                llm=llm_engine_instance,
                prompt_text=text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get('enable_stitching', True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None,
                text=text
            )
            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if sink.accumulated_fallback and len(sink.accumulated_result) == 1:
                    final_result = f"## Fallback Model ({fallback_model})\\n\\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\\n\\n{result}"

            output_result(final_result, config.get('output_mode'), config.get('voice_id'),
                          auto_close=config.get('auto_close_results', False), opacity=config.get('popup_opacity', 0.8),
                          fallback_language=config.get('fallback_language', 'python'))
        except Exception as e:
            print(f"Error during processing text input: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
        finally:
            set_processing(False)
"""
content = re.sub(r'    def _process\(\):.*?finally:\n            set_processing\(False\)', process_text_replacement.strip('\n'), content, flags=re.DOTALL)


# Replace _capture function in handle_capture
process_capture_replacement = """
    def _capture():
        try:
            global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance, active_source_instance

            show_headers = False
            fallback_model = active_profile.get('fallback_model', 'None')
            main_model = active_profile.get('model', 'gemini-2.5-flash-lite')
            prompt_id = active_profile.get('prompt_id', 'default')

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            sink = PopupSink(config, show_headers, main_model, fallback_model)

            result = process_pipeline(
                source=active_source_instance,
                llm=llm_engine_instance,
                prompt_text=active_prompt_text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get('enable_stitching', True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None,
                coords=config.get('coordinates')
            )
            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if sink.accumulated_fallback and len(sink.accumulated_result) == 1:
                    final_result = f"## Fallback Model ({fallback_model})\\n\\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\\n\\n{result}"

            output_result(final_result, config.get('output_mode'), config.get('voice_id'),
                          auto_close=config.get('auto_close_results', False), opacity=config.get('popup_opacity', 0.8),
                          fallback_language=config.get('fallback_language', 'python'))
        except Exception as e:
            print(f"Error during processing: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
        finally:
            set_processing(False)
"""
content = re.sub(r'    def _capture\(\):.*?finally:\n            set_processing\(False\)', process_capture_replacement.strip('\n'), content, flags=re.DOTALL)

with open('main.py', 'w') as f:
    f.write(content)
