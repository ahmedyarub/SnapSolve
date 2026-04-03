import subprocess
import json
from PIL import ImageGrab
import os
import tempfile

def capture_and_process(coords):
    if not coords or len(coords) != 4:
        return "Error: Invalid coordinates. Please run coordinate selection again."

    # Unpack coordinates (x1, y1, x2, y2)
    bbox = tuple(coords)

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

        # We use the -p flag for a single prompt and --json for easy parsing
        # Pass the image file as positional argument to gemini CLI
        result = subprocess.run(
            ["gemini", "-p", prompt, temp_file_path, "--json"],
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
