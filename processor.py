import subprocess
import json
from PIL import ImageGrab
import os
import tempfile
import shutil
import time

def capture_and_process(coords, model="gemini-2.5-flash-lite", status_callback=None):
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

        # Simple, fast prompt to ensure a short, direct answer
        prompt = "Read the question in this image and provide a very short, direct answer. Do not include extra explanation."

        # We use the -p flag for a single prompt and -o json for easy parsing
        # Pass the image file as positional argument to gemini CLI
        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        # Ensure the prompt is properly wrapped and the path is prefixed with @
        combined_prompt = f'"{prompt} @{temp_file_path}"'

        # Get directory path and ensure it has a trailing slash and is wrapped in quotes
        temp_dir = os.path.dirname(temp_file_path)
        if not temp_dir.endswith(os.sep):
            temp_dir += os.sep
        include_dir_arg = f'"{temp_dir}"'

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

        start_time = time.time()
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
        return f"Error calling Gemini CLI: {str(e)}"
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
