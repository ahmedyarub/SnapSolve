import abc
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from PIL import ImageGrab


class OCREngine(abc.ABC):
    @abc.abstractmethod
    def extract_text(self, image_path: str, status_callback=None) -> str:
        pass


class NoOCREngine(OCREngine):
    def extract_text(self, image_path: str, status_callback=None) -> str:
        return None


class PaddleOCREngine(OCREngine):
    def __init__(self, status_callback=None):
        if status_callback:
            status_callback("Initializing PaddleOCR...")
        try:
            import warnings
            # Silence C++ logs
            os.environ['GLOG_minloglevel'] = '2'
            from paddleocr import PaddleOCR
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            self.ocr = PaddleOCR(
                lang='en',
                use_textline_orientation=False,
                use_doc_unwarping=False,
            )

            # Warmup
            if os.path.exists("test_image.png"):
                if status_callback:
                    status_callback("Warming up PaddleOCR...")
                self.ocr.ocr("test_image.png")
            else:
                from PIL import Image
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                img = Image.new('RGB', (100, 100), color='white')
                img.save(temp_file.name)
                self.ocr.ocr(temp_file.name)
                os.remove(temp_file.name)

        except ImportError:
            raise Exception("Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine.")
        except Exception as e:
            import traceback
            print(f"Error during OCR initialization:\n{traceback.format_exc()}")
            raise Exception(f"Error during OCR initialization: {str(e)}")

    def extract_text(self, image_path: str, status_callback=None) -> str:
        if status_callback:
            status_callback("Running PaddleOCR...")

        try:
            start_time = time.time()

            results = self.ocr.ocr(image_path)

            text_lines = []
            if results:
                for res in results:
                    if not res:
                        continue
                    if hasattr(res, 'json'):
                        data = res.json
                        if 'res' in data and 'rec_texts' in data['res']:
                            texts = data['res']['rec_texts']
                            scores = data['res']['rec_scores']

                            for text, score in zip(texts, scores):
                                if score >= 0.5:
                                    text_lines.append(text)

                    elif isinstance(res, list):
                        for line in res:
                            text = line[1][0]
                            confidence = line[1][1]
                            if confidence >= 0.5:
                                text_lines.append(text)

            extracted_text = None
            if text_lines:
                extracted_text = " ".join(text_lines)
                print(f"Extracted Text: {extracted_text}")
            else:
                print("PaddleOCR found no text.")

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"PaddleOCR took {elapsed_ms:.2f} ms")

            return extracted_text

        except ImportError:
            raise Exception("Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine.")
        except Exception as e:
            import traceback
            print(f"Error during OCR execution:\n{traceback.format_exc()}")
            raise Exception(f"Error during OCR execution: {str(e)}")


class LLMEngine(abc.ABC):
    def __init__(self, model: str):
        self.model = model

    @abc.abstractmethod
    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None, session_manager=None, enable_stitching=True,
                        chunk_callback=None) -> str:
        pass


class OllamaEngine(LLMEngine):
    def __init__(self, model: str, ollama_url: str, status_callback=None):
        super().__init__(model)
        self.ollama_url = ollama_url

        # Warmup
        if status_callback:
            status_callback("Warming up Ollama (loading model into memory)...")
        try:
            payload = {
                "model": self.model,
                "prompt": "What is the largest country in the world?",
                "stream": False
            }
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                # Just read the response to ensure it completed
                _ = response.read()
            if status_callback:
                status_callback("Ollama warmup complete.")
        except Exception as e:
            if status_callback:
                status_callback(f"Ollama warmup failed: {str(e)}")
            print(f"Ollama warmup failed: {str(e)}")

    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None, session_manager=None, enable_stitching=True,
                        chunk_callback=None) -> str:
        print(f"[OllamaEngine] Request started for model: {self.model} at {self.ollama_url}")
        if status_callback:
            status_callback("Processing with Ollama...")

        start_time = time.time()

        # Inject history
        full_prompt = prompt
        if session_manager and enable_stitching:
            history = session_manager.get_history()
            if history:
                history_text = "Previous conversation:\n"
                for h in history:
                    history_text += f"User: {h.get('prompt', '')}\n"
                    history_text += f"Assistant: {h.get('response', '')}\n\n"
                history_text += "Current request:\n"
                full_prompt = history_text + prompt

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False
        }

        if not extracted_text:
            # Need to send image if no text was extracted
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                payload["images"] = [encoded_string]

        try:
            print(f"[OllamaEngine] Sending request...")
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                ans = data.get("response", "").strip()
        except Exception as e:
            print(f"[OllamaEngine] Error calling Ollama API: {str(e)}")
            return f"Error calling Ollama API: {str(e)}"

        elapsed_ms = (time.time() - start_time) * 1000
        print(f"[OllamaEngine] Request finished successfully in {elapsed_ms:.2f} ms")
        return ans


class GeminiCLIEngine(LLMEngine):
    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None, session_manager=None, enable_stitching=True,
                        chunk_callback=None) -> str:
        print(f"[GeminiCLIEngine] Request started for model: {self.model}")
        start_time = time.time()
        # We use the -p flag for a single prompt and -o json for easy parsing
        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = prompt
        if session_manager and enable_stitching:
            history = session_manager.get_history()
            if history:
                history_text = "Previous conversation:\n"
                for h in history:
                    history_text += f"User: {h.get('prompt', '')}\n"
                    history_text += f"Assistant: {h.get('response', '')}\n\n"
                history_text += "Current request:\n"
                full_prompt = history_text + prompt

        safe_prompt = full_prompt

        if extracted_text:
            # If we have extracted text, just send the text prompt without the image
            combined_prompt = f'"{safe_prompt}"'

            cmd_args = [
                gemini_cmd,
                "-p", combined_prompt,
                "-o", "json",
                "-m", self.model
            ]
        else:
            # Ensure the prompt is properly wrapped and the path is prefixed with @
            combined_prompt = f'"{safe_prompt} @{image_path}"'

            # Get directory path and ensure it has a trailing slash and is wrapped in quotes
            temp_dir = os.path.dirname(image_path)
            if not temp_dir.endswith(os.sep):
                temp_dir += os.sep
            include_dir_arg = f'{temp_dir}'

            cmd_args = [
                gemini_cmd,
                "-p", combined_prompt,
                "-o", "json",
                "--include-directories", include_dir_arg,
                "-m", self.model
            ]

        print(f"Executing command: {' '.join(cmd_args)}")

        if status_callback:
            status_callback("Processing with Gemini CLI...")

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                check=True
            )
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"Processing took {elapsed_ms:.2f} ms")

            # Parse the JSON response from the CLI
            data = json.loads(result.stdout)
            return data.get("response", "").strip()
        except subprocess.CalledProcessError as e:
            return f"CLI Error: {e.stderr}"


class GoogleGenAIEngine(LLMEngine):
    def __init__(self, model: str, api_key: str):
        super().__init__(model)
        self.api_key = api_key
        print(f"[GoogleGenAIEngine] Initialized with model: {self.model}")

    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None, session_manager=None, enable_stitching=True,
                        chunk_callback=None) -> str:
        if status_callback:
            status_callback("Processing with Google GenAI...")

        print(f"[GoogleGenAIEngine] Request started for model: {self.model}")
        print(f"[GoogleGenAIEngine] Extracted text provided: {bool(extracted_text)}")

        try:
            from google import genai
            from google.genai import types
            print("[GoogleGenAIEngine] SDK imported successfully.")
        except ImportError:
            print("[GoogleGenAIEngine] Error: google-genai SDK not installed.")
            return "Error: google-genai is not installed. Please install it to use the 'google-genai' engine."

        if not self.api_key:
            print("[GoogleGenAIEngine] Error: API key is missing.")
            return "Error: Google GenAI API key is missing. Please add it to your configuration."

        start_time = time.time()

        try:
            print("[GoogleGenAIEngine] Initializing client...")
            client = genai.Client(api_key=self.api_key)

            contents = []

            if session_manager and enable_stitching:
                history = session_manager.get_history()
                for h in history:
                    # Map previous interactions to content objects
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=h.get('prompt', ''))]
                    ))
                    contents.append(types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=h.get('response', ''))]
                    ))

            current_parts = []
            current_parts.append(types.Part.from_text(text=prompt))

            if not extracted_text:
                print(f"[GoogleGenAIEngine] Loading image from {image_path}...")
                with open(image_path, "rb") as f:
                    image_bytes = f.read()

                # Guess mime type based on extension
                import mimetypes
                mime_type, _ = mimetypes.guess_type(image_path)
                if not mime_type:
                    mime_type = 'image/png'

                current_parts.append(
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mime_type,
                    )
                )

            contents.append(types.Content(role="user", parts=current_parts))

            print("[GoogleGenAIEngine] Sending request to API...")

            print("[GoogleGenAIEngine] Calling generate_content_stream...")
            response_stream = client.models.generate_content_stream(
                model=self.model,
                contents=contents,
            )

            print("[GoogleGenAIEngine] Stream started, waiting for chunks...")
            ans_chunks = []
            buffer = ""
            for i, chunk in enumerate(response_stream):
                print(f"[GoogleGenAIEngine] Received chunk {i}: {repr(chunk.text)}")
                ans_chunks.append(chunk.text)
                buffer += chunk.text
                if "\n" in buffer:
                    last_newline_idx = buffer.rindex("\n")
                    complete_lines = buffer[:last_newline_idx + 1]
                    buffer = buffer[last_newline_idx + 1:]
                    if chunk_callback:
                        chunk_callback(complete_lines)

            if buffer and chunk_callback:
                chunk_callback(buffer)

            ans = "".join(ans_chunks)

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"[GoogleGenAIEngine] Request finished successfully in {elapsed_ms:.2f} ms")
            return ans
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"


import threading


def capture_and_process(coords, prompt_text="answer the following question quickly and briefly", session_manager=None, enable_stitching=True,
                        model="gemini-2.5-flash-lite", llm_engine="gemini", ocr_engine="none",
                        ollama_url="http://localhost:11434", google_genai_api_key="", ocr_engine_instance=None,
                        llm_engine_instance=None, status_callback=None, chunk_callback=None, fallback_model=None,
                        fallback_llm_engine_instance=None, pre_extracted_text=None):

    temp_file_path = None
    extracted_text = pre_extracted_text

    if not pre_extracted_text:
        if not coords or len(coords) != 4:
            return "Error: Invalid coordinates. Please run coordinate selection again."

        # Unpack coordinates (x1, y1, x2, y2)
        bbox = tuple(coords)

        if status_callback:
            status_callback("Capturing screen...")

        try:
            # Capture screen region
            img = ImageGrab.grab(bbox=bbox)
        except Exception as e:
            return f"Error capturing screen: {str(e)}"

        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_file_path = temp_file.name
        temp_file.close()

    try:
        if not pre_extracted_text:
            # Save image to temporary file
            img.save(temp_file_path)

            # Setup OCR engine
            ocr = ocr_engine_instance
            if not ocr:
                if ocr_engine == "paddleocr":
                    ocr = PaddleOCREngine()
                else:
                    ocr = NoOCREngine()

            try:
                extracted_text = ocr.extract_text(temp_file_path, status_callback)
            except Exception as e:
                return str(e)

        # Setup LLM engine
        llm = llm_engine_instance
        if not llm:
            if llm_engine == "ollama":
                llm = OllamaEngine(model, ollama_url)
            elif llm_engine == "google-genai":
                llm = GoogleGenAIEngine(model, google_genai_api_key)
            else:
                llm = GeminiCLIEngine(model)

        if extracted_text:
            prompt = f"{prompt_text}: {extracted_text}"
        else:
            prompt = prompt_text

        if not fallback_model or fallback_model == "None":
            ans = llm.generate_answer(prompt, temp_file_path, extracted_text, status_callback, chunk_callback)
            return ans

        # Fallback model logic
        fallback_llm = fallback_llm_engine_instance
        if not fallback_llm:
            if llm_engine == "ollama":
                fallback_llm = OllamaEngine(fallback_model, ollama_url)
            elif llm_engine == "google-genai":
                fallback_llm = GoogleGenAIEngine(fallback_model, google_genai_api_key)
            else:
                fallback_llm = GeminiCLIEngine(fallback_model)

        results = {}
        threads = []
        lock = threading.Lock()

        main_started = [False]
        fallback_started = [False]

        main_finished = threading.Event()
        main_success = [False]

        def run_main():
            def main_chunk_callback(chunk):
                with lock:
                    main_started[0] = True
                    if chunk_callback and not fallback_started[0]:
                        chunk_callback(chunk, is_main=True, replace=False)

            try:
                ans = llm.generate_answer(prompt, temp_file_path, extracted_text, status_callback, session_manager, enable_stitching, main_chunk_callback)
                with lock:
                    # In this application, API errors are often returned as strings starting with "Error"
                    if isinstance(ans, str) and ans.startswith("Error"):
                        results['main_error'] = ans
                    else:
                        results['main'] = ans
                        main_success[0] = True
                        if chunk_callback and fallback_started[0]:
                            chunk_callback(ans, is_main=True, replace=True)
            except Exception as e:
                with lock:
                    results['main_error'] = str(e)
            finally:
                main_finished.set()

        def run_fallback():
            def fallback_chunk_callback(chunk):
                with lock:
                    # We continue pushing fallback chunks to the UI as long as the main model
                    # hasn't started streaming, AND hasn't completed successfully.
                    if not main_started[0] and not main_success[0] and not main_finished.is_set():
                        fallback_started[0] = True
                        if chunk_callback:
                            chunk_callback(chunk, is_main=False, replace=False)

            try:
                ans = fallback_llm.generate_answer(prompt, temp_file_path, extracted_text, None, session_manager, enable_stitching,
                                                   fallback_chunk_callback)
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

        if main_success[0] and 'main' in results:
            final_result = results['main']
            if session_manager and final_result and not final_result.startswith("Error"):
                try:
                    # check if we have a direct string path or just using image
                    # in capture_and_process, we pass temp_file_path.
                    # but if there was NO capture and just text passed directly, maybe temp_file_path is None?
                    # wait, capture_and_process creates a temp file even for warmups.
                    # let's just pass temp_file_path, it's defined in the method wrapper
                    session_manager.append_interaction(prompt, temp_file_path, final_result, extracted_text)
                except Exception as e:
                    print(f"Failed to append to session manager: {e}")
            return final_result

        # Main model failed.
        # If fallback hasn't finished yet, we need to wait for it.
        fallback_thread.join()

        if 'fallback' in results:
            final_result = results['fallback']
        elif 'main_error' in results:
            final_result = f"Error processing main: {results['main_error']}, Fallback error: {results.get('fallback_error', 'unknown')}"
        else:
            final_result = f"Error processing with both models."

        if session_manager and final_result and not final_result.startswith("Error"):
            try:
                # `pre_extracted_text` doesn't exist here, handle correctly:
                is_direct_text = locals().get('pre_extracted_text', None) is not None
                session_manager.append_interaction(prompt, temp_file_path if not is_direct_text else None, final_result, extracted_text)
            except Exception as e:
                print(f"Failed to append to session manager: {e}")

        return final_result

    except Exception as e:
        return f"Error processing: {str(e)}"
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
