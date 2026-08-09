from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from inkflow.source_import import MAX_SOURCE_BYTES, extract_url


class SourceHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/large":
            body = b"x" * (MAX_SOURCE_BYTES + 1)
            content_type = "text/plain; charset=utf-8"
        else:
            body = (
                "<html><body><h1>标题</h1><script>隐藏</script>"
                "<p>可读正文</p></body></html>"
            ).encode()
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def source_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SourceHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_url_source_is_read_through_the_capped_real_http_boundary() -> None:
    with source_server() as base_url:
        content, provenance = extract_url(f"{base_url}/article")

    assert content == "标题\n可读正文"
    assert provenance["resolved_url"] == f"{base_url}/article"


def test_url_source_rejects_a_response_beyond_the_material_budget() -> None:
    with source_server() as base_url:
        with pytest.raises(ValueError, match="response limit"):
            extract_url(f"{base_url}/large")
