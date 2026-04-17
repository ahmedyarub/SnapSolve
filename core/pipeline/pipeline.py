import threading
from core.sources.base import Source
from core.llm.base import LLMEngine
from core.sinks.base import Sink

class ConcurrentSinkWrapper(Sink):
    def __init__(self, target_sink: Sink, main_finished_event: threading.Event,
                 main_started: list, fallback_started: list, main_success: list):
        self.target_sink = target_sink
        self.main_finished_event = main_finished_event
        self.main_started = main_started
        self.fallback_started = fallback_started
        self.main_success = main_success
        self.lock = threading.Lock()

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if not self.target_sink:
            return

        with self.lock:
            if is_main:
                self.main_started[0] = True
                self.target_sink.process_chunk(chunk, is_main=True, replace=False)
            else:
                if not self.main_started[0] and not self.main_success[0] and not self.main_finished_event.is_set():
                    self.fallback_started[0] = True
                    self.target_sink.process_chunk(chunk, is_main=False, replace=False)

    def force_replace(self):
        if self.target_sink and self.fallback_started[0]:
            self.target_sink.process_chunk("", is_main=True, replace=True)

def process_pipeline(
    source: Source,
    llm: LLMEngine,
    prompt_text: str,
    status_callback=None,
    session_manager=None,
    enable_stitching: bool = True,
    sink: Sink = None,
    fallback_llm: LLMEngine = None,
    coords=None,
    text=None
) -> str:
    extracted_text = None
    image_path = None
    is_image = False

    # 1. Text/Image Retrieval
    try:
        try:
            extracted_text = source.get_text(coords=coords, text=text, status_callback=status_callback)
        except ValueError as e:
            if llm.supports_images:
                is_image = True
                image_path = source.get_image(coords=coords, text=text)
            else:
                raise ValueError(f"Pipeline failed: Source could not provide text ({str(e)}), and LLM does not support images.")
    except Exception as e:
        return f"Error retrieving data from source: {str(e)}"

    # 2. Prompt Augmentation
    prompt = prompt_text
    if extracted_text:
        prompt = f"{prompt_text}: {extracted_text}"

    # 3. LLM Execution (with Fallback Concurrency)
    if not fallback_llm:
        if is_image:
            return llm.process_image(prompt, image_path, status_callback, session_manager, enable_stitching, sink, is_main=True)
        else:
            return llm.process_text(prompt, status_callback, session_manager, enable_stitching, sink, is_main=True)

    results = {}
    threads = []
    lock = threading.Lock()

    main_started = [False]
    fallback_started = [False]
    main_success = [False]
    main_finished = threading.Event()

    concurrent_sink = ConcurrentSinkWrapper(sink, main_finished, main_started, fallback_started, main_success) if sink else None

    def run_main():
        try:
            if is_image:
                ans = llm.process_image(prompt, image_path, status_callback, session_manager, enable_stitching, concurrent_sink, is_main=True)
            else:
                ans = llm.process_text(prompt, status_callback, session_manager, enable_stitching, concurrent_sink, is_main=True)

            with lock:
                if isinstance(ans, str) and ans.startswith("Error"):
                    results['main_error'] = ans
                else:
                    results['main'] = ans
                    main_success[0] = True
                    if concurrent_sink:
                        concurrent_sink.force_replace()
                        if not main_started[0]:
                            concurrent_sink.target_sink.process_chunk(ans, is_main=True, replace=False)

        except Exception as e:
            with lock:
                results['main_error'] = str(e)
        finally:
            main_finished.set()

    def run_fallback():
        try:
            if is_image:
                ans = fallback_llm.process_image(prompt, image_path, None, session_manager, enable_stitching, concurrent_sink, is_main=False)
            else:
                ans = fallback_llm.process_text(prompt, None, session_manager, enable_stitching, concurrent_sink, is_main=False)
            with lock:
                results['fallback'] = ans
        except Exception as e:
            with lock:
                results['fallback_error'] = str(e)

    main_thread = threading.Thread(target=run_main, daemon=True)
    fallback_thread = threading.Thread(target=run_fallback, daemon=True)

    main_thread.start()
    fallback_thread.start()

    main_thread.join()

    final_result = None

    if main_success[0] and 'main' in results:
        final_result = results['main']
    else:
        fallback_thread.join()
        if 'fallback' in results:
            final_result = results['fallback']
        elif 'main_error' in results:
            final_result = f"Error processing main: {results['main_error']}, Fallback error: {results.get('fallback_error', 'unknown')}"
        else:
            final_result = "Error processing with both models."

    if session_manager and final_result and not final_result.startswith("Error"):
        try:
            session_manager.append_interaction(prompt, image_path, final_result, extracted_text)
        except Exception as e:
            print(f"Failed to append to session manager: {e}")

    return final_result
