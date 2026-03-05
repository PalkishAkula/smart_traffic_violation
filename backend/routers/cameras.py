"""
routers/cameras.py – Camera CRUD + start/stop live detection.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from database import cameras_collection, violations_collection
from schemas import CameraCreate
from routers.auth import get_current_user

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

# camera_manager is set by app.py at startup
camera_manager = None


def set_camera_manager(mgr):
    global camera_manager
    camera_manager = mgr


@router.get("")
async def list_cameras(user=Depends(get_current_user)):
    """Return all cameras."""
    cameras = []
    async for doc in cameras_collection.find({"user_id": str(user["_id"])}, {"_id": 0}):
        # Update status from camera manager
        if camera_manager:
            doc["status"] = camera_manager.status(doc["camera_id"])
        cameras.append(doc)
    return cameras


@router.post("")
async def create_camera(cam: CameraCreate, user=Depends(get_current_user)):
    """Create a new camera."""
    existing = await cameras_collection.find_one({"camera_id": cam.camera_id})
    if existing:
        raise HTTPException(status_code=400, detail="Camera ID already exists")

    doc = {
        "user_id": str(user["_id"]),
        "camera_id": cam.camera_id,
        "location": cam.location,
        "source": cam.source,
        "status": "stopped",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await cameras_collection.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str, user=Depends(get_current_user)):
    """Delete a camera. Stops it first if running."""
    cam = await cameras_collection.find_one({
        "camera_id": camera_id,
        "user_id": str(user["_id"]),
    })
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Stop if running
    if camera_manager and camera_manager.status(camera_id) == "running":
        camera_manager.stop(camera_id)

    await cameras_collection.delete_one({
        "camera_id": camera_id,
        "user_id": str(user["_id"]),
    })
    return {"message": f"Camera {camera_id} deleted"}


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, user=Depends(get_current_user)):
    """Start live detection for a camera."""
    cam = await cameras_collection.find_one({
        "camera_id": camera_id,
        "user_id": str(user["_id"]),
    })
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not camera_manager:
        raise HTTPException(status_code=500, detail="Camera manager not initialized")

    camera_manager.start(camera_id, cam["source"])
    await cameras_collection.update_one(
        {"camera_id": camera_id, "user_id": str(user["_id"])},
        {"$set": {"status": "running"}}
    )
    return {"message": f"Camera {camera_id} started", "status": "running"}


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, user=Depends(get_current_user)):
    """Stop live detection for a camera."""
    cam = await cameras_collection.find_one({
        "camera_id": camera_id,
        "user_id": str(user["_id"]),
    })
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    if camera_manager:
        camera_manager.stop(camera_id)

    await cameras_collection.update_one(
        {"camera_id": camera_id, "user_id": str(user["_id"])},
        {"$set": {"status": "stopped"}}
    )
    return {"message": f"Camera {camera_id} stopped", "status": "stopped"}


@router.get("/{camera_id}/status")
async def camera_status(camera_id: str, user=Depends(get_current_user)):
    """Get camera status + violation count for today."""
    cam = await cameras_collection.find_one(
        {"camera_id": camera_id, "user_id": str(user["_id"])},
        {"_id": 0},
    )
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Real-time status from manager
    if camera_manager:
        cam["status"] = camera_manager.status(camera_id)

    # Today's violation count
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    violation_count = await violations_collection.count_documents({
        "user_id": str(user["_id"]),
        "camera_id": camera_id,
        "detected_at": {"$gte": today}
    })
    cam["violation_count"] = violation_count

    return cam
