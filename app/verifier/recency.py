from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse
import re
import xml.etree.ElementTree as ET

from app.database import get_connection, init_db
from app.http_client import FetchResult, fetch_url
from app.importer import canonicalize_url


COMMON_FEED_PATHS = ("/feed", "/feed/", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml")
DATE_RE = re.compile(r"(20\d{2})[-/.年](0?[1-9]|1[0-2])[-/.月](0?[1-9]|[12]\d|3[01])日?")
DATETIME_ATTR_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?")


@dataclass
class SiteMetadata:
    feed_urls: List[str] = field(default_factory=list)
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None
    description: Optional[str] = None
    og_image: Optional[str] = None
    dates: List[date] = field(default_factory=list)


@dataclass
class VerificationResult:
    status_code: Optional[int]
    last_post_at: Optional[date]
    recency_source: Optional[str]
    rss_url: Optional[str]
    github_url: Optional[str]
    twitter_url: Optional[str]
    thumbnail_url: Optional[str]
    description: Optional[str]
    error: Optional[str]


class MetadataParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.metadata = SiteMetadata()

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs}
        if tag == "link":
            rel = attrs_dict.get("rel", "").lower()
            href = attrs_dict.get("href")
            type_attr = attrs_dict.get("type", "").lower()
            if href and ("alternate" in rel or "feed" in rel) and (
                "rss" in type_attr or "atom" in type_attr or "xml" in type_attr or "json" in type_attr
            ):
                self.metadata.feed_urls.append(canonicalize_url(urljoin(self.base_url, href)))
        elif tag == "a":
            href = attrs_dict.get("href")
            if not href:
                return
            url = canonicalize_url(urljoin(self.base_url, href))
            lowered = url.lower()
            if "github.com" in lowered and self.metadata.github_url is None:
                self.metadata.github_url = url
            elif ("twitter.com" in lowered or "x.com" in lowered) and self.metadata.twitter_url is None:
                self.metadata.twitter_url = url
        elif tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content")
            if not content:
                return
            if name in {"description", "og:description", "twitter:description"} and self.metadata.description is None:
                self.metadata.description = content.strip()
            elif name in {"og:image", "twitter:image"} and self.metadata.og_image is None:
                self.metadata.og_image = canonicalize_url(urljoin(self.base_url, content.strip()))
            elif name in {"article:published_time", "article:modified_time", "date", "pubdate"}:
                parsed = parse_date_value(content)
                if parsed:
                    self.metadata.dates.append(parsed)
        elif tag == "time":
            value = attrs_dict.get("datetime")
            parsed = parse_date_value(value) if value else None
            if parsed:
                self.metadata.dates.append(parsed)

    def handle_data(self, data: str) -> None:
        for parsed in parse_dates_from_text(data):
            self.metadata.dates.append(parsed)


def verify_all(limit: int = 500, recent_since: Optional[date] = None) -> int:
    init_db()
    recent_since = recent_since or (date.today() - timedelta(days=365))
    rows = _target_rows(limit)
    count = 0
    for row in rows:
        result = verify_site(
            site_url=row["site_url"],
            rss_url=row["rss_url"],
            recent_since=recent_since,
        )
        _save_result(row["id"], result, recent_since)
        count += 1
        print(
            f"[{count}/{len(rows)}] {row['site_name']} "
            f"status={result.status_code or '-'} latest={result.last_post_at or '-'} "
            f"source={result.recency_source or '-'}",
            flush=True,
        )
    return count


def verify_site(site_url: str, rss_url: Optional[str], recent_since: date) -> VerificationResult:
    status_code = None
    site_html = ""
    metadata = SiteMetadata()

    try:
        site_response = fetch_url(site_url, timeout=12)
        status_code = site_response.status_code
        content_type = site_response.headers.get("content-type", "")
        if "text/html" in content_type or "xml" not in content_type:
            site_html = site_response.text
            parser = MetadataParser(site_response.final_url)
            parser.feed(site_html[:300_000])
            metadata = parser.metadata
    except Exception as exc:
        return VerificationResult(
            status_code=status_code,
            last_post_at=None,
            recency_source=None,
            rss_url=rss_url,
            github_url=None,
            twitter_url=None,
            thumbnail_url=None,
            description=None,
            error=f"site fetch failed: {type(exc).__name__}: {exc}",
        )

    feed_urls = _candidate_feed_urls(site_url, rss_url, metadata.feed_urls)
    for feed_url in feed_urls:
        try:
            feed_response = fetch_url(feed_url, timeout=12)
            latest = latest_date_from_feed(feed_response)
            if latest:
                return VerificationResult(
                    status_code=status_code,
                    last_post_at=latest,
                    recency_source="rss" if latest >= recent_since else "rss_stale",
                    rss_url=feed_response.final_url,
                    github_url=metadata.github_url,
                    twitter_url=metadata.twitter_url,
                    thumbnail_url=metadata.og_image,
                    description=metadata.description,
                    error=None,
                )
        except Exception:
            continue

    for sitemap_url in _candidate_sitemaps(site_url):
        try:
            latest = latest_date_from_sitemap(fetch_url(sitemap_url, timeout=12))
            if latest:
                return VerificationResult(
                    status_code=status_code,
                    last_post_at=latest,
                    recency_source="sitemap" if latest >= recent_since else "sitemap_stale",
                    rss_url=rss_url or (feed_urls[0] if feed_urls else None),
                    github_url=metadata.github_url,
                    twitter_url=metadata.twitter_url,
                    thumbnail_url=metadata.og_image,
                    description=metadata.description,
                    error=None,
                )
        except Exception:
            continue

    latest_html_date = max(metadata.dates) if metadata.dates else None
    if latest_html_date:
        return VerificationResult(
            status_code=status_code,
            last_post_at=latest_html_date,
            recency_source="html" if latest_html_date >= recent_since else "html_stale",
            rss_url=rss_url or (feed_urls[0] if feed_urls else None),
            github_url=metadata.github_url,
            twitter_url=metadata.twitter_url,
            thumbnail_url=metadata.og_image,
            description=metadata.description,
            error=None,
        )

    return VerificationResult(
        status_code=status_code,
        last_post_at=None,
        recency_source=None,
        rss_url=rss_url or (feed_urls[0] if feed_urls else None),
        github_url=metadata.github_url,
        twitter_url=metadata.twitter_url,
        thumbnail_url=metadata.og_image,
        description=metadata.description,
        error=None,
    )


def latest_date_from_feed(response: FetchResult) -> Optional[date]:
    text = response.text.strip()
    if not text:
        return None

    dates: List[date] = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
        for elem in root.iter():
            local_name = elem.tag.rsplit("}", 1)[-1].lower()
            if local_name in {"published", "updated", "pubdate", "lastbuilddate", "date"} and elem.text:
                parsed = parse_date_value(elem.text)
                if parsed:
                    dates.append(parsed)
    except ET.ParseError:
        pass

    if not dates:
        for match in DATETIME_ATTR_RE.finditer(text):
            parsed = parse_date_value(match.group(0))
            if parsed:
                dates.append(parsed)
        for line in text.splitlines():
            if any(marker in line.lower() for marker in ("pubdate", "published", "updated")):
                parsed = parse_date_value(re.sub(r"<[^>]+>", " ", line))
                if parsed:
                    dates.append(parsed)

    return max(dates) if dates else None


def latest_date_from_sitemap(response: FetchResult) -> Optional[date]:
    text = response.text.strip()
    if not text:
        return None

    dates: List[date] = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
        for elem in root.iter():
            local_name = elem.tag.rsplit("}", 1)[-1].lower()
            if local_name == "lastmod" and elem.text:
                parsed = parse_date_value(elem.text)
                if parsed:
                    dates.append(parsed)
    except ET.ParseError:
        for match in DATETIME_ATTR_RE.finditer(text):
            parsed = parse_date_value(match.group(0))
            if parsed:
                dates.append(parsed)

    return max(dates) if dates else None


def parse_date_value(value: str) -> Optional[date]:
    value = value.strip()
    if not value:
        return None

    iso_match = DATETIME_ATTR_RE.search(value)
    if iso_match:
        try:
            return datetime.fromisoformat(iso_match.group(1)).date()
        except ValueError:
            pass

    chinese_match = DATE_RE.search(value)
    if chinese_match:
        year, month, day = chinese_match.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def parse_dates_from_text(value: str) -> List[date]:
    dates = []
    for match in DATE_RE.finditer(value):
        parsed = parse_date_value(match.group(0))
        if parsed:
            dates.append(parsed)
    return dates


def _candidate_feed_urls(site_url: str, rss_url: Optional[str], discovered_urls: Iterable[str]) -> List[str]:
    urls: List[str] = []
    for candidate in [rss_url, *discovered_urls]:
        if candidate:
            urls.append(canonicalize_url(candidate))

    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    for path in COMMON_FEED_PATHS:
        urls.append(canonicalize_url(urljoin(root, path)))

    return list(dict.fromkeys(urls))


def _candidate_sitemaps(site_url: str) -> List[str]:
    parsed = urlparse(site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return [
        canonicalize_url(urljoin(root, "/sitemap.xml")),
        canonicalize_url(urljoin(root, "/sitemap_index.xml")),
    ]


def _target_rows(limit: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, site_name, site_url, rss_url
            FROM bloggers
            WHERE status != 'hidden'
            ORDER BY quality_score DESC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def _save_result(blogger_id: int, result: VerificationResult, recent_since: date) -> None:
    if result.last_post_at and result.last_post_at >= recent_since:
        status = "verified"
        quality_boost = 12
    else:
        status = "candidate"
        quality_boost = 0

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE bloggers
            SET
              status = CASE WHEN status = 'hidden' THEN status ELSE ? END,
              site_status_code = ?,
              recency_source = ?,
              verification_error = ?,
              last_post_at = ?,
              last_checked_at = CURRENT_TIMESTAMP,
              rss_url = COALESCE(rss_url, ?),
              github_url = COALESCE(github_url, ?),
              twitter_url = COALESCE(twitter_url, ?),
              thumbnail_url = COALESCE(thumbnail_url, ?),
              description = CASE
                WHEN LENGTH(description) < 24 AND ? IS NOT NULL THEN ?
                ELSE description
              END,
              quality_score = CASE
                WHEN status != 'verified' AND ? > 0 THEN MIN(100, quality_score + ?)
                ELSE quality_score
              END,
              updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                result.status_code,
                result.recency_source,
                result.error,
                result.last_post_at.isoformat() if result.last_post_at else None,
                result.rss_url,
                result.github_url,
                result.twitter_url,
                result.thumbnail_url,
                result.description,
                result.description,
                quality_boost,
                quality_boost,
                blogger_id,
            ),
        )
        conn.commit()
