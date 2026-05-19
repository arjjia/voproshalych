"""Эндпоинты задач админ-панели."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from admin.db import get_db
from admin.queries import (
    create_admin_task,
    create_task_report,
    delete_admin_task,
    fetch_admin_tasks,
    fetch_task_report,
    fetch_task_reports,
    restore_task_report_item,
    update_admin_task_status,
)
from admin.schemas import (
    AdminTask,
    CreateTaskRequest,
    PageMeta,
    TaskActionResponse,
    TaskReport,
    TaskReportsResponse,
    TasksResponse,
    UpdateTaskStatusRequest,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TasksResponse)
def list_tasks(db: Session = Depends(get_db)) -> TasksResponse:
    return TasksResponse(items=fetch_admin_tasks(db))


@router.get("/reports", response_model=TaskReportsResponse)
def list_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TaskReportsResponse:
    items, total = fetch_task_reports(db, page, size)
    return TaskReportsResponse(items=items, meta=PageMeta(page=page, size=size, total=total))


@router.post("/reports", response_model=TaskReport)
def create_report(db: Session = Depends(get_db)) -> TaskReport:
    report = create_task_report(db)
    if report is None:
        raise HTTPException(status_code=400, detail="No done tasks to archive")
    return report


@router.get("/reports/{report_id}", response_model=TaskReport)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
) -> TaskReport:
    report = fetch_task_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/reports/items/{item_id}/restore", response_model=AdminTask)
def restore_report_item(
    item_id: int,
    db: Session = Depends(get_db),
) -> AdminTask:
    task = restore_task_report_item(db, item_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Report item not found")
    return task


@router.post("", response_model=AdminTask)
def create_task(
    request: CreateTaskRequest,
    db: Session = Depends(get_db),
) -> AdminTask:
    task = create_admin_task(db, request.question_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return task


@router.patch("/{task_id}/status", response_model=AdminTask)
def update_task_status(
    task_id: int,
    request: UpdateTaskStatusRequest,
    db: Session = Depends(get_db),
) -> AdminTask:
    task = update_admin_task_status(db, task_id, request.status)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", response_model=TaskActionResponse)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
) -> TaskActionResponse:
    return TaskActionResponse(ok=delete_admin_task(db, task_id))
