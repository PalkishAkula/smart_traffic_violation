"""
routers/stats.py – Dashboard summary + timeline stats.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query, Depends

from database import violations_collection, cameras_collection
from routers.auth import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
async def get_summary(user=Depends(get_current_user)):
    """Return dashboard summary stats."""
    user_id = str(user["_id"])
    # Total violations
    total_violations = await violations_collection.count_documents({"user_id": user_id})

    # Today's violations
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    today_violations = await violations_collection.count_documents({
        "user_id": user_id,
        "detected_at": {"$gte": today}
    })

    # Camera counts
    cameras_total = await cameras_collection.count_documents({"user_id": user_id})

    # Active cameras — count by checking status field
    cameras_active = await cameras_collection.count_documents({"user_id": user_id, "status": "running"})

    # Breakdown by violation type
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$violation_type", "count": {"$sum": 1}}}
    ]
    by_type = {}
    async for doc in violations_collection.aggregate(pipeline):
        by_type[doc["_id"]] = doc["count"]

    # Recent 5 violations
    recent = []
    cursor = (violations_collection
              .find({"user_id": user_id})
              .sort("detected_at", -1)
              .limit(5))
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        recent.append(doc)

    return {
        "total_violations": total_violations,
        "today_violations": today_violations,
        "cameras_active": cameras_active,
        "cameras_total": cameras_total,
        "by_type": by_type,
        "recent_violations": recent,
    }


@router.get("/timeline")
async def get_timeline(days: int = Query(7, ge=1, le=90), user=Depends(get_current_user)):
    """Return daily violation counts for the last N days."""
    user_id = str(user["_id"])
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Build date range
    data = []
    for i in range(days):
        day = start + timedelta(days=i)
        day_start = day.isoformat()
        day_end = (day + timedelta(days=1)).isoformat()

        count = await violations_collection.count_documents({
            "user_id": user_id,
            "detected_at": {"$gte": day_start, "$lt": day_end}
        })
        data.append({
            "date": day.strftime("%Y-%m-%d"),
            "count": count,
        })

    return {"data": data}
