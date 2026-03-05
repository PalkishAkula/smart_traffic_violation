"""
routers/violations.py – Paginated + filtered violations list, detail, delete.
"""

import math
import re
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional

from database import violations_collection
from cloudinary_service import delete_image
from routers.auth import get_current_user

router = APIRouter(prefix="/api/violations", tags=["violations"])


@router.get("")
async def list_violations(
    user=Depends(get_current_user),
    camera_id: Optional[str] = Query(None),
    violation_type: Optional[str] = Query(None),
    plate_text: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Return paginated + filtered violations."""
    query = {"user_id": str(user["_id"])}

    if camera_id:
        query["camera_id"] = camera_id

    if violation_type:
        query["violation_type"] = violation_type

    if plate_text:
        if plate_text.upper() == "UNDETECTED":
            query["plate_text"] = None
        else:
            query["plate_text"] = {"$regex": plate_text, "$options": "i"}

    if date_from or date_to:
        date_q = {}
        if date_from:
            date_q["$gte"] = date_from
        if date_to:
            date_q["$lte"] = date_to
        query["detected_at"] = date_q

    total = await violations_collection.count_documents(query)
    pages = max(1, math.ceil(total / per_page))
    skip = (page - 1) * per_page

    items = []
    cursor = (violations_collection
              .find(query)
              .sort("detected_at", -1)
              .skip(skip)
              .limit(per_page))

    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        items.append(doc)

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
    }


@router.get("/{violation_id}")
async def get_violation(violation_id: str, user=Depends(get_current_user)):
    """Return single violation record."""
    from bson import ObjectId
    try:
        doc = await violations_collection.find_one({
            "_id": ObjectId(violation_id),
            "user_id": str(user["_id"]),
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid violation ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Violation not found")

    doc["id"] = str(doc.pop("_id"))
    return doc


@router.delete("/{violation_id}")
async def delete_violation(violation_id: str, user=Depends(get_current_user)):
    """Delete a violation and its Cloudinary image."""
    from bson import ObjectId
    try:
        doc = await violations_collection.find_one({
            "_id": ObjectId(violation_id),
            "user_id": str(user["_id"]),
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid violation ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Violation not found")

    # Delete Cloudinary image if exists
    cloudinary_id = doc.get("cloudinary_id")
    if cloudinary_id:
        delete_image(cloudinary_id)

    await violations_collection.delete_one({
        "_id": ObjectId(violation_id),
        "user_id": str(user["_id"]),
    })
    return {"message": "Violation deleted"}
