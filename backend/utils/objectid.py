from __future__ import annotations

from bson import ObjectId


def to_object_id(value: str | ObjectId | None):
    if value is None:
        raise ValueError("ObjectId value is required")
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str):
        if not ObjectId.is_valid(value):
            raise ValueError(f"Invalid ObjectId: {value}")
        return ObjectId(value)
    raise TypeError(f"Unsupported ObjectId type: {type(value)}")


def to_string_id(value: ObjectId | str | None) -> str | None:
    if value is None:
        return None
    return str(value)
