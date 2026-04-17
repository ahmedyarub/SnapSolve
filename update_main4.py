import re

with open('main.py', 'r') as f:
    content = f.read()

# Replace _end_multi_capture
end_multi_replacement = """
    def _end_multi_capture():
        global is_processing, is_multi_capturing, multi_capture_texts, llm_engine_instance, fallback_llm_engine_instance
        try:
            if not multi_capture_texts:
                if 'popup' in config.get('output_mode', ['popup']):
                    show_popup("No text captured in multi-capture mode.", auto_close=3000, opacity=config.get('popup_opacity', 0.8), is_result=False)
                is_multi_capturing = False
                update_multi_state(False)
                return

            combined_text = "\\n\\n".join(multi_capture_texts)
            print(f"Combined Text:\\n{combined_text}")

            def status_update(msg):
                if 'popup' in config.get('output_mode', ['popup']):
                    show_popup(msg, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

            show_headers = False
            fallback_model = active_profile.get('fallback_model', 'None')
            main_model = active_profile.get('model', 'gemini-2.5-flash-lite')
            prompt_id = active_profile.get('prompt_id', 'default')

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            sink = PopupSink(config, show_headers, main_model, fallback_model)

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
                text=combined_text
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
            print(f"Error during processing multi-capture: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
        finally:
            set_processing(False)
            is_multi_capturing = False
            multi_capture_texts = []
"""

content = re.sub(r'    def _end_multi_capture\(\):.*?multi_capture_texts = \[\]', end_multi_replacement.strip('\n'), content, flags=re.DOTALL)

with open('main.py', 'w') as f:
    f.write(content)
