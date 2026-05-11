import os
import warnings
import logging

import cv2
import numpy as np
from PIL import Image, ImageDraw
from fastapi import FastAPI, HTTPException
from paddleocr import PaddleOCR
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# Helper function to parse OCR results consistently, based on local_paddleocr_engine.py
def _parse_json_result(data):
    """Parse JSON result format."""
    text_lines = []
    if "res" in data and "rec_texts" in data["res"]:
        texts = data["res"]["rec_texts"]
        scores = data["res"]["rec_scores"]
        for text, score in zip(texts, scores):
            if score >= 0.5:
                text_lines.append(text)
    return text_lines


def _parse_list_result(res):
    """Parse list result format."""
    text_lines = []
    for line in res:
        text = line[1][0]
        confidence = line[1][1]
        if confidence >= 0.5:
            text_lines.append(text)
    return text_lines


def _parse_ocr_result(res):
    """Parse single OCR result."""
    if hasattr(res, "json"):
        data = res.json
        return _parse_json_result(data)
    elif isinstance(res, list):
        return _parse_list_result(res)
    return []


def parse_ocr_results(results):
    """Parse OCR results and extract text."""
    text_lines = []
    if results:
        for res in results:
            if not res:
                continue
            text_lines.extend(_parse_ocr_result(res))

    return " ".join(text_lines)


# Initialize ONCE on boot
logging.info("Loading OCR weights...")
os.environ["GLOG_minloglevel"] = "2"
warnings.filterwarnings("ignore", category=DeprecationWarning)

ocr = PaddleOCR(
    lang="en",
    use_textline_orientation=False,
    use_doc_unwarping=False,
)
logging.info("OCR Engine Ready.")

# Create a dummy image with text for warmup
img = Image.new("RGB", (200, 50), color=(255, 255, 255))
d = ImageDraw.Draw(img)
warmup_text_input = "Warmup Text"
d.text((10, 10), warmup_text_input, fill=(0, 0, 0))
open_cv_image = np.array(img)
open_cv_image = open_cv_image[:, :, ::-1].copy()  # RGB to BGR
warmup_result = ocr.ocr(open_cv_image)

warmup_extracted_text = parse_ocr_results(warmup_result)

if warmup_text_input in warmup_extracted_text:
    logging.info(f"OCR Engine Warmed Up. Recognized text: '{warmup_extracted_text}'")
else:
    logging.info(
        f"OCR Engine Warmed Up. Warning: Recognized text '{warmup_extracted_text}' did not match expected '{warmup_text_input}'"
    )


class ImageRequest(BaseModel):
    file_path: str


app = FastAPI()


@app.post("/ocr")
async def extract_text(request: ImageRequest):
    logging.info(f"Received OCR request: {request.model_dump_json()}")
    # 1. Validate the file exists
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk.")

    logging.info(f"Received image for OCR: {request.file_path}")

    # 2. Read directly from disk into a numpy array via OpenCV
    image_data = cv2.imread(request.file_path)

    if image_data is None:
        raise HTTPException(status_code=400, detail="Could not read the image file.")

    # 3. Instant execution
    result = ocr.ocr(image_data)

    # 4. Extract just the text
    extracted_text = parse_ocr_results(result)

    logging.info(f"Recognized text: {extracted_text}")

    return {"text": extracted_text}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
