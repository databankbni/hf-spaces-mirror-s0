import os
import cv2
import requests
from ultralytics import YOLO
from datetime import datetime, timezone

SPRING_BOOT_URL = os.getenv("SPRING_BOOT_URL", "http://spring-boot:8081")

_models: dict[str, YOLO] = {}

def get_model(model_name: str) -> YOLO:
    if model_name not in _models:
        print(f"Loading model: {model_name}")
        _models[model_name] = YOLO(model_name)
    return _models[model_name]


def detect_on_single_frame(
    rtsp_url: str,
    camera_id: str,
    model_name: str = "yolov8n.pt",
    confidence: float = 0.5
) -> dict:
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open stream: {rtsp_url}")

    for _ in range(3):
        cap.grab()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError(f"Failed to read frame from: {rtsp_url}")

    h, w = frame.shape[:2]
    model = get_model(model_name)
    results = model(frame, conf=confidence, verbose=False)

    detections = []
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append({
                "label":       model.names[int(box.cls)],
                "confidence":  round(float(box.conf), 3),
                "x":           x1,
                "y":           y1,
                "width":       x2 - x1,
                "height":      y2 - y1,
                "frameWidth":  w,
                "frameHeight": h,
            })

    payload = {
        "cameraId":    camera_id,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "detections":  detections,
        "frameWidth":  w,
        "frameHeight": h,
    }

    # Post results to Spring Boot
    try:
        requests.post(
            f"{SPRING_BOOT_URL}/api/detections",
            json=payload,
            timeout=2
        )
    except Exception as e:
        print(f"[WARNING] Failed to POST to Spring Boot: {e}")

    return payload