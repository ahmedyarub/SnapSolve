import logging
import os
import sys

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from PIL import Image, ImageDraw
from pydantic import BaseModel

# Allow `python services/ocr_service.py` as well as `uvicorn services.ocr_service:app`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.paddle_ocr_common import create_paddle_ocr, parse_ocr_results

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _warmup(engine):
    """Runs one inference on a rendered string so CUDA and the models are loaded."""
    img = Image.new("RGB", (200, 50), color=(255, 255, 255))
    expected = "Warmup Text"
    ImageDraw.Draw(img).text((10, 10), expected, fill=(0, 0, 0))
    bgr = np.array(img)[:, :, ::-1].copy()
    recognised = " ".join(parse_ocr_results(engine.ocr(bgr)))
    if expected in recognised:
        logger.info(f"OCR Engine Warmed Up. Recognized text: '{recognised}'")
    else:
        logger.info(
            f"OCR Engine Warmed Up. Warning: Recognized text '{recognised}' did not match expected '{expected}'"
        )


# Initialize ONCE on boot
logger.info("Loading OCR weights...")
ocr = create_paddle_ocr()
logger.info("OCR Engine Ready.")
_warmup(ocr)


class ImageRequest(BaseModel):
    file_path: str


app = FastAPI()


@app.post("/ocr")
async def extract_text(request: ImageRequest):
    logger.info(f"Received OCR request: {request.model_dump_json()}")
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk.")

    image_data = cv2.imread(request.file_path)
    if image_data is None:
        raise HTTPException(status_code=400, detail="Could not read the image file.")

    extracted_text = " ".join(parse_ocr_results(ocr.ocr(image_data)))
    logger.info(f"Recognized text: {extracted_text}")
    return {"text": extracted_text}


if __name__ == "__main__":
    import signal

    import uvicorn

    def _handle_exit(_sig, _frame):
        os._exit(0)

    signal.signal(signal.SIGINT, _handle_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_exit)

    uvicorn.run(app, host="127.0.0.1", port=8000)
