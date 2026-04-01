from google import genai
from PIL import ImageGrab
import os

def capture_and_process(api_key, coords):
    if not api_key:
        return "Error: Gemini API Key is missing. Please set it in config.json or via command line."

    if not coords or len(coords) != 4:
        return "Error: Invalid coordinates. Please run coordinate selection again."

    # Unpack coordinates (x1, y1, x2, y2)
    bbox = tuple(coords)

    try:
        # Capture screen region
        img = ImageGrab.grab(bbox=bbox)
    except Exception as e:
        return f"Error capturing screen: {str(e)}"

    try:
        # Configure Gemini API client
        client = genai.Client(api_key=api_key)

        # Use gemini-2.5-flash as the latest fast model
        # Simple, fast prompt to ensure a short, direct answer
        prompt = "Read the question in this image and provide a very short, direct answer. Do not include extra explanation."

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img]
        )
        return response.text.strip()
    except Exception as e:
        return f"Error calling Gemini API: {str(e)}"
