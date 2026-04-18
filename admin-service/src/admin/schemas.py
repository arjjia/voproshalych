"""Pydantic-схемы ответов admin-service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


Platform = Literal["telegram", "vk", "max"]
Period = Literal["day", "week", "month", "year"]


class PlatformCount(BaseModel):
    platform: str
    count: int


class Overview(BaseModel):
    users_total: int
    users_by_platform: list[PlatformCount]
    questions_total: int
    questions_today: int
    questions_last_month: int
    active_users_last_month: int


class TimeseriesPoint(BaseModel):
    bucket: datetime
    count: int


class Timeseries(BaseModel):
    period: Period
    platform: str | None
    points: list[TimeseriesPoint]


class Source(BaseModel):
    id: str | None
    title: str | None
    url: str | None


class QAPair(BaseModel):
    question_id: int
    answer_id: int | None
    question: str
    answer: str | None
    platform: str | None
    username: str | None
    asked_at: datetime
    model_used: str | None
    sources: list[Source] = []


class PageMeta(BaseModel):
    page: int
    size: int
    total: int


class QAPageResponse(BaseModel):
    items: list[QAPair]
    meta: PageMeta


class UserRow(BaseModel):
    id: int
    platform: str
    platform_user_id: str
    username: str | None
    first_name: str | None
    last_name: str | None
    is_subscribed: bool
    questions_count: int
    last_active_at: datetime | None
    created_at: datetime | None


class UsersPageResponse(BaseModel):
    items: list[UserRow]
    meta: PageMeta
