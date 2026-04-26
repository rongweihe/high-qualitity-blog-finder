from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus, urlparse
import json

import yaml

from .database import ROOT_DIR, get_connection, init_db


SEEDS_PATH = ROOT_DIR / "data" / "seeds.yaml"


def _favicon_url(site_url: str) -> str:
    parsed = urlparse(site_url)
    domain = parsed.netloc or parsed.path
    return f"https://www.google.com/s2/favicons?domain={quote_plus(domain)}&sz=128"


def sync_seed_data(path: Path = SEEDS_PATH) -> None:
    init_db()
    if not path.exists():
        return

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tag_rows = raw.get("tags", [])
    blogger_rows = raw.get("bloggers", [])

    with get_connection() as conn:
        for tag in tag_rows:
            conn.execute(
                """
                INSERT INTO tags (slug, name, group_name, display_order)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                  name = excluded.name,
                  group_name = excluded.group_name,
                  display_order = excluded.display_order
                """,
                (
                    tag["slug"],
                    tag["name"],
                    tag.get("group", "topic"),
                    int(tag.get("order", 999)),
                ),
            )

        tag_name_by_slug = {tag["slug"]: tag["name"] for tag in tag_rows}

        for item in blogger_rows:
            for tag_slug in item.get("tags", []):
                if tag_slug not in tag_name_by_slug:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO tags (slug, name, group_name, display_order)
                        VALUES (?, ?, 'topic', 999)
                        """,
                        (tag_slug, tag_slug.replace("-", " ").title()),
                    )

            thumbnail_url = item.get("thumbnail_url") or item.get("avatar_url") or _favicon_url(item["site_url"])
            other_social_urls = json.dumps(item.get("other_social_urls", []), ensure_ascii=False)

            conn.execute(
                """
                INSERT INTO bloggers (
                  slug, name, site_name, site_url, canonical_url, description,
                  avatar_url, thumbnail_url, rss_url, github_url, twitter_url,
                  other_social_urls, source_name, source_url, status, quality_score,
                  last_post_at, last_checked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                  name = excluded.name,
                  site_name = excluded.site_name,
                  site_url = excluded.site_url,
                  canonical_url = excluded.canonical_url,
                  description = excluded.description,
                  avatar_url = excluded.avatar_url,
                  thumbnail_url = excluded.thumbnail_url,
                  rss_url = excluded.rss_url,
                  github_url = excluded.github_url,
                  twitter_url = excluded.twitter_url,
                  other_social_urls = excluded.other_social_urls,
                  source_name = excluded.source_name,
                  source_url = excluded.source_url,
                  status = CASE
                    WHEN bloggers.status = 'verified' THEN bloggers.status
                    ELSE excluded.status
                  END,
                  quality_score = MAX(bloggers.quality_score, excluded.quality_score),
                  last_post_at = COALESCE(bloggers.last_post_at, excluded.last_post_at),
                  last_checked_at = COALESCE(bloggers.last_checked_at, excluded.last_checked_at),
                  updated_at = CURRENT_TIMESTAMP
                """,
                (
                    item["slug"],
                    item["name"],
                    item.get("site_name", item["name"]),
                    item["site_url"],
                    item.get("canonical_url", item["site_url"]),
                    item.get("description", ""),
                    item.get("avatar_url"),
                    thumbnail_url,
                    item.get("rss_url"),
                    item.get("github_url"),
                    item.get("twitter_url"),
                    other_social_urls,
                    item.get("source_name", "manual_seed"),
                    item.get("source_url"),
                    item.get("status", "candidate"),
                    int(item.get("quality_score", 50)),
                    item.get("last_post_at"),
                    item.get("last_checked_at"),
                ),
            )

            blogger_id = conn.execute(
                "SELECT id FROM bloggers WHERE slug = ?",
                (item["slug"],),
            ).fetchone()["id"]

            conn.execute("DELETE FROM blogger_tags WHERE blogger_id = ?", (blogger_id,))
            for tag_slug in item.get("tags", []):
                tag_id = conn.execute("SELECT id FROM tags WHERE slug = ?", (tag_slug,)).fetchone()["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO blogger_tags (blogger_id, tag_id) VALUES (?, ?)",
                    (blogger_id, tag_id),
                )

            conn.execute(
                "DELETE FROM source_refs WHERE blogger_id = ? AND source_name = ?",
                (blogger_id, item.get("source_name", "manual_seed")),
            )
            conn.execute(
                """
                INSERT INTO source_refs (blogger_id, source_name, source_url, raw_title, raw_description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    blogger_id,
                    item.get("source_name", "manual_seed"),
                    item.get("source_url"),
                    item.get("site_name", item["name"]),
                    item.get("description", ""),
                ),
            )

        conn.commit()


if __name__ == "__main__":
    sync_seed_data()
    print(f"Synced seed data from {SEEDS_PATH}")
