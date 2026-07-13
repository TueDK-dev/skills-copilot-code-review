"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementBase(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    start_date: Optional[datetime] = None
    expiration_date: datetime


class AnnouncementCreate(AnnouncementBase):
    pass


class AnnouncementUpdate(AnnouncementBase):
    pass


def _require_authenticated_user(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _validate_announcement_dates(start_date: Optional[datetime], expiration_date: datetime) -> None:
    if start_date and expiration_date <= start_date:
        raise HTTPException(
            status_code=400,
            detail="Expiration date must be later than start date"
        )


def _sanitize_message(message: str) -> str:
    cleaned = message.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    return cleaned


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "message": doc["message"],
        "start_date": doc.get("start_date").isoformat() if doc.get("start_date") else None,
        "expiration_date": doc["expiration_date"].isoformat(),
        "created_by": doc.get("created_by"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)

    query = {
        "expiration_date": {"$gt": now},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": {"$lte": now}}
        ]
    }

    docs = announcements_collection.find(query).sort("expiration_date", 1)
    return [_serialize_announcement(doc) for doc in docs]


@router.get("", response_model=List[Dict[str, Any]])
def list_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    _require_authenticated_user(teacher_username)

    docs = announcements_collection.find({}).sort("updated_at", -1)
    return [_serialize_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementCreate,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    teacher = _require_authenticated_user(teacher_username)
    _validate_announcement_dates(payload.start_date, payload.expiration_date)
    message = _sanitize_message(payload.message)

    now = datetime.now(timezone.utc)
    document = {
        "message": message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
        "created_by": teacher["_id"],
        "created_at": now,
        "updated_at": now
    }

    result = announcements_collection.insert_one(document)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return _serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdate,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    _require_authenticated_user(teacher_username)
    _validate_announcement_dates(payload.start_date, payload.expiration_date)
    message = _sanitize_message(payload.message)

    try:
        object_id = ObjectId(announcement_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "message": message,
                "start_date": payload.start_date,
                "expiration_date": payload.expiration_date,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": object_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    _require_authenticated_user(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
