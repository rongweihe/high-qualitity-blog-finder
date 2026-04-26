from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import gzip
import ssl


USER_AGENT = "HighQualityBlogFinder/0.1 (+https://localhost)"


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    headers: Dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        return self.body.decode(charset or "utf-8", errors="replace")


def fetch_url(url: str, timeout: float = 12.0) -> FetchResult:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
        },
    )
    context = ssl.create_default_context()

    try:
        response = urlopen(request, timeout=timeout, context=context)
        raw_body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        if headers.get("content-encoding") == "gzip":
            raw_body = gzip.decompress(raw_body)
        return FetchResult(
            url=url,
            final_url=response.geturl(),
            status_code=response.status,
            headers=headers,
            body=raw_body,
        )
    except HTTPError as exc:
        body = exc.read()
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return FetchResult(
            url=url,
            final_url=exc.geturl(),
            status_code=exc.code,
            headers=headers,
            body=body,
        )
    except URLError:
        raise
