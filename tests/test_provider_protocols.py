from __future__ import annotations

import asyncio
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

import pytest

from inkflow.providers.base import ProviderError
from inkflow.providers.openai_compatible import OpenAICompatibleProvider
from inkflow.providers.openai_responses import OpenAIResponsesProvider

RESULT_SCHEMA = {
    "type": "object",
    "properties": {"outputs": {"type": "array", "items": {"type": "string"}}},
    "required": ["outputs"],
    "additionalProperties": False,
}


class ProtocolServer(ThreadingHTTPServer):
    requests: list[dict[str, Any]]
    responses: dict[str, bytes]


class ProtocolHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        server = self.server
        assert isinstance(server, ProtocolServer)
        server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("authorization"),
                "payload": json.loads(body),
            }
        )
        response = server.responses[self.path]
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("x-request-id", "request-loopback-001")
        self.send_header("content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


@contextmanager
def protocol_server(responses: dict[str, dict[str, Any] | bytes]) -> Iterator[ProtocolServer]:
    server = ProtocolServer(("127.0.0.1", 0), ProtocolHandler)
    server.requests = []
    server.responses = {
        path: value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
        for path, value in responses.items()
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_chat_adapter_sends_strict_schema_over_a_real_http_boundary() -> None:
    with protocol_server(
        {
            "/v1/chat/completions": {
                "choices": [
                    {
                        "message": {"content": '{"outputs":["聊天结果"]}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 12},
            }
        }
    ) as server:
        provider = OpenAICompatibleProvider(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="loopback-key",
            model="fixed-chat-model",
        )
        response = asyncio.run(
            provider.complete(
                system="system",
                user="user",
                response_schema=RESULT_SCHEMA,
            )
        )

    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["authorization"] == "Bearer loopback-key"
    assert sent["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "inkflow_result",
            "strict": True,
            "schema": RESULT_SCHEMA,
        },
    }
    assert response.content == '{"outputs":["聊天结果"]}'
    assert response.request_id == "request-loopback-001"
    assert response.finish_reason == "stop"


def test_responses_adapter_sends_strict_schema_and_web_search_over_http() -> None:
    with protocol_server(
        {
            "/v1/responses": {
                "output_text": '{"outputs":["Responses 结果"]}',
                "status": "completed",
                "usage": {"total_tokens": 14},
            }
        }
    ) as server:
        provider = OpenAIResponsesProvider(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="loopback-key",
            model="fixed-responses-model",
        )
        response = asyncio.run(
            provider.complete(
                system="system",
                user="user",
                response_schema=RESULT_SCHEMA,
                use_web_search=True,
            )
        )

    sent = server.requests[0]
    assert sent["payload"]["text"]["format"] == {
        "type": "json_schema",
        "name": "inkflow_result",
        "strict": True,
        "schema": RESULT_SCHEMA,
    }
    assert sent["payload"]["tools"] == [{"type": "web_search"}]
    assert response.content == '{"outputs":["Responses 结果"]}'
    assert response.finish_reason == "completed"


def test_provider_envelope_rejects_duplicate_keys_before_consumption() -> None:
    duplicate = b'{"choices":[],"choices":[]}'
    with protocol_server({"/v1/chat/completions": duplicate}) as server:
        provider = OpenAICompatibleProvider(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="loopback-key",
            model="fixed-chat-model",
        )
        with pytest.raises(ProviderError) as raised:
            asyncio.run(
                provider.complete(
                    system="system",
                    user="user",
                    response_schema=RESULT_SCHEMA,
                )
            )
    assert raised.value.kind == "invalid_json"
