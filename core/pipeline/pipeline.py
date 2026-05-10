import threading
import time
from core.sources.base import Source
from core.llm.base import LLMEngine
from core.sinks.base import Sink

PIPELINE_CANCELLED_MSG = "Pipeline cancelled."


class ConcurrentSinkWrapper(Sink):
    def __init__(
        self,
        target_sink: Sink,
        main_finished_event: threading.Event,
        main_started: list,
        fallback_started: list,
        main_success: list,
        cancel_event: threading.Event = None,
    ):
        super().__init__(cancel_event)
        self.target_sink = target_sink
        self.main_finished_event = main_finished_event
        self.main_started = main_started
        self.fallback_started = fallback_started
        self.main_success = main_success
        self.lock = threading.Lock()

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if not self.target_sink or self.cancel_event.is_set():
            return

        with self.lock:
            if is_main:
                self.main_started[0] = True
                self.target_sink.process_chunk(chunk, is_main=True, replace=False)
            else:
                if (
                    not self.main_started[0]
                    and not self.main_success[0]
                    and not self.main_finished_event.is_set()
                ):
                    self.fallback_started[0] = True
                    self.target_sink.process_chunk(chunk, is_main=False, replace=False)

    def force_replace(self):
        if self.target_sink and self.fallback_started[0]:
            self.target_sink.process_chunk("", is_main=True, replace=True)


def _retrieve_source_data(source, llm, coords, text, status_callback, cancel_event):
    extracted_text, image_path, is_image = None, None, False
    try:
        if hasattr(source, "get_text") and "cancel_event" in source.get_text.__code__.co_varnames:
            extracted_text = source.get_text(coords=coords, text=text, status_callback=status_callback, cancel_event=cancel_event)
        else:
            extracted_text = source.get_text(coords=coords, text=text, status_callback=status_callback)
        print(f"Retrieved text from source: {extracted_text}")
    except ValueError as e:
        if llm.supports_images:
            is_image = True
            if hasattr(source, "get_image") and "cancel_event" in source.get_image.__code__.co_varnames:
                image_path = source.get_image(coords=coords, text=text, cancel_event=cancel_event)
            else:
                image_path = source.get_image(coords=coords, text=text)
            print(f"Retrieved image from source: {image_path}")
        else:
            raise ValueError(f"Pipeline failed: Source could not provide text ({str(e)}), and LLM does not support images.")
    return extracted_text, image_path, is_image

def _execute_single_llm(llm, prompt, image_path, is_image, status_callback, enable_stitching, sink, cancel_event, is_main=True):
    if is_image:
        if "cancel_event" in llm.process_image.__code__.co_varnames:
            return llm.process_image(prompt, image_path, status_callback, enable_stitching, sink, is_main=is_main, cancel_event=cancel_event)
        return llm.process_image(prompt, image_path, status_callback, enable_stitching, sink, is_main=is_main)
    else:
        if "cancel_event" in llm.process_text.__code__.co_varnames:
            return llm.process_text(prompt, status_callback, enable_stitching, sink, is_main=is_main, cancel_event=cancel_event)
        return llm.process_text(prompt, status_callback, enable_stitching, sink, is_main=is_main)

def _handle_main_result(results, main_success, ans, concurrent_sink, main_started):
    if isinstance(ans, str) and ans.startswith("Error"):
        results["main_error"] = ans
    else:
        results["main"], main_success[0] = ans, True
        if concurrent_sink:
            concurrent_sink.force_replace()
            if not main_started[0]: concurrent_sink.target_sink.process_chunk(ans, is_main=True, replace=False)

def _finalize_concurrent_result(results, main_success, fallback_thread):
    if main_success[0] and "main" in results: return results["main"]
    fallback_thread.join()
    if "fallback" in results: return results["fallback"]
    if "main_error" in results: return f"Error processing main: {results['main_error']}, Fallback error: {results.get('fallback_error', 'unknown')}"
    return "Error processing with both models."

def _run_concurrent_llms(llm, fallback_llm, prompt, image_path, is_image, status_callback, enable_stitching, sink, cancel_event):
    results = {}
    lock, main_finished = threading.Lock(), threading.Event()
    main_started, fallback_started, main_success = [False], [False], [False]

    concurrent_sink = ConcurrentSinkWrapper(sink, main_finished, main_started, fallback_started, main_success, cancel_event) if sink else None

    def run_main():
        try:
            ans = _execute_single_llm(llm, prompt, image_path, is_image, status_callback, enable_stitching, concurrent_sink, cancel_event, True)
            with lock: _handle_main_result(results, main_success, ans, concurrent_sink, main_started)
        except Exception as e:
            with lock: results["main_error"] = str(e)
        finally:
            main_finished.set()

    def run_fallback():
        try:
            ans = _execute_single_llm(fallback_llm, prompt, image_path, is_image, None, enable_stitching, concurrent_sink, cancel_event, False)
            with lock: results["fallback"] = ans
        except Exception as e:
            with lock: results["fallback_error"] = str(e)

    mt = threading.Thread(target=run_main, daemon=True)
    ft = threading.Thread(target=run_fallback, daemon=True)
    mt.start()
    ft.start()
    mt.join()

    if cancel_event.is_set(): return PIPELINE_CANCELLED_MSG
    return _finalize_concurrent_result(results, main_success, ft)


def process_pipeline(
    source: Source, llm: LLMEngine, prompt_text: str, status_callback=None, session_manager=None,
    enable_stitching: bool = True, sink: Sink = None, fallback_llm: LLMEngine = None,
    coords=None, text=None, cancel_event: threading.Event = None,
) -> str:
    if cancel_event is None: cancel_event = threading.Event()
    pipeline_start_time = time.time()

    print(f"Using source: {source.__class__.__name__}")
    source_name = getattr(source, "name", "unknown")

    try:
        extracted_text, image_path, is_image = _retrieve_source_data(source, llm, coords, text, status_callback, cancel_event)
    except Exception as e: return f"Error retrieving data from source: {str(e)}"

    if cancel_event.is_set(): return PIPELINE_CANCELLED_MSG

    prompt = f"{prompt_text}: {extracted_text}" if prompt_text and extracted_text else (prompt_text or extracted_text)
    print(f"Submitted prompt: {prompt}")

    if cancel_event.is_set(): return PIPELINE_CANCELLED_MSG

    if not fallback_llm:
        final_result = _execute_single_llm(llm, prompt, image_path, is_image, status_callback, enable_stitching, sink, cancel_event, True)
    else:
        final_result = _run_concurrent_llms(llm, fallback_llm, prompt, image_path, is_image, status_callback, enable_stitching, sink, cancel_event)

    if cancel_event.is_set(): return PIPELINE_CANCELLED_MSG

    elapsed_ms = (time.time() - pipeline_start_time) * 1000
    print(f"[Pipeline] Main thread finished processing in {elapsed_ms:.2f} ms")

    if session_manager and final_result and not final_result.startswith("Error"):
        try: session_manager.append_interaction(prompt, image_path, final_result, extracted_text, source_name=source_name)
        except Exception as e: print(f"Failed to append to session manager: {e}")

    return final_result
