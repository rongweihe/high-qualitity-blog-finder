from __future__ import annotations

from math import ceil
from typing import Any, Dict, List, Tuple

from .database import get_connection


MAJOR_TABS = [
    ("", "全部"),
    ("ai", "AI"),
    ("agent", "Agent"),
    ("fullstack", "全栈"),
    ("backend", "后端"),
    ("frontend", "前端"),
    ("indie", "独立开发"),
    ("crypto", "加密货币"),
    ("trading", "交易套利"),
    ("infra", "工程基础设施"),
    ("opensource", "开源"),
]


def _build_filters(tag: str = "", query: str = "") -> Tuple[str, List[Any]]:
    filters = ["b.status != 'hidden'"]
    params: List[Any] = []

    if tag:
        filters.append(
            """
            EXISTS (
              SELECT 1
              FROM blogger_tags fbt
              JOIN tags ft ON ft.id = fbt.tag_id
              WHERE fbt.blogger_id = b.id AND ft.slug = ?
            )
            """
        )
        params.append(tag)

    if query:
        like_query = f"%{query.strip()}%"
        filters.append(
            """
            (
              b.name LIKE ?
              OR b.site_name LIKE ?
              OR b.description LIKE ?
              OR b.site_url LIKE ?
              OR EXISTS (
                SELECT 1
                FROM blogger_tags qbt
                JOIN tags qt ON qt.id = qbt.tag_id
                WHERE qbt.blogger_id = b.id
                  AND (qt.name LIKE ? OR qt.slug LIKE ?)
              )
            )
            """
        )
        params.extend([like_query, like_query, like_query, like_query, like_query, like_query])

    return " AND ".join(filters), params


def _sort_clause(sort: str) -> str:
    if sort == "recent":
        return "b.last_post_at IS NULL ASC, b.last_post_at DESC, b.quality_score DESC"
    if sort == "name":
        return "b.site_name COLLATE NOCASE ASC, b.quality_score DESC"
    return "b.quality_score DESC, b.last_post_at IS NULL ASC, b.last_post_at DESC, b.site_name ASC"


def _row_to_blogger(row: Any) -> Dict[str, Any]:
    tags = []
    if row["tags_compact"]:
        for tag_item in row["tags_compact"].split("||"):
            slug, name, group_name = tag_item.split("::", 2)
            tags.append({"slug": slug, "name": name, "group_name": group_name})

    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "site_name": row["site_name"],
        "site_url": row["site_url"],
        "description": row["description"],
        "thumbnail_url": row["thumbnail_url"],
        "rss_url": row["rss_url"],
        "github_url": row["github_url"],
        "twitter_url": row["twitter_url"],
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "status": row["status"],
        "site_status_code": row["site_status_code"],
        "recency_source": row["recency_source"],
        "last_checked_at": row["last_checked_at"],
        "quality_score": row["quality_score"],
        "last_post_at": row["last_post_at"],
        "tags": tags,
    }


def list_bloggers(
    tag: str = "",
    query: str = "",
    page: int = 1,
    page_size: int = 24,
    sort: str = "quality",
) -> Tuple[List[Dict[str, Any]], int]:
    where_sql, params = _build_filters(tag=tag, query=query)
    offset = (page - 1) * page_size

    with get_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(DISTINCT b.id) AS count FROM bloggers b WHERE {where_sql}",
            params,
        ).fetchone()["count"]

        rows = conn.execute(
            f"""
            SELECT
              b.*,
              GROUP_CONCAT(t.slug || '::' || t.name || '::' || t.group_name, '||') AS tags_compact
            FROM bloggers b
            LEFT JOIN blogger_tags bt ON bt.blogger_id = b.id
            LEFT JOIN tags t ON t.id = bt.tag_id
            WHERE {where_sql}
            GROUP BY b.id
            ORDER BY {_sort_clause(sort)}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    return [_row_to_blogger(row) for row in rows], int(total)


def get_tag_counts() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
              t.slug,
              t.name,
              t.group_name,
              t.display_order,
              COUNT(DISTINCT CASE WHEN b.status != 'hidden' THEN b.id END) AS count
            FROM tags t
            LEFT JOIN blogger_tags bt ON bt.tag_id = t.id
            LEFT JOIN bloggers b ON b.id = bt.blogger_id
            GROUP BY t.id
            ORDER BY t.display_order ASC, t.name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_stats() -> Dict[str, int]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN status = 'candidate' THEN 1 ELSE 0 END) AS candidate,
              SUM(CASE WHEN last_checked_at IS NOT NULL THEN 1 ELSE 0 END) AS checked
            FROM bloggers
            WHERE status != 'hidden'
            """
        ).fetchone()
    return {
        "total": row["total"] or 0,
        "verified": row["verified"] or 0,
        "candidate": row["candidate"] or 0,
        "checked": row["checked"] or 0,
    }


def build_tabs(tag_counts: List[Dict[str, Any]], total: int) -> List[Dict[str, Any]]:
    counts = {tag["slug"]: tag["count"] for tag in tag_counts}
    tabs = []
    for slug, name in MAJOR_TABS:
        tabs.append({"slug": slug, "name": name, "count": total if slug == "" else counts.get(slug, 0)})
    return tabs


def make_pagination(page: int, page_size: int, total: int) -> Dict[str, int]:
    total_pages = max(ceil(total / page_size), 1)
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "prev_page": max(page - 1, 1),
        "next_page": min(page + 1, total_pages),
        "start": 0 if total == 0 else (page - 1) * page_size + 1,
        "end": min(page * page_size, total),
    }
