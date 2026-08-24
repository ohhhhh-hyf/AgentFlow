import os
os.environ["CUDA_VISIBLE_DEVICES"] = "2"

import json
from paddleocr import PaddleOCR


ocr = PaddleOCR(
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    device="gpu:0"
)

img_path = "/root/h00984725/ocr/samples/examples/U202314751_15.jpg"

result = ocr.predict(img_path)

output_path = "paddleocr_raw_result.json"

raw_result = []

for res in result:
    raw_result.append(res.json)

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(
        raw_result,
        f,
        ensure_ascii=False,
        indent=2,
        default=str
    )

print(f"OCR完成，结果保存到: {output_path}")