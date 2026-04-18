"""Эндпоинты пар вопрос-ответ."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from admin.db import get_db
from admin.queries import fetch_qa_pairs
from admin.schemas import PageMeta, Platform, QAPageResponse


router = APIRouter(prefix="/qa", tags=["qa"])


@router.get("/pairs", response_model=QAPageResponse)
def pairs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    platform: Optional[Platform] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> QAPageResponse:
    items, total = fetch_qa_pairs(db, page, size, platform, date_from, date_to, search)
    return QAPageResponse(items=items, meta=PageMeta(page=page, size=size, total=total))
