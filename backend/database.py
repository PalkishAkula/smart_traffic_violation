"""
database.py – Motor async MongoDB client, collection references, indexes.
Uses MongoDB (not PostgreSQL) per project requirements.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "violations_db"

client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]

# Collection references
users_collection = db["users"]
cameras_collection = db["cameras"]
violations_collection = db["violations"]


async def create_indexes():
    """Create indexes for fast lookups. Called once on app startup."""
    await users_collection.create_index("email", unique=True)
    await cameras_collection.create_index("camera_id", unique=True)
    await cameras_collection.create_index("user_id")
    await violations_collection.create_index("camera_id")
    await violations_collection.create_index("user_id")
    await violations_collection.create_index("violation_type")
    await violations_collection.create_index("detected_at")
    await violations_collection.create_index("plate_text")
