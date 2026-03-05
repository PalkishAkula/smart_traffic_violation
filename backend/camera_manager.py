"""
camera_manager.py – Manages one background thread per active camera.
Singleton instance shared across the FastAPI app.

Since run_pipeline_live may not exist yet in the ML pipeline,
this module attempts to import it and falls back to a stub if unavailable.
"""

import threading
import asyncio
import time
import sys
import os
from typing import Dict, Callable, Optional

# Add ML pipeline to path
ML_PIPELINE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "integrate")
)
if ML_PIPELINE_DIR not in sys.path:
    sys.path.insert(0, ML_PIPELINE_DIR)


class CameraManager:
    """
    Manages one background thread per active camera.
    """
    def __init__(self, violation_handler: Callable, frame_handler: Callable,
                 loop: asyncio.AbstractEventLoop,
                 status_callback: Callable = None):
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._violation_handler = violation_handler
        self._frame_handler = frame_handler
        self._loop = loop
        self._status_callback = status_callback  # async fn(camera_id, status)

    def start(self, camera_id: str, source: str):
        """Start live detection for a camera."""
        if camera_id in self._threads and self._threads[camera_id].is_alive():
            return  # already running

        # Convert source to int if it's a digit (webcam index)
        src = int(source) if source.isdigit() else source

        stop_event = threading.Event()
        self._stop_events[camera_id] = stop_event

        def violation_cb(rec, jpeg):
            asyncio.run_coroutine_threadsafe(
                self._violation_handler(camera_id, rec, jpeg),
                self._loop
            )

        def frame_cb(jpeg):
            asyncio.run_coroutine_threadsafe(
                self._frame_handler(camera_id, jpeg),
                self._loop
            )

        def on_thread_exit(cam_id, status):
            """Called when camera thread exits — update status."""
            if self._status_callback:
                asyncio.run_coroutine_threadsafe(
                    self._status_callback(cam_id, status),
                    self._loop
                )

        t = threading.Thread(
            target=self._run_camera,
            args=(src, camera_id, stop_event, violation_cb, frame_cb, on_thread_exit),
            daemon=True,
            name=f"cam-{camera_id}",
        )
        self._threads[camera_id] = t
        t.start()
        print(f"[CameraManager] Started thread for camera {camera_id} (source={src})")

    def _run_camera(self, source, camera_id, stop_event, violation_cb, frame_cb, on_exit):
        """Run the live pipeline in a background thread."""
        exit_status = "stopped"
        try:
            from main import run_pipeline_live
            from model_registry import models
            print(f"[CameraManager] Using run_pipeline_live for {camera_id}")
            run_pipeline_live(
                source,
                camera_id,
                stop_event,
                violation_cb,
                frame_cb,
                model_registry=models,
            )
        except ImportError:
            print(f"[CameraManager] run_pipeline_live not available — "
                  f"using stub for camera {camera_id}")
            self._stub_live(source, camera_id, stop_event, frame_cb)
        except Exception as e:
            print(f"[CameraManager] Error in camera {camera_id}: {e}")
            import traceback
            traceback.print_exc()
            exit_status = "error"
        finally:
            print(f"[CameraManager] Camera {camera_id} thread exiting with status={exit_status}")
            on_exit(camera_id, exit_status)

    def _stub_live(self, source, camera_id, stop_event, frame_cb):
        """
        Stub fallback when run_pipeline_live is not yet implemented.
        Opens the video/camera source and streams frames without ML processing.
        """
        import cv2
        print(f"[Stub] Opening source: {source} (type={type(source).__name__})")
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[Stub] ERROR: Cannot open source: {source}")
            raise RuntimeError(f"Cannot open camera source: {source}")

        print(f"[Stub] Camera {camera_id} opened successfully, streaming frames...")
        last_emit = 0
        frame_count = 0
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                if isinstance(source, int):
                    time.sleep(0.01)  # brief pause before retry
                    continue  # webcam — keep trying
                break  # file ended

            frame_count += 1
            now = time.time()
            if now - last_emit >= 0.1:  # 10 FPS throttle
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                frame_cb(jpeg.tobytes())
                last_emit = now
                if frame_count % 100 == 0:
                    print(f"[Stub] Camera {camera_id}: {frame_count} frames captured")

        cap.release()
        print(f"[Stub] Camera {camera_id} released")

    def stop(self, camera_id: str):
        """Stop live detection for a camera."""
        if camera_id in self._stop_events:
            self._stop_events[camera_id].set()
        if camera_id in self._threads:
            self._threads[camera_id].join(timeout=5)
            del self._threads[camera_id]
            del self._stop_events[camera_id]

    def status(self, camera_id: str) -> str:
        t = self._threads.get(camera_id)
        if t and t.is_alive():
            return "running"
        return "stopped"

    def stop_all(self):
        for cid in list(self._stop_events):
            self.stop(cid)
