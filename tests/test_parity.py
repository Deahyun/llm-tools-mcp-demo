"""Phase 1(registry) 과 Phase 2(MCP) 가 **같은 도구 집합**을 노출하는지 검증.

LLM 은 필요 없습니다. MCP 서버를 stdio 로 띄워 list_tools 응답을 registry 와 대조합니다.
새 도구를 추가했는데 이 테스트가 깨진다면 MCP 쪽 노출이 빠진 것입니다.
"""

from __future__ import annotations

import json

from mcp import Client

from toolsdemo.mcp_.client_agent import server_params, to_ollama_schemas
from toolsdemo.tools import booking  # noqa: F401 - registry 채우기
from toolsdemo.tools.registry import get_registry, ollama_tool_schemas


async def test_mcp_exposes_same_tools_as_registry():
    expected = get_registry()

    async with Client(server_params()) as client:
        listed = await client.list_tools()

    got = {t.name: t for t in listed.tools}

    assert set(got) == set(expected), "registry 와 MCP 노출 도구 집합이 다릅니다"
    for name, spec in expected.items():
        assert got[name].description == spec.description, f"{name}: 설명 불일치"
        assert got[name].input_schema == spec.parameters, f"{name}: 입력 스키마 불일치"


async def test_ollama_schemas_are_identical_across_phases():
    """두 Phase 가 모델에게 보여주는 tools 배열이 완전히 같아야 한다."""
    phase1 = {s["function"]["name"]: s for s in ollama_tool_schemas()}

    async with Client(server_params()) as client:
        listed = await client.list_tools()
    phase2 = {s["function"]["name"]: s for s in to_ollama_schemas(listed.tools)}

    assert phase1 == phase2


async def test_mcp_tool_call_returns_json_payload():
    """브라우저가 필요 없는 도구(get_today)로 MCP 왕복을 확인한다."""
    async with Client(server_params()) as client:
        response = await client.call_tool("get_today", {})

    text = next(c.text for c in response.content if getattr(c, "type", None) == "text")
    payload = json.loads(text)
    assert payload["ok"] is True
    assert len(payload["today"]) == 10


async def test_tool_failure_travels_as_data_not_protocol_error():
    """도구 실패는 isError 가 아니라 {"ok": false} 페이로드로 와야 한다 (Phase 1 과 동일)."""
    async with Client(server_params()) as client:
        response = await client.call_tool(
            "search_trains", {"departure": "서울", "arrival": "부산", "date": "내일모레"}
        )

    text = next(c.text for c in response.content if getattr(c, "type", None) == "text")
    payload = json.loads(text)
    assert payload["ok"] is False
    assert "YYYY-MM-DD" in payload["error"]
