"""
model_registry.py – Singleton that loads all ML models once at app startup.

All cameras and upload jobs share the same model instances.
YOLO and EasyOCR inference calls are stateless so sharing is safe.
"""

import threading
import time
import os
import sys
import numpy as np

# Ensure ML pipeline is importable
ML_PIPELINE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "integrate")
)
if ML_PIPELINE_DIR not in sys.path:
    sys.path.insert(0, ML_PIPELINE_DIR)

# Model paths (same as in integrate/main.py)
MODEL_COCO   = "yolov8n.pt"
MODEL_HELMET = r"D:\Final year project\user interface\models\helmet\best.pt"
MODEL_PLATE  = r"D:\Final year project\user interface\models\license\best.pt"


class ModelRegistry:
    """
    Singleton — loads all ML models once at app startup.
    All cameras and upload jobs share the same model instances.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._loaded = False
        return cls._instance

    def load(self):
        """Load all models into memory. Call once at startup."""
        if self._loaded:
            return

        from ultralytics import YOLO
        import easyocr

        print("[ModelRegistry] Loading models — this happens only once...")
        t0 = time.time()

        self.coco_model = YOLO(MODEL_COCO)
        print(f"  [✓] COCO model       ({time.time()-t0:.1f}s)")

        t1 = time.time()
        self.helmet_model = YOLO(MODEL_HELMET)
        print(f"  [✓] Helmet model     ({time.time()-t1:.1f}s)")

        t2 = time.time()
        self.plate_model = YOLO(MODEL_PLATE)
        print(f"  [✓] Plate model      ({time.time()-t2:.1f}s)")

        t3 = time.time()
        self.ocr_reader = easyocr.Reader(['en'], gpu=False)
        print(f"  [✓] EasyOCR reader   ({time.time()-t3:.1f}s)")

        self._warmup()
        self._loaded = True
        print(f"[ModelRegistry] All models ready in {time.time()-t0:.1f}s\n")

    def _warmup(self):
        """
        Run one dummy inference on each model to trigger JIT compilation.
        Without this the very first real frame is slow.
        """
        dummy = np.zeros((256, 416, 3), dtype='uint8')
        self.coco_model(dummy, verbose=False)
        self.helmet_model(dummy, verbose=False)
        self.plate_model(dummy, verbose=False)
        print("  [✓] Warm-up complete")

    @property
    def is_loaded(self) -> bool:
        return self._loaded


# Global singleton — import this everywhere
models = ModelRegistry()
