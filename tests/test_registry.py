"""registry 의 스키마 자동 생성 / 안전한 도구 호출 검증. LLM·브라우저 불필요."""

from __future__ import annotations

from typing import Any

import pytest

from toolsdemo.tools import registry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """전역 레지스트리를 건드리지 않도록 테스트마다 비운다."""
    monkeypatch.setattr(registry, "_REGISTRY", {})
    yield


def test_schema_from_type_hints_and_docstring():
    @registry.tool
    async def sample(city: str, days: int = 3, tags: list[str] | None = None) -> dict[str, Any]:
        """도시의 날씨를 조회한다.

        Args:
            city: 도시 이름. 예: 서울
            days: 조회할 일수
            tags: 필터 태그 목록
        """
        return {"ok": True}

    spec = registry.get_registry()["sample"]
    assert spec.description == "도시의 날씨를 조회한다."

    props = spec.parameters["properties"]
    assert props["city"] == {"type": "string", "description": "도시 이름. 예: 서울"}
    assert props["days"]["type"] == "integer"
    assert props["days"]["default"] == 3
    assert props["tags"]["type"] == "array"
    assert props["tags"]["items"]["type"] == "string"

    # 기본값 없는 인자만 required
    assert spec.parameters["required"] == ["city"]


def test_ollama_schema_shape():
    @registry.tool
    async def ping() -> dict[str, Any]:
        """연결을 확인한다."""
        return {"ok": True}

    schemas = registry.ollama_tool_schemas()
    assert len(schemas) == 1
    fn = schemas[0]["function"]
    assert schemas[0]["type"] == "function"
    assert fn["name"] == "ping"
    assert fn["parameters"] == {"type": "object", "properties": {}, "required": []}


def test_sync_function_is_rejected():
    with pytest.raises(TypeError):

        @registry.tool
        def not_async(x: str) -> dict:
            """동기 함수는 도구가 될 수 없다."""
            return {}


def test_missing_docstring_is_rejected():
    with pytest.raises(ValueError):

        @registry.tool
        async def undocumented(x: str) -> dict:
            return {}


async def test_unknown_tool_returns_error_not_exception():
    result = await registry.call_tool("nope", {})
    assert result["ok"] is False
    assert "nope" in result["error"]


async def test_undefined_arguments_are_dropped():
    seen = {}

    @registry.tool
    async def echo(value: str) -> dict[str, Any]:
        """값을 그대로 돌려준다.

        Args:
            value: 아무 문자열
        """
        seen["value"] = value
        return {"ok": True, "value": value}

    # 모델이 스키마에 없는 인자를 지어내도 죽지 않아야 한다
    result = await registry.call_tool("echo", {"value": "hi", "hallucinated": 1})
    assert result == {"ok": True, "value": "hi"}
    assert seen == {"value": "hi"}


async def test_tool_exception_becomes_error_dict():
    @registry.tool
    async def boom() -> dict[str, Any]:
        """항상 실패한다."""
        raise RuntimeError("터졌다")

    result = await registry.call_tool("boom", {})
    assert result["ok"] is False
    assert "터졌다" in result["error"]


async def test_missing_required_argument_becomes_error_dict():
    @registry.tool
    async def needs_arg(value: str) -> dict[str, Any]:
        """인자가 필요하다.

        Args:
            value: 필수 문자열
        """
        return {"ok": True}

    result = await registry.call_tool("needs_arg", {})
    assert result["ok"] is False
    assert "인자 오류" in result["error"]
