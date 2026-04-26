from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin
import html
import re

from app.http_client import fetch_url
from app.importer import BloggerCandidate, canonicalize_url
from app.taxonomy import classify_tags, is_tech_relevant


SOURCE_NAME = "forever_blog"
LIST_URL = "https://www.foreverblog.cn/blogs.html"
YEARS = list(range(2026, 2016, -1))


@dataclass
class ForeverListItem:
    name: str
    detail_url: str
    title: str
    avatar_url: Optional[str]
    signed_at: Optional[str]


@dataclass
class ForeverDetail:
    site_url: Optional[str]
    description: str
    avatar_url: Optional[str]


class ForeverListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: List[ForeverListItem] = []
        self._current: Optional[dict] = None
        self._capture_name = False
        self._capture_date = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and "item" in attrs_dict.get("class", "").split():
            self._current = {
                "detail_url": urljoin(LIST_URL, attrs_dict.get("href", "")),
                "title": attrs_dict.get("title", ""),
                "avatar_url": None,
                "name": "",
                "signed_at": None,
            }
        elif self._current is not None and tag == "img":
            self._current["avatar_url"] = attrs_dict.get("data-original") or attrs_dict.get("src")
        elif self._current is not None and tag == "h4" and "name" in attrs_dict.get("class", "").split():
            self._capture_name = True
        elif self._current is not None and tag == "span" and "date" in attrs_dict.get("class", "").split():
            self._capture_date = True

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        if self._capture_name:
            self._current["name"] += data
        if self._capture_date:
            match = re.search(r"\d{4}-\d{2}-\d{2}", data)
            if match:
                self._current["signed_at"] = match.group(0)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h4":
            self._capture_name = False
        elif tag == "span":
            self._capture_date = False
        elif tag == "a" and self._current is not None:
            if self._current.get("name") and self._current.get("detail_url"):
                self.items.append(
                    ForeverListItem(
                        name=html.unescape(self._current["name"]).strip(),
                        detail_url=self._current["detail_url"],
                        title=html.unescape(self._current.get("title") or "").strip(),
                        avatar_url=self._current.get("avatar_url"),
                        signed_at=self._current.get("signed_at"),
                    )
                )
            self._current = None


class ForeverDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[tuple[str, str]] = []
        self.avatar_url: Optional[str] = None
        self.description_parts: List[str] = []
        self._anchor_href: Optional[str] = None
        self._anchor_text: List[str] = []
        self._in_cleft = False
        self._in_description = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        class_names = attrs_dict.get("class", "").split()
        if tag == "div" and "cleft" in class_names:
            self._in_cleft = True
        elif self._in_cleft and tag == "img" and self.avatar_url is None:
            self.avatar_url = attrs_dict.get("src")
        elif tag == "a":
            self._anchor_href = attrs_dict.get("href")
            self._anchor_text = []
        elif self._in_cleft and tag == "p":
            self._in_description = True

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._in_description:
            self.description_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href:
            text = " ".join(part.strip() for part in self._anchor_text if part.strip())
            self.anchors.append((self._anchor_href, text))
            self._anchor_href = None
            self._anchor_text = []
        elif tag == "p":
            self._in_description = False
        elif tag == "div" and self._in_cleft:
            self._in_cleft = False

    def detail(self) -> ForeverDetail:
        site_url = None
        for href, text in self.anchors:
            if "查看TA的网站" in text or "查看ta的网站" in text.lower():
                site_url = href
                break
        if site_url is None:
            for href, _text in self.anchors:
                if href.startswith("http") and "foreverblog.cn" not in href:
                    site_url = href
                    break

        description = " ".join(part.strip() for part in self.description_parts if part.strip())
        description = re.sub(r"\s+", " ", description).replace("博主寄语:", "").strip()
        return ForeverDetail(
            site_url=canonicalize_url(site_url) if site_url else None,
            description=description,
            avatar_url=self.avatar_url,
        )


def collect(
    max_items: int = 500,
    include_broad: bool = False,
    detail_limit: int = 160,
) -> List[BloggerCandidate]:
    candidates: List[BloggerCandidate] = []
    seen_detail_urls = set()
    checked_details = 0

    for year in YEARS:
        list_url = f"{LIST_URL}?year={year}"
        parser = ForeverListParser()
        parser.feed(fetch_url(list_url).text)

        for item in parser.items:
            if item.detail_url in seen_detail_urls:
                continue
            seen_detail_urls.add(item.detail_url)
            checked_details += 1
            if checked_details > detail_limit:
                return candidates

            detail_html = fetch_url(item.detail_url, timeout=10).text
            detail_parser = ForeverDetailParser()
            detail_parser.feed(detail_html)
            detail = detail_parser.detail()
            if not detail.site_url:
                continue

            description = detail.description or item.title or "十年之约签约独立博客。"
            tags = classify_tags(f"{item.name} {item.title} {description}", ["foreverblog"])
            if not include_broad and not is_tech_relevant(tags):
                continue

            score = 46
            if is_tech_relevant(tags):
                score += 12
            if item.signed_at and item.signed_at >= "2024-01-01":
                score += 4

            candidates.append(
                BloggerCandidate(
                    name=item.name,
                    site_name=item.name,
                    site_url=detail.site_url,
                    description=description[:180],
                    avatar_url=detail.avatar_url or item.avatar_url,
                    thumbnail_url=detail.avatar_url or item.avatar_url,
                    tags=tags,
                    source_name=SOURCE_NAME,
                    source_url=item.detail_url,
                    quality_score=min(score, 76),
                )
            )
            if len(candidates) >= max_items:
                return candidates

    return candidates
