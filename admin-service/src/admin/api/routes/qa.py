"""Эндпоинты пар вопрос-ответ."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from admin.db import get_db
from admin.queries import fetch_qa_pairs, mark_qa_false_positive
from admin.schemas import PageMeta, Platform, QAPageResponse, QAStatus, TaskActionResponse


router = APIRouter(prefix="/qa", tags=["qa"])


@router.get("/pairs", response_model=QAPageResponse)
def pairs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    platform: Optional[Platform] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    status: Optional[QAStatus] = None,
    db: Session = Depends(get_db),
) -> QAPageResponse:
    items, total = fetch_qa_pairs(
        db,
        page,
        size,
        platform,
        date_from,
        date_to,
        search,
        status,
    )
    return QAPageResponse(items=items, meta=PageMeta(page=page, size=size, total=total))


@router.post("/pairs/{question_id}/false-positive", response_model=TaskActionResponse)
def false_positive(
    question_id: int,
    db: Session = Depends(get_db),
) -> TaskActionResponse:
    return TaskActionResponse(ok=mark_qa_false_positive(db, question_id))
