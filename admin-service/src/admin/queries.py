"""SQL-запросы аналитики.

Используется raw SQL через SQLAlchemy Core — для аналитических запросов
с агрегацией по времени это удобнее, чем ORM.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from admin.schemas import (
    Overview,
    PlatformCount,
    QAPair,
    Source,
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

    return Overview(
        users_total=users_total,
        users_by_platform=[
            PlatformCount(platform=row.platform, count=row.c) for row in by_platform_rows
        ],
        questions_total=questions_total,
        questions_today=questions_today,
        questions_last_month=questions_month,
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

    where_clause = "WHERE " + " AND ".join(filters)

    from_clause = """
        FROM questions_answers qa
        JOIN messages qm ON qm.id = qa.question_id
        LEFT JOIN messages am ON am.id = qa.answer_id
        JOIN sessions s ON s.id = qm.session_id
        JOIN users u ON u.id = s.user_id
    """

    total = db.execute(
        text(f"SELECT count(*) {from_clause} {where_clause}"), params
    ).scalar_one()

    sources_join = """
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
        ) src ON true
    """

    rows = db.execute(
        text(
            f"""
            SELECT
                qm.id AS question_id,
                am.id AS answer_id,
                qm.content AS question,
                am.content AS answer,
                u.platform AS platform,
                u.username AS username,
                qm.created_at AS asked_at,
                am.model_used AS model_used,
                COALESCE(src.sources, '[]'::json) AS sources
            {from_clause}
            {sources_join}
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
            username=row.username,
            asked_at=row.asked_at,
            model_used=row.model_used,
            sources=[Source(**s) for s in (row.sources or [])],
        )
        for row in rows
    ]
    return items, int(total)


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
