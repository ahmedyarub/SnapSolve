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
    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None) -> str:
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

    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None) -> str:
        if status_callback:
            status_callback("Processing with Ollama...")

        start_time = time.time()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        if not extracted_text:
            # Need to send image if no text was extracted
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                payload["images"] = [encoded_string]

        try:
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
            return f"Error calling Ollama API: {str(e)}"

        elapsed_ms = (time.time() - start_time) * 1000
        print(f"Ollama took {elapsed_ms:.2f} ms")
        return ans


class GeminiCLIEngine(LLMEngine):
    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None) -> str:
        start_time = time.time()
        # We use the -p flag for a single prompt and -o json for easy parsing
        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        if extracted_text:
            # If we have extracted text, just send the text prompt without the image
            combined_prompt = f'"{prompt}"'

            cmd_args = [
                gemini_cmd,
                "-p", combined_prompt,
                "-o", "json",
                "-m", self.model
            ]
        else:
            # Ensure the prompt is properly wrapped and the path is prefixed with @
            combined_prompt = f'"{prompt} @{image_path}"'

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

    def generate_answer(self, prompt: str, image_path: str, extracted_text: str, status_callback=None) -> str:
        if status_callback:
            status_callback("Processing with Google GenAI...")

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return "Error: google-genai is not installed. Please install it to use the 'google-genai' engine."

        if not self.api_key:
            return "Error: Google GenAI API key is missing. Please add it to your configuration."

        start_time = time.time()

        try:
            client = genai.Client(api_key=self.api_key)

            contents = []
            contents.append(prompt)

            if not extracted_text:
                from PIL import Image
                img = Image.open(image_path)
                contents.append(img)

            response = client.models.generate_content(
                model=self.model,
                contents=contents,
            )

            ans = response.text

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"Google GenAI took {elapsed_ms:.2f} ms")
            return ans
        except Exception as e:
            return f"Error calling Google GenAI API: {str(e)}"


def capture_and_process(coords, model="gemini-2.5-flash-lite", llm_engine="gemini", ocr_engine="none",
                        ollama_url="http://localhost:11434", google_genai_api_key="", ocr_engine_instance=None,
                        llm_engine_instance=None, status_callback=None):
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
        # Save image to temporary file
        img.save(temp_file_path)

        # Setup OCR engine
        ocr = ocr_engine_instance
        if not ocr:
            if ocr_engine == "paddleocr":
                ocr = PaddleOCREngine()
            else:
                ocr = NoOCREngine()

        extracted_text = None
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

        # Simple, fast prompt to ensure a short, direct answer
        base_prompt = "answer the following question quickly and briefly"

        if extracted_text:
            prompt = f"{base_prompt}: {extracted_text}"
        else:
            prompt = f"Read the question in this image and {base_prompt}."

        ans = llm.generate_answer(prompt, temp_file_path, extracted_text, status_callback)
        return ans

    except Exception as e:
        return f"Error processing: {str(e)}"
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
