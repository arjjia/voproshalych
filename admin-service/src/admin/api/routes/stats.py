"""Аналитические эндпоинты."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from admin.db import get_db
from admin.queries import fetch_overview, fetch_timeseries
from admin.schemas import Overview, Period, Platform, Timeseries


router = APIRouter(prefix="/stats", tags=["stats"])


_DEFAULT_DAYS_BACK = {
    "day": 30,
    "week": 180,
    "month": 365,
    "year": 365 * 5,
}


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)) -> Overview:
    return fetch_overview(db)


@router.get("/questions-timeseries", response_model=Timeseries)
def questions_timeseries(
    period: Period = Query("day"),
    platform: Optional[Platform] = Query(None),
    days_back: Optional[int] = Query(None, ge=1, le=3650),
    db: Session = Depends(get_db),
) -> Timeseries:
    effective_days_back = days_back or _DEFAULT_DAYS_BACK[period]
    return fetch_timeseries(db, period, platform, effective_days_back)
