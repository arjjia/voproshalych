"""Pydantic-схемы ответов admin-service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


Platform = Literal["telegram", "vk", "max"]
Period = Literal["day", "week", "month", "year"]
QAStatus = Literal["answered", "unanswered", "not_confluence", "document_added"]
TaskStatus = Literal["added", "in_progress", "done", "on_hold"]


class PlatformCount(BaseModel):
    platform: str
    count: int


class Overview(BaseModel):
    users_total: int
    users_by_platform: list[PlatformCount]
    questions_total: int
    questions_today: int
    questions_last_month: int
    unanswered_questions_total: int
    not_confluence_questions_total: int
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
    asked_at: datetime
    model_used: str | None
    is_unanswered: bool = False
    is_not_confluence: bool = False
    is_document_added: bool = False
    task_id: int | None = None
    task_status: TaskStatus | None = None
    sources: list[Source] = []


class PageMeta(BaseModel):
    page: int
    size: int
    total: int


class QAPageResponse(BaseModel):
    items: list[QAPair]
    meta: PageMeta


class AdminTask(BaseModel):
    id: int
    question_id: int
    answer_id: int | None
    question: str
    answer: str | None
    platform: str | None
    asked_at: datetime
    model_used: str | None
    status: TaskStatus
    is_unanswered: bool = False
    is_not_confluence: bool = False
    is_document_added: bool = False
    sources: list[Source] = []
    created_at: datetime
    updated_at: datetime


class TasksResponse(BaseModel):
    items: list[AdminTask]


class TaskReportItem(BaseModel):
    id: int
    task_id: int | None
    question_id: int
    answer_id: int | None
    question: str
    answer: str | None
    platform: str | None
    asked_at: datetime
    model_used: str | None
    sources: list[Source] = []
    created_at: datetime
    restored_at: datetime | None = None
    restored_task_id: int | None = None


class TaskReport(BaseModel):
    id: int
    created_at: datetime
    tasks_count: int
    items: list[TaskReportItem] = []


class TaskReportSummary(BaseModel):
    id: int
    created_at: datetime
    tasks_count: int


class TaskReportsResponse(BaseModel):
    items: list[TaskReportSummary]
    meta: PageMeta


class CreateTaskRequest(BaseModel):
    question_id: int


class UpdateTaskStatusRequest(BaseModel):
    status: TaskStatus


class TaskActionResponse(BaseModel):
    ok: bool


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
