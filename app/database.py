from pathlib import Path
import sqlite3


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bloggers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  site_name TEXT NOT NULL,
  site_url TEXT NOT NULL,
  canonical_url TEXT,
  description TEXT NOT NULL,
  avatar_url TEXT,
  thumbnail_url TEXT,
  rss_url TEXT,
  github_url TEXT,
  twitter_url TEXT,
  other_social_urls TEXT,
  source_name TEXT,
  source_url TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  site_status_code INTEGER,
  recency_source TEXT,
  verification_error TEXT,
  quality_score INTEGER NOT NULL DEFAULT 0,
  last_post_at TEXT,
  last_checked_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  group_name TEXT NOT NULL DEFAULT 'topic',
  display_order INTEGER NOT NULL DEFAULT 999
);

CREATE TABLE IF NOT EXISTS blogger_tags (
  blogger_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  PRIMARY KEY (blogger_id, tag_id),
  FOREIGN KEY (blogger_id) REFERENCES bloggers(id) ON DELETE CASCADE,
  FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  blogger_id INTEGER NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT,
  raw_title TEXT,
  raw_description TEXT,
  collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (blogger_id) REFERENCES bloggers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bloggers_status ON bloggers(status);
CREATE INDEX IF NOT EXISTS idx_bloggers_quality ON bloggers(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_bloggers_last_post ON bloggers(last_post_at DESC);
CREATE INDEX IF NOT EXISTS idx_tags_slug ON tags(slug);
"""


MIGRATIONS = [
    "ALTER TABLE bloggers ADD COLUMN site_status_code INTEGER",
    "ALTER TABLE bloggers ADD COLUMN recency_source TEXT",
    "ALTER TABLE bloggers ADD COLUMN verification_error TEXT",
]


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(bloggers)").fetchall()
        }
        for statement in MIGRATIONS:
            column_name = statement.rsplit(" ", 2)[-2]
            if column_name not in existing_columns:
                conn.execute(statement)
