import subprocess
import json
from PIL import ImageGrab
import os
import tempfile
import shutil
import time
import base64
import urllib.request
import urllib.error

def capture_and_process(coords, model="gemini-2.5-flash-lite", llm_engine="gemini", ocr_engine="none", ollama_url="http://localhost:11434", status_callback=None):
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

        extracted_text = None

        if ocr_engine == "paddleocr":
            if status_callback:
                status_callback("Running PaddleOCR...")
            start_time = time.time()
            try:
                import warnings
                # Silence C++ logs
                os.environ['GLOG_minloglevel'] = '2'
                from paddleocr import PaddleOCR
                warnings.filterwarnings("ignore", category=DeprecationWarning)

                ocr = PaddleOCR(
                    lang='en',
                    use_textline_orientation=False,
                    use_doc_unwarping=False,
                    show_log=False
                )

                results = ocr.ocr(temp_file_path)

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

                if text_lines:
                    extracted_text = " ".join(text_lines)
                    print(f"Extracted Text: {extracted_text}")
                else:
                    print("PaddleOCR found no text.")
            except ImportError:
                return "Error: paddleocr is not installed. Please install it to use the 'paddleocr' engine."
            except Exception as e:
                import traceback
                print(f"Error during OCR execution:\n{traceback.format_exc()}")
                return f"Error during OCR execution: {str(e)}"

            elapsed_ms = (time.time() - start_time) * 1000
            print(f"PaddleOCR took {elapsed_ms:.2f} ms")


        # Simple, fast prompt to ensure a short, direct answer
        base_prompt = "answer the following question quickly and briefly"

        if extracted_text:
            prompt = f"{base_prompt}: {extracted_text}"
        else:
            prompt = f"Read the question in this image and {base_prompt}."

        start_time = time.time()

        if llm_engine == "ollama":
            if status_callback:
                status_callback("Processing with Ollama...")

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }

            if not extracted_text:
                # Need to send image if no text was extracted
                with open(temp_file_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    payload["images"] = [encoded_string]

            try:
                req = urllib.request.Request(
                    f"{ollama_url.rstrip('/')}/api/generate",
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

        else: # default to gemini
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
                    "-m", model
                ]
            else:
                # Ensure the prompt is properly wrapped and the path is prefixed with @
                combined_prompt = f'"{prompt} @{temp_file_path}"'

                # Get directory path and ensure it has a trailing slash and is wrapped in quotes
                temp_dir = os.path.dirname(temp_file_path)
                if not temp_dir.endswith(os.sep):
                    temp_dir += os.sep
                include_dir_arg = f'{temp_dir}'

                cmd_args = [
                    gemini_cmd,
                    "-p", combined_prompt,
                    "-o", "json",
                    "--include-directories", include_dir_arg,
                    "-m", model
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

    except Exception as e:
        return f"Error processing: {str(e)}"
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
