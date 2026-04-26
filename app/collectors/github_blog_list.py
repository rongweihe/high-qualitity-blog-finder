from __future__ import annotations

from typing import Iterable, List, Optional
import re

from app.http_client import fetch_url
from app.importer import BloggerCandidate, canonicalize_url
from app.taxonomy import classify_tags, is_tech_relevant


SOURCE_NAME = "github_blog_list"
RAW_BASE = "https://raw.githubusercontent.com/qianguyihao/blog-list/main"

DEFAULT_FILES = [
    ("05-%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD.md", ["ai", "github-list"]),
    ("06-%E6%8A%80%E6%9C%AF%E5%8D%9A%E5%AE%A2.md", ["github-list"]),
    ("07-%E4%BA%A7%E5%93%81%E8%AE%BE%E8%AE%A1.md", ["product", "github-list"]),
    ("08-%E6%9C%AF%E4%B8%9A%E4%B8%93%E6%94%BB.md", ["github-list"]),
]

URL_RE = re.compile(r"https?://[^\s)>\]）}，。；,]+")
HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
NO_RSS_MARKERS = ("暂无rss", "暂无 RSS", "暂无rss链接", "暂无 RSS 链接")
EXCLUDED_HOSTS = (
    "github.com",
    "weibo.com",
    "twitter.com",
    "x.com",
    "zhihu.com",
    "juejin.cn",
    "xiaoyuzhoufm.com",
    "medium.com",
)


def collect(max_items: int = 500) -> List[BloggerCandidate]:
    candidates: List[BloggerCandidate] = []
    for filename, extra_tags in DEFAULT_FILES:
        source_url = f"{RAW_BASE}/{filename}"
        markdown = fetch_url(source_url).text
        for name, block in _iter_blocks(markdown):
            candidate = _candidate_from_block(name, block, source_url, extra_tags)
            if candidate is None:
                continue
            candidates.append(candidate)
            if len(candidates) >= max_items:
                return candidates
    return candidates


def _iter_blocks(markdown: str) -> Iterable[tuple[str, str]]:
    current_name: Optional[str] = None
    current_lines: List[str] = []

    for line in markdown.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            if current_name and current_lines:
                yield current_name, "\n".join(current_lines).strip()
            current_name = _clean_text(heading.group(1))
            current_lines = []
        elif current_name:
            current_lines.append(line)

    if current_name and current_lines:
        yield current_name, "\n".join(current_lines).strip()


def _candidate_from_block(
    name: str,
    block: str,
    source_url: str,
    extra_tags: Iterable[str],
) -> Optional[BloggerCandidate]:
    urls = URL_RE.findall(block)
    if not urls:
        return None

    rss_url = _find_rss_url(block, urls)
    site_url = _find_site_url(block, urls, rss_url)
    if not site_url:
        return None

    text = _clean_text(block)
    tags = classify_tags(f"{name} {text}", extra_tags)
    if not is_tech_relevant(tags):
        return None

    github_url = _find_host_url(urls, "github.com")
    twitter_url = _find_host_url(urls, "twitter.com") or _find_host_url(urls, "x.com")
    description = _description_from_block(block)

    score = 62
    if "ai" in tags:
        score += 8
    if "agent" in tags:
        score += 8
    if "github-list" in tags:
        score += 8
    if rss_url:
        score += 6
    if github_url or twitter_url:
        score += 4

    return BloggerCandidate(
        name=name,
        site_name=name,
        site_url=site_url,
        rss_url=rss_url,
        github_url=github_url,
        twitter_url=twitter_url,
        description=description,
        tags=tags,
        source_name=SOURCE_NAME,
        source_url=source_url,
        quality_score=min(score, 95),
    )


def _find_rss_url(block: str, urls: List[str]) -> Optional[str]:
    for marker in NO_RSS_MARKERS:
        if marker.lower() in block.lower():
            return None

    for line in block.splitlines():
        if "rss" in line.lower() or "atom" in line.lower():
            match = URL_RE.search(line)
            if match:
                return canonicalize_url(match.group(0))

    for url in urls:
        lowered = url.lower()
        if "rss" in lowered or "atom" in lowered or "feed" in lowered:
            return canonicalize_url(url)
    return None


def _find_site_url(block: str, urls: List[str], rss_url: Optional[str]) -> Optional[str]:
    preferred_markers = ("博客", "地址", "主页", "网站", "空间", "blog")
    short_candidates = []
    for line in block.splitlines():
        if "rss" in line.lower() or "订阅" in line.lower():
            continue
        match = URL_RE.search(line)
        if match and len(line.strip()) <= 120:
            candidate = canonicalize_url(match.group(0))
            if candidate != rss_url and not _is_excluded_url(candidate):
                short_candidates.append(candidate)
    if short_candidates:
        return short_candidates[-1]

    for line in block.splitlines():
        lowered = line.lower()
        if "rss" in lowered or "订阅" in lowered:
            continue
        if any(marker.lower() in lowered for marker in preferred_markers):
            match = URL_RE.search(line)
            if match:
                candidate = canonicalize_url(match.group(0))
                if candidate != rss_url and not _is_excluded_url(candidate):
                    return candidate

    for url in urls:
        candidate = canonicalize_url(url)
        if candidate != rss_url and not _is_excluded_url(candidate):
            return candidate
    return None


def _find_host_url(urls: List[str], host: str) -> Optional[str]:
    for url in urls:
        if host in url.lower():
            return canonicalize_url(url)
    return None


def _is_excluded_url(url: str) -> bool:
    lowered = url.lower()
    if lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return True
    return any(host in lowered for host in EXCLUDED_HOSTS)


def _description_from_block(block: str) -> str:
    lines = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.startswith(">"):
            continue
        if stripped.startswith("###"):
            continue
        cleaned = _clean_text(stripped)
        if cleaned:
            lines.append(cleaned)
    description = " ".join(lines)
    if not description:
        description = _clean_text(block)
    return description[:180]


def _clean_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    text = re.sub(r"[#>*_`-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ：:-")
