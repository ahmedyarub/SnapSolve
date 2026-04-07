import subprocess
import json
from PIL import ImageGrab
import os
import tempfile
import shutil

def capture_and_process(coords, status_callback=None):
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

        # Combine the prompt and the image file path to avoid conflict.
        # Crucially, we must still use the -p flag to force non-interactive mode.
        combined_prompt = f"{prompt} {temp_file_path}"
        cmd_args = [gemini_cmd, "-p", combined_prompt, "-o", "json"]
        print(f"Executing command: {' '.join(cmd_args)}")

        if status_callback:
            status_callback("Processing with Gemini CLI...")

        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            check=True
        )

        # Parse the JSON response from the CLI
        data = json.loads(result.stdout)
        return data.get("candidates", [{}])[0].get("content", "").strip()

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
