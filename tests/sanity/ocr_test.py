import os
import time
import warnings

# Silence C++ logs
os.environ["GLOG_minloglevel"] = "2"
from paddleocr import PaddleOCR

warnings.filterwarnings("ignore", category=DeprecationWarning)

print("Initializing PaddleOCR with CUDA (v4 Models)...")

ocr = PaddleOCR(lang="en", use_textline_orientation=False, use_doc_unwarping=False)

img_path = "test_image.png"
print(f"\nProcessing {img_path}...")

start_time = time.time()

results = ocr.ocr(img_path)
end_time = time.time()

print("-" * 40)

if results:
    for res in results:
        if hasattr(res, "json"):
            data = res.json
            if "res" in data and "rec_texts" in data["res"]:
                texts = data["res"]["rec_texts"]
                scores = data["res"]["rec_scores"]

                for text, score in zip(texts, scores):
                    if score >= 0.5:
                        print(f"Text: {text:<20} | Confidence: {score:.4f}")

        elif isinstance(res, list):
            for line in res:
                text = line[1][0]
                confidence = line[1][1]
                if confidence >= 0.5:
                    print(f"Text: {text:<20} | Confidence: {confidence:.4f}")
else:
    print("No text detected in the image.")

print("-" * 40)
print(f"Inference Time: {end_time - start_time:.4f} seconds")
