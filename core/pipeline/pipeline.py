import threading
import time
from core.sources.base import Source
from core.llm.base import LLMEngine
from core.sinks.base import Sink


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
    text=None,
    cancel_event: threading.Event = None,
) -> str:
    if cancel_event is None:
        cancel_event = threading.Event()

    pipeline_start_time = time.time()
    extracted_text = None
    image_path = None
    is_image = False

    print(f"Using source: {source.__class__.__name__}")

    # 1. Text/Image Retrieval
    try:
        try:
            # Pass cancel_event to source if it accepts it
            if (
                hasattr(source, "get_text")
                and "cancel_event" in source.get_text.__code__.co_varnames
            ):
                extracted_text = source.get_text(
                    coords=coords,
                    text=text,
                    status_callback=status_callback,
                    cancel_event=cancel_event,
                )
            else:
                extracted_text = source.get_text(
                    coords=coords, text=text, status_callback=status_callback
                )
            print(f"Retrieved text from source: {extracted_text}")
        except ValueError as e:
            if llm.supports_images:
                is_image = True
                if (
                    hasattr(source, "get_image")
                    and "cancel_event" in source.get_image.__code__.co_varnames
                ):
                    image_path = source.get_image(
                        coords=coords, text=text, cancel_event=cancel_event
                    )
                else:
                    image_path = source.get_image(coords=coords, text=text)
                print(f"Retrieved image from source: {image_path}")
            else:
                raise ValueError(
                    f"Pipeline failed: Source could not provide text ({str(e)}), and LLM does not support images."
                )
    except Exception as e:
        return f"Error retrieving data from source: {str(e)}"

    if cancel_event.is_set():
        return "Pipeline cancelled."

    # 2. Prompt Augmentation
    if not prompt_text:
        prompt = extracted_text
    else:
        prompt = f"{prompt_text}: {extracted_text}" if extracted_text else prompt_text

    print(f"Submitted prompt: {prompt}")

    if cancel_event.is_set():
        return "Pipeline cancelled."

    # 3. LLM Execution (with Fallback Concurrency)
    if not fallback_llm:
        if is_image:
            if "cancel_event" in llm.process_image.__code__.co_varnames:
                return llm.process_image(
                    prompt,
                    image_path,
                    status_callback,
                    enable_stitching,
                    sink,
                    is_main=True,
                    cancel_event=cancel_event,
                )
            return llm.process_image(
                prompt,
                image_path,
                status_callback,
                enable_stitching,
                sink,
                is_main=True,
            )
        else:
            if "cancel_event" in llm.process_text.__code__.co_varnames:
                return llm.process_text(
                    prompt,
                    status_callback,
                    enable_stitching,
                    sink,
                    is_main=True,
                    cancel_event=cancel_event,
                )
            return llm.process_text(
                prompt, status_callback, enable_stitching, sink, is_main=True
            )

    results = {}
    lock = threading.Lock()

    main_started = [False]
    fallback_started = [False]
    main_success = [False]
    main_finished = threading.Event()

    concurrent_sink = (
        ConcurrentSinkWrapper(
            sink,
            main_finished,
            main_started,
            fallback_started,
            main_success,
            cancel_event,
        )
        if sink
        else None
    )

    def run_main():
        try:
            if is_image:
                if "cancel_event" in llm.process_image.__code__.co_varnames:
                    ans = llm.process_image(
                        prompt,
                        image_path,
                        status_callback,
                        enable_stitching,
                        concurrent_sink,
                        is_main=True,
                        cancel_event=cancel_event,
                    )
                else:
                    ans = llm.process_image(
                        prompt,
                        image_path,
                        status_callback,
                        enable_stitching,
                        concurrent_sink,
                        is_main=True,
                    )
            else:
                if "cancel_event" in llm.process_text.__code__.co_varnames:
                    ans = llm.process_text(
                        prompt,
                        status_callback,
                        enable_stitching,
                        concurrent_sink,
                        is_main=True,
                        cancel_event=cancel_event,
                    )
                else:
                    ans = llm.process_text(
                        prompt,
                        status_callback,
                        enable_stitching,
                        concurrent_sink,
                        is_main=True,
                    )

            with lock:
                if isinstance(ans, str) and ans.startswith("Error"):
                    results["main_error"] = ans
                else:
                    results["main"] = ans
                    main_success[0] = True
                    if concurrent_sink:
                        concurrent_sink.force_replace()
                        if not main_started[0]:
                            concurrent_sink.target_sink.process_chunk(
                                ans, is_main=True, replace=False
                            )

        except Exception as main_error:
            with lock:
                results["main_error"] = str(main_error)
        finally:
            main_finished.set()

    def run_fallback():
        try:
            if is_image:
                if "cancel_event" in fallback_llm.process_image.__code__.co_varnames:
                    ans = fallback_llm.process_image(
                        prompt,
                        image_path,
                        None,
                        enable_stitching,
                        concurrent_sink,
                        is_main=False,
                        cancel_event=cancel_event,
                    )
                else:
                    ans = fallback_llm.process_image(
                        prompt,
                        image_path,
                        None,
                        enable_stitching,
                        concurrent_sink,
                        is_main=False,
                    )
            else:
                if "cancel_event" in fallback_llm.process_text.__code__.co_varnames:
                    ans = fallback_llm.process_text(
                        prompt,
                        None,
                        enable_stitching,
                        concurrent_sink,
                        is_main=False,
                        cancel_event=cancel_event,
                    )
                else:
                    ans = fallback_llm.process_text(
                        prompt, None, enable_stitching, concurrent_sink, is_main=False
                    )
            with lock:
                results["fallback"] = ans
        except Exception as fallback_error:
            with lock:
                results["fallback_error"] = str(fallback_error)

    main_thread = threading.Thread(target=run_main, daemon=True)
    fallback_thread = threading.Thread(target=run_fallback, daemon=True)

    main_thread.start()
    fallback_thread.start()

    main_thread.join()

    if cancel_event.is_set():
        return "Pipeline cancelled."

    elapsed_ms = (time.time() - pipeline_start_time) * 1000
    print(f"[Pipeline] Main thread finished processing in {elapsed_ms:.2f} ms")

    if main_success[0] and "main" in results:
        final_result = results["main"]
    else:
        fallback_thread.join()
        if "fallback" in results:
            final_result = results["fallback"]
        elif "main_error" in results:
            final_result = f"Error processing main: {results['main_error']}, Fallback error: {results.get('fallback_error', 'unknown')}"
        else:
            final_result = "Error processing with both models."

    if session_manager and final_result and not final_result.startswith("Error"):
        try:
            session_manager.append_interaction(
                prompt, image_path, final_result, extracted_text
            )
        except Exception as e:
            print(f"Failed to append to session manager: {e}")

    return final_result
