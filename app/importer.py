from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional
from urllib.parse import quote_plus, urlparse, urlunparse
import hashlib
import json
import re

from .database import get_connection, init_db
from .taxonomy import DEFAULT_TAGS


@dataclass
class BloggerCandidate:
    name: str
    site_url: str
    description: str
    tags: List[str]
    source_name: str
    source_url: str
    site_name: Optional[str] = None
    rss_url: Optional[str] = None
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None
    avatar_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str = "candidate"
    quality_score: int = 50
    other_social_urls: List[str] = field(default_factory=list)


def canonicalize_url(url: str) -> str:
    url = url.strip().strip(" \t\r\n\"'<>）)]}，。；;,")
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        url = f"https://{url}"
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    clean = parsed._replace(netloc=netloc, path=path, params="", query="", fragment="")
    return urlunparse(clean)


def favicon_url(site_url: str) -> str:
    parsed = urlparse(site_url)
    domain = parsed.netloc or parsed.path
    return f"https://www.google.com/s2/favicons?domain={quote_plus(domain)}&sz=128"


def host_key(site_url: str) -> str:
    parsed = urlparse(site_url)
    return re.sub(r"^www\.", "", parsed.netloc.lower())


def slug_for_url(site_url: str, name: str = "") -> str:
    parsed = urlparse(site_url)
    domain = host_key(site_url)
    stem = re.sub(r"[^a-z0-9]+", "-", domain).strip("-") or "blog"
    digest = hashlib.sha1(f"{site_url}|{name}".encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}"


def ensure_default_tags(conn) -> None:
    for tag in DEFAULT_TAGS:
        conn.execute(
            """
            INSERT INTO tags (slug, name, group_name, display_order)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
              name = excluded.name,
              group_name = excluded.group_name,
              display_order = excluded.display_order
            """,
            (tag["slug"], tag["name"], tag["group"], tag["order"]),
        )


def upsert_candidate(candidate: BloggerCandidate) -> int:
    init_db()
    canonical_url = canonicalize_url(candidate.site_url)
    if not canonical_url:
        raise ValueError("candidate.site_url is required")

    candidate.site_url = canonical_url
    candidate.site_name = candidate.site_name or candidate.name
    candidate.thumbnail_url = candidate.thumbnail_url or candidate.avatar_url or favicon_url(candidate.site_url)
    candidate.tags = list(dict.fromkeys(candidate.tags))

    with get_connection() as conn:
        ensure_default_tags(conn)
        existing = conn.execute(
            """
            SELECT id, slug
            FROM bloggers
            WHERE canonical_url = ? OR site_url = ?
            LIMIT 1
            """,
            (canonical_url, canonical_url),
        ).fetchone()

        if existing is None:
            host = host_key(canonical_url)
            existing = conn.execute(
                """
                SELECT id, slug
                FROM bloggers
                WHERE
                  REPLACE(
                    REPLACE(
                      REPLACE(
                        REPLACE(site_url, 'https://www.', ''),
                        'http://www.',
                        ''
                      ),
                      'https://',
                      ''
                    ),
                    'http://',
                    ''
                  ) LIKE ?
                LIMIT 1
                """,
                (f"{host}%",),
            ).fetchone()

        slug = existing["slug"] if existing else slug_for_url(canonical_url, candidate.name)
        other_social_urls = json.dumps(candidate.other_social_urls, ensure_ascii=False)

        conn.execute(
            """
            INSERT INTO bloggers (
              slug, name, site_name, site_url, canonical_url, description,
              avatar_url, thumbnail_url, rss_url, github_url, twitter_url,
              other_social_urls, source_name, source_url, status, quality_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
              name = CASE WHEN bloggers.name = '' THEN excluded.name ELSE bloggers.name END,
              site_name = CASE WHEN bloggers.site_name = '' THEN excluded.site_name ELSE bloggers.site_name END,
              site_url = bloggers.site_url,
              canonical_url = COALESCE(bloggers.canonical_url, excluded.canonical_url),
              description = CASE
                WHEN LENGTH(bloggers.description) < 24 THEN excluded.description
                ELSE bloggers.description
              END,
              avatar_url = COALESCE(bloggers.avatar_url, excluded.avatar_url),
              thumbnail_url = COALESCE(bloggers.thumbnail_url, excluded.thumbnail_url),
              rss_url = COALESCE(bloggers.rss_url, excluded.rss_url),
              github_url = COALESCE(bloggers.github_url, excluded.github_url),
              twitter_url = COALESCE(bloggers.twitter_url, excluded.twitter_url),
              other_social_urls = CASE
                WHEN bloggers.other_social_urls IS NULL OR bloggers.other_social_urls = '[]' THEN excluded.other_social_urls
                ELSE bloggers.other_social_urls
              END,
              source_name = CASE WHEN bloggers.source_name = 'manual_seed' THEN bloggers.source_name ELSE excluded.source_name END,
              source_url = COALESCE(bloggers.source_url, excluded.source_url),
              status = CASE
                WHEN bloggers.status = 'verified' THEN bloggers.status
                WHEN excluded.status = 'hidden' THEN excluded.status
                ELSE bloggers.status
              END,
              quality_score = MAX(bloggers.quality_score, excluded.quality_score),
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                slug,
                candidate.name,
                candidate.site_name,
                candidate.site_url,
                canonical_url,
                candidate.description,
                candidate.avatar_url,
                candidate.thumbnail_url,
                candidate.rss_url,
                candidate.github_url,
                candidate.twitter_url,
                other_social_urls,
                candidate.source_name,
                candidate.source_url,
                candidate.status,
                candidate.quality_score,
            ),
        )

        blogger_id = conn.execute("SELECT id FROM bloggers WHERE slug = ?", (slug,)).fetchone()["id"]

        for tag_slug in candidate.tags:
            conn.execute(
                """
                INSERT OR IGNORE INTO tags (slug, name, group_name, display_order)
                VALUES (?, ?, 'topic', 999)
                """,
                (tag_slug, tag_slug.replace("-", " ").title()),
            )
            tag_id = conn.execute("SELECT id FROM tags WHERE slug = ?", (tag_slug,)).fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO blogger_tags (blogger_id, tag_id) VALUES (?, ?)",
                (blogger_id, tag_id),
            )

        conn.execute(
            """
            INSERT INTO source_refs (blogger_id, source_name, source_url, raw_title, raw_description)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
              SELECT 1 FROM source_refs
              WHERE blogger_id = ? AND source_name = ? AND COALESCE(source_url, '') = COALESCE(?, '')
            )
            """,
            (
                blogger_id,
                candidate.source_name,
                candidate.source_url,
                candidate.site_name,
                candidate.description,
                blogger_id,
                candidate.source_name,
                candidate.source_url,
            ),
        )
        conn.commit()

    return int(blogger_id)


def import_candidates(candidates: Iterable[BloggerCandidate], max_items: int = 500) -> int:
    count = 0
    for candidate in candidates:
        if count >= max_items:
            break
        upsert_candidate(candidate)
        count += 1
    return count
