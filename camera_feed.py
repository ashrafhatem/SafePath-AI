import cv2
import requests
import time
import threading
from ml_utils import init_models, get_smoke_model, get_yolo_model

# ===============================
# Load models once
# ===============================
init_models(load_yolo=True)
smokeModel = get_smoke_model()
model, model_lock = get_yolo_model()

BACKEND_URL = "http://127.0.0.1:5000/update_camera_data"

# ===============================
# Cameras
# ===============================
cameras = [f"{c}{i}" for c in "ABCDEFG" for i in (1, 2)]
VIDEO_SOURCE = "videos/vid1.mp4"

camera_data = {}
for cam_id in cameras:
    camera_data[cam_id] = {
        "camera_id": cam_id,
        "corridor": f"Corridor {cam_id[0]}",
        "fire_status": False,
        "people_count": 0,
        "timestamp": time.time()
    }

# ===============================
# Count People
# ===============================
def count_people(frame):
    with model_lock:
        results = model(frame, verbose=False)

    count = 0
    for r in results:
        for cls in r.boxes.cls:
            if int(cls) == 0:
                count += 1

    return count

# ===============================
# Single Camera Thread Worker
# ===============================
def camera_worker(cam_id):
    cap = cv2.VideoCapture(VIDEO_SOURCE)

    while True:
        ret, frame = cap.read()

        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        people = count_people(frame)

        camera_data[cam_id]["people_count"] = people
        camera_data[cam_id]["fire_status"] = False  # Keep false or mock
        camera_data[cam_id]["timestamp"] = time.time()
        
        time.sleep(1) # Delay to prevent massive CPU consumption

# ===============================
# Start Threads
# ===============================
for cam_id in cameras:
    threading.Thread(
        target=camera_worker,
        args=(cam_id,),
        daemon=True
    ).start()

# ===============================
# Live Data Sending
# ===============================
while True:
    try:
        requests.post(
            BACKEND_URL,
            json=camera_data,
            timeout=1
        )
        print("LIVE SENT: 14 cameras data")
    except Exception as e:
        print("Connection error:", e)

    time.sleep(1)