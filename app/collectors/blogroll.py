from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse
import re

from app.database import get_connection, init_db
from app.http_client import fetch_url
from app.importer import BloggerCandidate, canonicalize_url, host_key
from app.taxonomy import classify_tags


SOURCE_NAME = "blogroll"

FRIEND_KEYWORDS = (
    "友链",
    "友情链接",
    "朋友",
    "邻居",
    "伙伴",
    "links",
    "friends",
    "blogroll",
)
FRIEND_PATHS = (
    "/friends",
    "/friends/",
    "/friend",
    "/friend/",
    "/links",
    "/links/",
    "/link",
    "/link/",
    "/blogroll",
    "/blogroll/",
)
EXCLUDED_HOST_KEYWORDS = (
    "github.com",
    "twitter.com",
    "x.com",
    "weibo.com",
    "zhihu.com",
    "juejin.cn",
    "bilibili.com",
    "youtube.com",
    "google.com",
    "baidu.com",
    "qq.com",
    "douban.com",
    "medium.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "telegram.",
    "discord.",
    "creativecommons.org",
    "schema.org",
    "digitalocean.com",
    "eepurl.com",
    "mailchimp.com",
)
EXCLUDED_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".pdf",
    ".zip",
)


@dataclass
class BlogrollSeed:
    name: str
    site_url: str


@dataclass
class CrawlResult:
    source_name: str
    source_site_url: str
    friend_page_url: Optional[str]
    candidates: List[BloggerCandidate]
    error: Optional[str] = None


class LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: List[Dict[str, str]] = []
        self.title = ""
        self._in_title = False
        self._current: Optional[Dict[str, str]] = None
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            href = attrs_dict.get("href")
            if not href:
                return
            self._current = {
                "href": canonicalize_url(urljoin(self.base_url, href)),
                "title": attrs_dict.get("title") or "",
                "rel": attrs_dict.get("rel") or "",
            }
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._current is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._current is not None:
            text = clean_text(" ".join(self._text_parts))
            self._current["text"] = text
            self.links.append(self._current)
            self._current = None
            self._text_parts = []


def collect(
    max_items: int = 500,
    depth: int = 1,
    workers: int = 4,
    seed_limit: int = 80,
    page_limit: int = 4,
    seed_urls: Optional[Sequence[str]] = None,
) -> List[BloggerCandidate]:
    init_db()
    all_candidates: List[BloggerCandidate] = []
    seen_urls = existing_site_urls()
    seen_hosts = existing_site_hosts()
    frontier = seed_rows(seed_limit=seed_limit, seed_urls=seed_urls)

    for level in range(max(depth, 1)):
        if not frontier or len(all_candidates) >= max_items:
            break

        next_frontier: List[BlogrollSeed] = []
        with ProcessPoolExecutor(max_workers=max(workers, 1)) as executor:
            futures = [
                executor.submit(crawl_seed, seed, page_limit)
                for seed in frontier
            ]
            for future in as_completed(futures):
                result = future.result()
                if result.error:
                    print(
                        f"blogroll depth={level + 1} {result.source_name}: {result.error}",
                        flush=True,
                    )
                    continue

                for candidate in result.candidates:
                    canonical = canonicalize_url(candidate.site_url)
                    host = host_key(canonical)
                    if not canonical or canonical in seen_urls or host in seen_hosts:
                        continue
                    seen_urls.add(canonical)
                    seen_hosts.add(host)
                    all_candidates.append(candidate)
                    next_frontier.append(BlogrollSeed(name=candidate.name, site_url=canonical))
                    if len(all_candidates) >= max_items:
                        break
                if len(all_candidates) >= max_items:
                    break

        frontier = next_frontier[:seed_limit]

    return all_candidates[:max_items]


def crawl_seed(seed: BlogrollSeed, page_limit: int) -> CrawlResult:
    try:
        friend_pages = discover_friend_pages(seed.site_url, page_limit=page_limit)
        for friend_page_url in friend_pages:
            response = fetch_url(friend_page_url, timeout=10)
            if response.status_code >= 400:
                continue
            parser = LinkParser(response.final_url)
            parser.feed(response.text[:300_000])
            candidates = candidates_from_links(
                links=parser.links,
                source_name=seed.name,
                source_site_url=seed.site_url,
                friend_page_url=response.final_url,
            )
            if candidates:
                return CrawlResult(
                    source_name=seed.name,
                    source_site_url=seed.site_url,
                    friend_page_url=response.final_url,
                    candidates=candidates,
                )
        return CrawlResult(seed.name, seed.site_url, None, [])
    except Exception as exc:
        return CrawlResult(seed.name, seed.site_url, None, [], f"{type(exc).__name__}: {exc}")


def discover_friend_pages(site_url: str, page_limit: int = 4) -> List[str]:
    canonical_site = canonicalize_url(site_url)
    parsed = urlparse(canonical_site)
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates: List[str] = []

    try:
        home = fetch_url(canonical_site, timeout=8)
        home_parser = LinkParser(home.final_url)
        home_parser.feed(home.text[:200_000])
        for link in home_parser.links:
            text = f"{link.get('text', '')} {link.get('title', '')} {link.get('href', '')}".lower()
            if has_friend_keyword(text):
                href = link.get("href", "")
                if is_same_domain(root, href):
                    candidates.append(canonicalize_url(href))
    except Exception:
        pass

    for path in FRIEND_PATHS:
        candidates.append(canonicalize_url(urljoin(root, path)))

    return list(dict.fromkeys(candidates))[:page_limit]


def candidates_from_links(
    links: Iterable[Dict[str, str]],
    source_name: str,
    source_site_url: str,
    friend_page_url: str,
) -> List[BloggerCandidate]:
    parsed_source = urlparse(source_site_url)
    source_domain = normalize_domain(parsed_source.netloc)
    candidates: List[BloggerCandidate] = []
    seen = set()

    for link in links:
        url = canonicalize_url(link.get("href", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        if not is_candidate_blog_url(url, source_domain=source_domain):
            continue

        name = clean_text(link.get("text") or link.get("title") or site_name_from_url(url))
        if not name or len(name) > 60:
            name = site_name_from_url(url)

        tags = classify_tags(f"{name} {url}", ["blogroll"])
        candidates.append(
            BloggerCandidate(
                name=name,
                site_name=name,
                site_url=url,
                description=f"由 {source_name} 的友链页面发现，来源站点：{source_site_url}",
                tags=tags,
                source_name=SOURCE_NAME,
                source_url=friend_page_url,
                quality_score=48,
            )
        )

    return candidates


def seed_rows(seed_limit: int, seed_urls: Optional[Sequence[str]]) -> List[BlogrollSeed]:
    if seed_urls:
        return [
            BlogrollSeed(name=site_name_from_url(url), site_url=canonicalize_url(url))
            for url in seed_urls
            if canonicalize_url(url)
        ]

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT site_name, site_url
            FROM bloggers
            WHERE status != 'hidden'
            ORDER BY
              CASE WHEN status = 'verified' THEN 0 ELSE 1 END,
              quality_score DESC,
              id ASC
            LIMIT ?
            """,
            (seed_limit,),
        ).fetchall()
    return [BlogrollSeed(name=row["site_name"], site_url=row["site_url"]) for row in rows]


def existing_site_urls() -> set:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT site_url, canonical_url FROM bloggers WHERE status != 'hidden'"
        ).fetchall()
    values = set()
    for row in rows:
        for url in (row["site_url"], row["canonical_url"]):
            canonical = canonicalize_url(url or "")
            if canonical:
                values.add(canonical)
    return values


def existing_site_hosts() -> set:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT site_url, canonical_url FROM bloggers WHERE status != 'hidden'"
        ).fetchall()
    values = set()
    for row in rows:
        for url in (row["site_url"], row["canonical_url"]):
            canonical = canonicalize_url(url or "")
            if canonical:
                values.add(host_key(canonical))
    return values


def is_candidate_blog_url(url: str, source_domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    domain = normalize_domain(parsed.netloc)
    if not domain or is_same_site_family(domain, source_domain):
        return False
    lowered = url.lower()
    if any(keyword in lowered for keyword in EXCLUDED_HOST_KEYWORDS):
        return False
    if lowered.endswith(EXCLUDED_SUFFIXES):
        return False
    if any(segment in lowered for segment in ("/tag/", "/category/", "/search", "/comment", "/feed", "/rss")):
        return False
    return "." in domain


def is_same_domain(root_url: str, target_url: str) -> bool:
    root_domain = normalize_domain(urlparse(root_url).netloc)
    target_domain = normalize_domain(urlparse(target_url).netloc)
    return bool(root_domain and target_domain and is_same_site_family(target_domain, root_domain))


def is_same_site_family(domain: str, source_domain: str) -> bool:
    return root_domain(domain) == root_domain(source_domain)


def has_friend_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in FRIEND_KEYWORDS)


def normalize_domain(domain: str) -> str:
    return re.sub(r"^www\.", "", domain.lower())


def root_domain(domain: str) -> str:
    domain = normalize_domain(domain)
    parts = [part for part in domain.split(".") if part]
    if len(parts) <= 2:
        return domain

    suffix2 = ".".join(parts[-2:])
    suffix3 = ".".join(parts[-3:])
    platform_suffixes = {
        "github.io",
        "gitlab.io",
        "vercel.app",
        "netlify.app",
        "pages.dev",
        "blogspot.com",
        "wordpress.com",
    }
    if suffix2 in platform_suffixes:
        return domain
    if suffix2 in {"com.cn", "net.cn", "org.cn", "co.uk", "com.au"} and len(parts) >= 3:
        return suffix3
    return suffix2


def site_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    domain = normalize_domain(parsed.netloc)
    return domain or url


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_｜|·:：")
