import joblib
import pandas as pd
from config import fire_sim, columns_order

import threading

# ----- Models -----
smoke_model = None
fire_risk_model = None
yolo_model = None
yolo_lock = threading.Lock()
results_dict = {}

def init_models(load_yolo=False):
    global smoke_model, fire_risk_model, yolo_model
    
    try:
        smoke_model = joblib.load("smoke_xgboost_model.pkl")
        print("[OK] Loaded Smoke XGBoost model")
        compute_results()
    except Exception as e:
        print(f"[ERROR] Failed to load Smoke model: {e}")
        
    try:
        fire_risk_model = joblib.load("fire_risk_xgb.pkl")
        print("[OK] Loaded Fire Risk XGBoost model")
    except Exception as e:
        print(f"[ERROR] Failed to load Fire Risk model: {e}")
        
    if load_yolo:
        try:
            from ultralytics import YOLO
            yolo_model = YOLO("yolo_models/yolov8n.pt")
            print("[OK] Loaded YOLO model")
        except Exception as e:
            print(f"[ERROR] Failed to load YOLO model: {e}")

def get_smoke_model():
    return smoke_model

def get_fire_risk_model():
    return fire_risk_model

def get_yolo_model():
    return yolo_model, yolo_lock

def compute_results():
    """Run predictions using the *current* sensor state from the fire simulator."""
    global results_dict
    if not smoke_model:
        return
    current_data = fire_sim.get_sensor_data()   # ← dynamic snapshot
    # print(fire_sim.status())                     # log sim state to console
    for shop_key, sensor_data in current_data.items():
        df_test = pd.DataFrame(sensor_data, columns=columns_order)
        proba = smoke_model.predict_proba(df_test)[0][1]
        results_dict[shop_key] = float(proba * 100) / 100

def get_grid_predictions():
    """Return binary fire/no-fire prediction per shop using current sim data."""
    if not smoke_model:
        return {}

    grid_results = {}
    current_data = fire_sim.get_sensor_data()   # ← dynamic snapshot
    for shop_key, sensor_data in current_data.items():
        df_test = pd.DataFrame(sensor_data, columns=columns_order)
        prediction = smoke_model.predict(df_test)[0]
        grid_results[shop_key] = int(prediction)
    return grid_results

def get_results_dict():
    """Re-compute and return fire probabilities based on current sim time."""
    compute_results()   # refresh every time the UI polls
    return results_dict

