from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import ROOT_DIR
from .repository import build_tabs, get_stats, get_tag_counts, list_bloggers, make_pagination
from .seed_loader import sync_seed_data


app = FastAPI(title="中文高质量技术博主发现站")
templates = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "app" / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    sync_seed_data()


def _normalize_page_size(page_size: int) -> int:
    allowed = [12, 24, 48, 96]
    return page_size if page_size in allowed else 24


def _page_url(
    *,
    tag: str,
    q: str,
    sort: str,
    page_size: int,
    page: int,
    overrides: Optional[dict] = None,
) -> str:
    params = {
        "tag": tag,
        "q": q,
        "sort": sort,
        "page_size": page_size,
        "page": page,
    }
    if overrides:
        params.update(overrides)
    clean_params = {key: value for key, value in params.items() if value not in ("", None)}
    return f"/?{urlencode(clean_params)}"


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    tag: str = "",
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1),
    sort: str = "quality",
) -> HTMLResponse:
    page_size = _normalize_page_size(page_size)
    sort = sort if sort in {"quality", "recent", "name"} else "quality"
    q = q.strip()

    bloggers, total = list_bloggers(tag=tag, query=q, page=page, page_size=page_size, sort=sort)
    pagination = make_pagination(page=page, page_size=page_size, total=total)

    if page > pagination["total_pages"]:
        page = pagination["total_pages"]
        bloggers, total = list_bloggers(tag=tag, query=q, page=page, page_size=page_size, sort=sort)
        pagination = make_pagination(page=page, page_size=page_size, total=total)

    tag_counts = get_tag_counts()
    stats = get_stats()

    def page_url(**overrides: object) -> str:
        return _page_url(tag=tag, q=q, sort=sort, page_size=page_size, page=page, overrides=overrides)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bloggers": bloggers,
            "tag_counts": tag_counts,
            "tabs": build_tabs(tag_counts, stats["total"]),
            "stats": stats,
            "active_tag": tag,
            "query": q,
            "sort": sort,
            "page_size": page_size,
            "pagination": pagination,
            "page_url": page_url,
        },
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
