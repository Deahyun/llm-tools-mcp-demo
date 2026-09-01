"""Streamable HTTP 트랜스포트로도 stdio 와 **같은 도구 집합/같은 동작**인지 검증.

LLM 도 브라우저도 필요 없습니다. uvicorn 을 백그라운드 스레드로 띄우고 URL 로 접속합니다.
`test_parity.py` 가 stdio 에 대해 하는 검증을 HTTP 에 대해 반복하는 셈입니다.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn
from mcp import Client

from toolsdemo.mcp_.http_server import build_app
from toolsdemo.tools import booking  # noqa: F401 - registry 채우기
from toolsdemo.tools.registry import get_registry, ollama_tool_schemas


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _reachable(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def http_endpoint():
    """MCP Streamable HTTP 서버를 임시 포트로 띄우고 접속 URL 을 준다."""
    port = _free_port()
    config = uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline and not _reachable("127.0.0.1", port):
        time.sleep(0.2)
    if not _reachable("127.0.0.1", port):
        server.should_exit = True
        pytest.skip(f"MCP HTTP 서버를 127.0.0.1:{port} 에 띄우지 못했습니다.")

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=5)


async def test_http_exposes_same_tools_as_registry(http_endpoint):
    expected = get_registry()

    async with Client(http_endpoint) as client:
        listed = await client.list_tools()

    got = {t.name: t for t in listed.tools}

    assert set(got) == set(expected), "registry 와 HTTP 노출 도구 집합이 다릅니다"
    for name, spec in expected.items():
        assert got[name].description == spec.description, f"{name}: 설명 불일치"
        assert got[name].input_schema == spec.parameters, f"{name}: 입력 스키마 불일치"


async def test_http_and_registry_produce_identical_ollama_schemas(http_endpoint):
    """트랜스포트가 바뀌어도 모델에게 보여주는 tools 배열은 같아야 한다."""
    from toolsdemo.mcp_.client_agent import to_ollama_schemas

    async with Client(http_endpoint) as client:
        listed = await client.list_tools()

    assert {s["function"]["name"]: s for s in to_ollama_schemas(listed.tools)} == {
        s["function"]["name"]: s for s in ollama_tool_schemas()
    }


async def test_http_tool_call_returns_json_payload(http_endpoint):
    """브라우저가 필요 없는 도구(get_today)로 HTTP 왕복을 확인한다."""
    async with Client(http_endpoint) as client:
        response = await client.call_tool("get_today", {})

    text = next(c.text for c in response.content if getattr(c, "type", None) == "text")
    payload = json.loads(text)
    assert payload["ok"] is True
    assert len(payload["today"]) == 10


async def test_http_tool_failure_travels_as_data(http_endpoint):
    """실패는 프로토콜 오류가 아니라 {"ok": false} 페이로드로 와야 한다 (stdio 와 동일)."""
    async with Client(http_endpoint) as client:
        response = await client.call_tool(
            "search_trains", {"departure": "서울", "arrival": "부산", "date": "내일모레"}
        )

    text = next(c.text for c in response.content if getattr(c, "type", None) == "text")
    payload = json.loads(text)
    assert payload["ok"] is False
    assert "YYYY-MM-DD" in payload["error"]
