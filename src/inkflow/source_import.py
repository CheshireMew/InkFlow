from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

MAX_SOURCE_BYTES = 4 * 1024 * 1024


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in {"p", "br", "li", "h1", "h2", "h3", "article"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag in {"p", "li", "h1", "h2", "h3", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in " ".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def extract_url(url: str, *, timeout_seconds: float = 20) -> tuple[str, dict[str, str]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source URL must be an absolute http or https URL")
    try:
        with httpx.stream(
            "GET",
            url,
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": "InkFlow (+local writing workbench)"},
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            resolved_url = str(response.url)
            payload = bytearray()
            for chunk in response.iter_bytes():
                if len(payload) + len(chunk) > MAX_SOURCE_BYTES:
                    raise ValueError(
                        f"source URL exceeds the {MAX_SOURCE_BYTES}-byte response limit"
                    )
                payload.extend(chunk)
            decoded = bytes(payload).decode(response.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise ValueError(f"unable to read source URL: {exc}") from exc
    if "html" in content_type:
        parser = _VisibleTextParser()
        parser.feed(decoded)
        content = parser.text()
    elif content_type.startswith("text/") or not content_type:
        content = decoded.strip()
    else:
        raise ValueError(f"source URL returned unsupported content type: {content_type}")
    if not content:
        raise ValueError("source URL did not contain readable text")
    return content, {
        "url": url,
        "resolved_url": resolved_url,
        "content_type": content_type,
    }
