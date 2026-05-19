"""SQL-запросы аналитики.

Используется raw SQL через SQLAlchemy Core — для аналитических запросов
с агрегацией по времени это удобнее, чем ORM.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from admin.schemas import (
    AdminTask,
    Overview,
    PlatformCount,
    QAPair,
    Source,
    TaskReport,
    TaskReportItem,
    TaskReportSummary,
    Timeseries,
    TimeseriesPoint,
    UserRow,
)


_BUCKET_EXPR = {
    "day": "date_trunc('day', m.created_at)",
    "week": "date_trunc('week', m.created_at)",
    "month": "date_trunc('month', m.created_at)",
    "year": "date_trunc('year', m.created_at)",
}

_UNANSWERED_SQL_EXPR = """
(
    COALESCE(qa.admin_status_override, '') NOT IN ('answered', 'document_added')
    AND (
    COALESCE(qa.relevance_type = 'b', false)
    OR (
        qa.relevance_type IS NULL
        AND COALESCE(am.content ILIKE '%нет информации из официальной базы знаний%', false)
    )
    )
)
"""

_SOURCE_LINKS_JSON_EXPR = "COALESCE(qa.source_links, '[]'::jsonb)"

_NOT_CONFLUENCE_SQL_EXPR = f"""
(
    COALESCE(qa.admin_status_override, '') NOT IN ('answered', 'document_added')
    AND
    COALESCE(qa.relevance_type, '') <> 'b'
    AND (
        EXISTS (
            SELECT 1
            FROM jsonb_array_elements({_SOURCE_LINKS_JSON_EXPR}) AS source_link(link)
            WHERE source_link.link->>'url' ILIKE 'http%'
              AND source_link.link->>'url' NOT ILIKE '%confluence.utmn.ru%'
        )
        OR EXISTS (
            SELECT 1
            FROM lightrag_doc_chunks dc_warn
            WHERE am.used_chunk_ids IS NOT NULL
              AND dc_warn.id = ANY(am.used_chunk_ids)
              AND dc_warn.file_path ILIKE 'http%'
              AND dc_warn.file_path NOT ILIKE '%confluence.utmn.ru%'
        )
    )
)
"""

_SOURCES_JOIN = f"""
    LEFT JOIN LATERAL (
        SELECT json_agg(
            json_build_object(
                'id', dc.id,
                'title', COALESCE(df.doc_name, dc.file_path),
                'url', dc.file_path
            )
            ORDER BY dc.id
        ) AS sources
        FROM lightrag_doc_chunks dc
        LEFT JOIN lightrag_doc_full df
            ON df.id = dc.full_doc_id AND df.workspace = dc.workspace
        WHERE am.used_chunk_ids IS NOT NULL
          AND dc.id = ANY(am.used_chunk_ids)
    ) chunk_src ON true
    LEFT JOIN LATERAL (
        SELECT json_agg(
            json_build_object(
                'id', NULL,
                'title', COALESCE(source_link.link->>'label', source_link.link->>'url'),
                'url', source_link.link->>'url'
            )
            ORDER BY source_link.ordinality
        ) AS sources
        FROM jsonb_array_elements({_SOURCE_LINKS_JSON_EXPR})
            WITH ORDINALITY AS source_link(link, ordinality)
        WHERE source_link.link->>'url' IS NOT NULL
    ) link_src ON true
"""


def fetch_overview(db: Session) -> Overview:
    users_total = db.execute(text("SELECT count(*) FROM users")).scalar_one()

    by_platform_rows = db.execute(
        text(
            """
            SELECT platform, count(*)::int AS c
            FROM users
            GROUP BY platform
            ORDER BY c DESC
            """
        )
    ).all()

    questions_total = db.execute(
        text("SELECT count(*) FROM messages WHERE role = 'user'")
    ).scalar_one()

    questions_today = db.execute(
        text(
            """
            SELECT count(*) FROM messages
            WHERE role = 'user'
              AND created_at >= date_trunc('day', now())
            """
        )
    ).scalar_one()

    questions_month = db.execute(
        text(
            """
            SELECT count(*) FROM messages
            WHERE role = 'user'
              AND created_at >= now() - interval '30 days'
            """
        )
    ).scalar_one()

    active_users_month = db.execute(
        text(
            """
            SELECT count(DISTINCT s.user_id)
            FROM sessions s
            JOIN messages m ON m.session_id = s.id
            WHERE m.role = 'user'
              AND m.created_at >= now() - interval '30 days'
            """
        )
    ).scalar_one()

    unanswered_questions_total = db.execute(
        text(
            f"""
            SELECT count(*)
            FROM questions_answers qa
            JOIN messages qm ON qm.id = qa.question_id
            LEFT JOIN messages am ON am.id = qa.answer_id
            WHERE qm.role = 'user'
              AND {_UNANSWERED_SQL_EXPR}
            """
        )
    ).scalar_one()

    not_confluence_questions_total = db.execute(
        text(
            f"""
            SELECT count(*)
            FROM questions_answers qa
            JOIN messages qm ON qm.id = qa.question_id
            LEFT JOIN messages am ON am.id = qa.answer_id
            WHERE qm.role = 'user'
              AND {_NOT_CONFLUENCE_SQL_EXPR}
            """
        )
    ).scalar_one()

    return Overview(
        users_total=users_total,
        users_by_platform=[
            PlatformCount(platform=row.platform, count=row.c) for row in by_platform_rows
        ],
        questions_total=questions_total,
        questions_today=questions_today,
        questions_last_month=questions_month,
        unanswered_questions_total=unanswered_questions_total,
        not_confluence_questions_total=not_confluence_questions_total,
        active_users_last_month=active_users_month,
    )


def fetch_timeseries(
    db: Session,
    period: str,
    platform: Optional[str],
    days_back: int,
) -> Timeseries:
    bucket_expr = _BUCKET_EXPR[period]
    params: dict = {"days_back": days_back}

    platform_filter = ""
    if platform:
        platform_filter = "AND u.platform = :platform"
        params["platform"] = platform

    sql = text(
        f"""
        SELECT {bucket_expr} AS bucket, count(*)::int AS c
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        JOIN users u ON u.id = s.user_id
        WHERE m.role = 'user'
          AND m.created_at >= now() - (:days_back * interval '1 day')
          {platform_filter}
        GROUP BY bucket
        ORDER BY bucket
        """
    )

    rows = db.execute(sql, params).all()
    return Timeseries(
        period=period,  # type: ignore[arg-type]
        platform=platform,
        points=[TimeseriesPoint(bucket=row.bucket, count=row.c) for row in rows],
    )


def fetch_qa_pairs(
    db: Session,
    page: int,
    size: int,
    platform: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    search: Optional[str],
    status: Optional[str],
) -> tuple[list[QAPair], int]:
    offset = (page - 1) * size
    params: dict = {"limit": size, "offset": offset}
    filters = ["qm.role = 'user'"]

    if platform:
        filters.append("u.platform = :platform")
        params["platform"] = platform
    if date_from:
        filters.append("qm.created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("qm.created_at <= :date_to")
        params["date_to"] = date_to
    if search:
        filters.append("(qm.content ILIKE :search OR am.content ILIKE :search)")
        params["search"] = f"%{search}%"
    if status == "unanswered":
        filters.append(_UNANSWERED_SQL_EXPR)
    elif status == "not_confluence":
        filters.append(_NOT_CONFLUENCE_SQL_EXPR)
    elif status == "answered":
        filters.append("COALESCE(qa.admin_status_override, '') <> 'document_added'")
        filters.append(f"NOT {_UNANSWERED_SQL_EXPR}")
        filters.append(f"NOT {_NOT_CONFLUENCE_SQL_EXPR}")
    elif status == "document_added":
        filters.append("qa.admin_status_override = 'document_added'")

    where_clause = "WHERE " + " AND ".join(filters)

    from_clause = """
        FROM questions_answers qa
        JOIN messages qm ON qm.id = qa.question_id
        LEFT JOIN messages am ON am.id = qa.answer_id
        JOIN sessions s ON s.id = qm.session_id
        JOIN users u ON u.id = s.user_id
        LEFT JOIN admin_tasks t
            ON t.question_id = qa.question_id
           AND t.archived_at IS NULL
    """

    total = db.execute(
        text(f"SELECT count(*) {from_clause} {where_clause}"), params
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT
                qm.id AS question_id,
                am.id AS answer_id,
                qm.content AS question,
                am.content AS answer,
                u.platform AS platform,
                qm.created_at AS asked_at,
                am.model_used AS model_used,
                {_UNANSWERED_SQL_EXPR} AS is_unanswered,
                {_NOT_CONFLUENCE_SQL_EXPR} AS is_not_confluence,
                qa.admin_status_override = 'document_added' AS is_document_added,
                t.id AS task_id,
                t.status AS task_status,
                COALESCE(chunk_src.sources, link_src.sources, '[]'::json) AS sources
            {from_clause}
            {_SOURCES_JOIN}
            {where_clause}
            ORDER BY qm.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()

    items = [
        QAPair(
            question_id=row.question_id,
            answer_id=row.answer_id,
            question=row.question,
            answer=row.answer,
            platform=row.platform,
            asked_at=row.asked_at,
            model_used=row.model_used,
            is_unanswered=bool(row.is_unanswered),
            is_not_confluence=bool(row.is_not_confluence),
            is_document_added=bool(row.is_document_added),
            task_id=row.task_id,
            task_status=row.task_status,
            sources=[Source(**s) for s in (row.sources or [])],
        )
        for row in rows
    ]
    return items, int(total)


def mark_qa_false_positive(db: Session, question_id: int) -> bool:
    result = db.execute(
        text(
            """
            UPDATE questions_answers
            SET admin_status_override = 'answered'
            WHERE question_id = :question_id
            """
        ),
        {"question_id": question_id},
    )
    db.execute(
        text(
            """
            DELETE FROM admin_tasks
            WHERE question_id = :question_id
              AND archived_at IS NULL
            """
        ),
        {"question_id": question_id},
    )
    db.commit()
    return bool(result.rowcount)


def create_admin_task(db: Session, question_id: int) -> AdminTask | None:
    db.execute(
        text(
            """
            INSERT INTO admin_tasks (question_id, answer_id)
            SELECT qa.question_id, qa.answer_id
            FROM questions_answers qa
            WHERE qa.question_id = :question_id
            ON CONFLICT (question_id) DO UPDATE
            SET updated_at = admin_tasks.updated_at
            """
        ),
        {"question_id": question_id},
    )
    db.commit()
    return fetch_admin_task_by_question(db, question_id)


def update_admin_task_status(db: Session, task_id: int, status: str) -> AdminTask | None:
    result = db.execute(
        text(
            """
            UPDATE admin_tasks
            SET status = :status,
                updated_at = now()
            WHERE id = :task_id
              AND archived_at IS NULL
            """
        ),
        {"task_id": task_id, "status": status},
    )
    if not result.rowcount:
        db.commit()
        return None
    if status == "done":
        db.execute(
            text(
                """
                UPDATE questions_answers qa
                SET admin_status_override = 'document_added'
                FROM admin_tasks t
                WHERE t.id = :task_id
                  AND t.archived_at IS NULL
                  AND qa.question_id = t.question_id
                """
            ),
            {"task_id": task_id},
        )
    else:
        db.execute(
            text(
                """
                UPDATE questions_answers qa
                SET admin_status_override = NULL
                FROM admin_tasks t
                WHERE t.id = :task_id
                  AND t.archived_at IS NULL
                  AND qa.question_id = t.question_id
                  AND qa.admin_status_override = 'document_added'
                """
            ),
            {"task_id": task_id},
        )
    db.commit()
    return fetch_admin_task(db, task_id)


def delete_admin_task(db: Session, task_id: int) -> bool:
    db.execute(
        text(
            """
            UPDATE questions_answers qa
            SET admin_status_override = NULL
            FROM admin_tasks t
            WHERE t.id = :task_id
              AND t.archived_at IS NULL
              AND qa.question_id = t.question_id
              AND qa.admin_status_override = 'document_added'
            """
        ),
        {"task_id": task_id},
    )
    result = db.execute(
        text("DELETE FROM admin_tasks WHERE id = :task_id AND archived_at IS NULL"),
        {"task_id": task_id},
    )
    db.commit()
    return bool(result.rowcount)


def fetch_admin_task(db: Session, task_id: int) -> AdminTask | None:
    rows = _fetch_admin_tasks(db, "WHERE t.id = :task_id", {"task_id": task_id})
    return rows[0] if rows else None


def fetch_admin_task_by_question(db: Session, question_id: int) -> AdminTask | None:
    rows = _fetch_admin_tasks(
        db,
        "WHERE t.question_id = :question_id",
        {"question_id": question_id},
    )
    return rows[0] if rows else None


def fetch_admin_tasks(db: Session) -> list[AdminTask]:
    return _fetch_admin_tasks(db, "WHERE t.archived_at IS NULL", {})


def create_task_report(db: Session) -> TaskReport | None:
    locked_task_rows = db.execute(
        text(
            """
            SELECT id
            FROM admin_tasks
            WHERE status = 'done'
              AND archived_at IS NULL
            ORDER BY updated_at DESC, id DESC
            FOR UPDATE SKIP LOCKED
            """
        )
    ).all()
    if not locked_task_rows:
        return None

    task_id_params = {f"task_id_{index}": row.id for index, row in enumerate(locked_task_rows)}
    task_ids_clause = ", ".join(f":{key}" for key in task_id_params)

    report_id = db.execute(
        text(
            """
            INSERT INTO admin_task_reports (tasks_count)
            VALUES (:tasks_count)
            RETURNING id
            """
        ),
        {"tasks_count": len(locked_task_rows)},
    ).scalar_one()

    db.execute(
        text(
            f"""
            INSERT INTO admin_task_report_items (
                report_id,
                task_id,
                question_id,
                answer_id,
                question,
                answer,
                platform,
                platform_user_id,
                username,
                first_name,
                last_name,
                asked_at,
                model_used,
                sources
            )
            SELECT
                :report_id,
                t.id,
                qm.id,
                am.id,
                qm.content,
                am.content,
                u.platform,
                u.platform_user_id,
                u.username,
                u.first_name,
                u.last_name,
                qm.created_at,
                am.model_used,
                COALESCE(chunk_src.sources, link_src.sources, '[]'::json)::jsonb
            FROM admin_tasks t
            JOIN messages qm ON qm.id = t.question_id
            LEFT JOIN messages am ON am.id = t.answer_id
            JOIN sessions s ON s.id = qm.session_id
            JOIN users u ON u.id = s.user_id
            LEFT JOIN questions_answers qa ON qa.question_id = t.question_id
            {_SOURCES_JOIN}
            WHERE t.id IN ({task_ids_clause})
            ORDER BY t.updated_at DESC
            """
        ),
        {"report_id": report_id, **task_id_params},
    )
    db.execute(
        text(
            f"""
            UPDATE questions_answers qa
            SET admin_status_override = 'document_added'
            FROM admin_tasks t
            WHERE t.id IN ({task_ids_clause})
              AND qa.question_id = t.question_id
            """
        ),
        task_id_params,
    )
    db.execute(
        text(
            f"""
            UPDATE admin_tasks
            SET archived_at = now(),
                report_id = :report_id,
                updated_at = now()
            WHERE id IN ({task_ids_clause})
            """
        ),
        {"report_id": report_id, **task_id_params},
    )
    db.commit()
    return fetch_task_report(db, report_id)


def fetch_task_report(db: Session, report_id: int) -> TaskReport | None:
    reports = _fetch_task_reports(db, "WHERE r.id = :report_id", {"report_id": report_id})
    return reports[0] if reports else None


def fetch_task_reports(db: Session, page: int, size: int) -> tuple[list[TaskReportSummary], int]:
    offset = (page - 1) * size
    total = db.execute(text("SELECT count(*) FROM admin_task_reports")).scalar_one()
    rows = db.execute(
        text(
            """
            SELECT id, created_at, tasks_count
            FROM admin_task_reports
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": size, "offset": offset},
    ).all()
    return [
        TaskReportSummary(
            id=row.id,
            created_at=row.created_at,
            tasks_count=row.tasks_count,
        )
        for row in rows
    ], int(total)


def restore_task_report_item(db: Session, item_id: int) -> AdminTask | None:
    item = db.execute(
        text(
            """
            SELECT task_id, question_id, answer_id, restored_task_id, restored_at
            FROM admin_task_report_items
            WHERE id = :item_id
            """
        ),
        {"item_id": item_id},
    ).one_or_none()
    if item is None:
        return None

    if item.restored_at is not None and item.restored_task_id is not None:
        restored_task = fetch_admin_task(db, item.restored_task_id)
        if restored_task is not None:
            return restored_task

    if item.task_id is not None:
        updated_task_id = db.execute(
            text(
                """
                UPDATE admin_tasks
                SET status = 'added',
                    archived_at = NULL,
                    report_id = NULL,
                    updated_at = now()
                WHERE id = :task_id
                RETURNING id
                """
            ),
            {"task_id": item.task_id},
        ).scalar_one_or_none()
        task_id = updated_task_id
    else:
        task_id = None

    if task_id is None:
        task_id = db.execute(
            text(
                """
                INSERT INTO admin_tasks (question_id, answer_id, status)
                VALUES (:question_id, :answer_id, 'added')
                ON CONFLICT (question_id) DO UPDATE
                SET answer_id = EXCLUDED.answer_id,
                    status = 'added',
                    archived_at = NULL,
                    report_id = NULL,
                    updated_at = now()
                RETURNING id
                """
            ),
            {"question_id": item.question_id, "answer_id": item.answer_id},
        ).scalar_one()

    db.execute(
        text(
            """
            UPDATE questions_answers
            SET admin_status_override = NULL
            WHERE question_id = :question_id
              AND admin_status_override = 'document_added'
            """
        ),
        {"question_id": item.question_id},
    )
    db.execute(
        text(
            """
            UPDATE admin_task_report_items
            SET restored_at = COALESCE(restored_at, now()),
                restored_task_id = :task_id,
                task_id = COALESCE(task_id, :task_id)
            WHERE id = :item_id
            """
        ),
        {"task_id": task_id, "item_id": item_id},
    )
    db.commit()
    return fetch_admin_task(db, task_id)


def _fetch_admin_tasks(db: Session, where_clause: str, params: dict) -> list[AdminTask]:
    rows = db.execute(
        text(
            f"""
            SELECT
                t.id AS id,
                qm.id AS question_id,
                am.id AS answer_id,
                qm.content AS question,
                am.content AS answer,
                u.platform AS platform,
                qm.created_at AS asked_at,
                am.model_used AS model_used,
                t.status AS status,
                {_UNANSWERED_SQL_EXPR} AS is_unanswered,
                {_NOT_CONFLUENCE_SQL_EXPR} AS is_not_confluence,
                qa.admin_status_override = 'document_added' AS is_document_added,
                COALESCE(chunk_src.sources, link_src.sources, '[]'::json) AS sources,
                t.created_at AS created_at,
                t.updated_at AS updated_at
            FROM admin_tasks t
            JOIN messages qm ON qm.id = t.question_id
            LEFT JOIN messages am ON am.id = t.answer_id
            JOIN sessions s ON s.id = qm.session_id
            JOIN users u ON u.id = s.user_id
            LEFT JOIN questions_answers qa ON qa.question_id = t.question_id
            {_SOURCES_JOIN}
            {where_clause}
            ORDER BY
                CASE t.status
                    WHEN 'added' THEN 1
                    WHEN 'in_progress' THEN 2
                    WHEN 'on_hold' THEN 3
                    WHEN 'done' THEN 4
                    ELSE 5
                END,
                t.updated_at DESC
            """
        ),
        params,
    ).all()

    return [
        AdminTask(
            id=row.id,
            question_id=row.question_id,
            answer_id=row.answer_id,
            question=row.question,
            answer=row.answer,
            platform=row.platform,
            asked_at=row.asked_at,
            model_used=row.model_used,
            status=row.status,
            is_unanswered=bool(row.is_unanswered),
            is_not_confluence=bool(row.is_not_confluence),
            is_document_added=bool(row.is_document_added),
            sources=[Source(**s) for s in (row.sources or [])],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def _fetch_task_reports(
    db: Session,
    where_clause: str,
    params: dict,
    limit_clause: str = "",
) -> list[TaskReport]:
    rows = db.execute(
        text(
            f"""
            SELECT
                r.id,
                r.created_at,
                r.tasks_count,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', ri.id,
                            'task_id', ri.task_id,
                            'question_id', ri.question_id,
                            'answer_id', ri.answer_id,
                            'question', ri.question,
                            'answer', ri.answer,
                            'platform', ri.platform,
                            'asked_at', ri.asked_at,
                            'model_used', ri.model_used,
                            'sources', ri.sources,
                            'created_at', ri.created_at,
                            'restored_at', ri.restored_at,
                            'restored_task_id', ri.restored_task_id
                        )
                        ORDER BY ri.created_at DESC, ri.id DESC
                    ) FILTER (WHERE ri.id IS NOT NULL),
                    '[]'::json
                ) AS items
            FROM admin_task_reports r
            LEFT JOIN admin_task_report_items ri ON ri.report_id = r.id
            {where_clause}
            GROUP BY r.id, r.created_at, r.tasks_count
            ORDER BY r.created_at DESC, r.id DESC
            {limit_clause}
            """
        ),
        params,
    ).all()

    return [
        TaskReport(
            id=row.id,
            created_at=row.created_at,
            tasks_count=row.tasks_count,
            items=[
                TaskReportItem(
                    id=item["id"],
                    task_id=item["task_id"],
                    question_id=item["question_id"],
                    answer_id=item["answer_id"],
                    question=item["question"],
                    answer=item["answer"],
                    platform=item["platform"],
                    asked_at=item["asked_at"],
                    model_used=item["model_used"],
                    sources=[Source(**source) for source in (item["sources"] or [])],
                    created_at=item["created_at"],
                    restored_at=item["restored_at"],
                    restored_task_id=item["restored_task_id"],
                )
                for item in (row.items or [])
            ],
        )
        for row in rows
    ]


def fetch_users(
    db: Session,
    page: int,
    size: int,
    platform: Optional[str],
    search: Optional[str],
) -> tuple[list[UserRow], int]:
    offset = (page - 1) * size
    params: dict = {"limit": size, "offset": offset}
    filters: list[str] = []

    if platform:
        filters.append("u.platform = :platform")
        params["platform"] = platform
    if search:
        filters.append(
            "(u.username ILIKE :search OR u.first_name ILIKE :search "
            "OR u.last_name ILIKE :search OR u.platform_user_id ILIKE :search)"
        )
        params["search"] = f"%{search}%"

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    total = db.execute(
        text(f"SELECT count(*) FROM users u {where}"), params
    ).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT
                u.id,
                u.platform,
                u.platform_user_id,
                u.username,
                u.first_name,
                u.last_name,
                u.is_subscribed,
                u.created_at,
                COALESCE(stats.questions_count, 0)::int AS questions_count,
                stats.last_active_at
            FROM users u
            LEFT JOIN (
                SELECT s.user_id,
                       count(*) AS questions_count,
                       max(m.created_at) AS last_active_at
                FROM sessions s
                JOIN messages m ON m.session_id = s.id
                WHERE m.role = 'user'
                GROUP BY s.user_id
            ) stats ON stats.user_id = u.id
            {where}
            ORDER BY stats.last_active_at DESC NULLS LAST, u.id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()

    items = [
        UserRow(
            id=row.id,
            platform=row.platform,
            platform_user_id=row.platform_user_id,
            username=row.username,
            first_name=row.first_name,
            last_name=row.last_name,
            is_subscribed=bool(row.is_subscribed),
            questions_count=row.questions_count,
            last_active_at=row.last_active_at,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return items, int(total)
