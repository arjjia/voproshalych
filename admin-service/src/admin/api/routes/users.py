"""Эндпоинты пользователей."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from admin.db import get_db
from admin.queries import fetch_users
from admin.schemas import PageMeta, Platform, UsersPageResponse


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UsersPageResponse)
def users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    platform: Optional[Platform] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> UsersPageResponse:
    items, total = fetch_users(db, page, size, platform, search)
    return UsersPageResponse(
        items=items, meta=PageMeta(page=page, size=size, total=total)
    )
