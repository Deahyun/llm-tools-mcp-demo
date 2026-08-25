"""도구 레지스트리 — Phase 1(native tools)과 Phase 2(MCP)의 **단일 진실 원천**.

`@tool` 데코레이터로 등록하면 타입 힌트와 docstring 에서 JSON Schema 를 자동 생성합니다.
JSON Schema 를 손으로 쓰지 마세요. 여기 한 번 등록하면 두 Phase 모두에 자동 노출됩니다.

docstring 형식 (Google 스타일)::

    한 줄 요약. LLM 이 언제 이 도구를 쓸지 판단하는 근거가 됩니다.

    Args:
        departure: 출발역 이름 (예: 서울)
        date: 출발 날짜, YYYY-MM-DD 형식
"""

from __future__ import annotations

import inspect
import logging
import re
import types
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

ToolFn = Callable[..., Awaitable[dict[str, Any]]]

_JSON_TYPES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn = field(repr=False)


_REGISTRY: dict[str, ToolSpec] = {}


def _split_docstring(doc: str) -> tuple:
    """docstring 을 (요약, {인자명: 설명}) 으로 분리."""
    doc = inspect.cleandoc(doc or "")
    parts = re.split(r"^\s*(?:Args|Arguments|Params|Parameters)\s*:\s*$", doc, flags=re.M)
    summary = parts[0].strip()
    arg_docs: dict[str, str] = {}
    if len(parts) > 1:
        # Returns: 등 다음 섹션이 나오면 거기서 멈춘다
        body = re.split(
            r"^\s*(?:Returns|Raises|Note|Notes|Example)s?\s*:\s*$", parts[1], flags=re.M
        )[0]
        current = None
        for line in body.splitlines():
            m = re.match(r"^\s{0,8}(\*{0,2}\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)$", line)
            if m:
                current = m.group(1).lstrip("*")
                arg_docs[current] = m.group(2).strip()
            elif current and line.strip():
                arg_docs[current] += " " + line.strip()
    return summary, arg_docs


def _json_type(annotation: Any) -> dict[str, Any]:
    """파이썬 타입 힌트를 JSON Schema 조각으로 변환."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # typing.Union 과 PEP 604 의 `X | None`(types.UnionType) 을 모두 받는다.
    # get_type_hints 는 보통 전자로 정규화하지만, 평가에 실패하면 후자가 그대로 들어온다.
    if origin is typing.Union or origin is types.UnionType:  # Optional[X] 포함
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _json_type(non_none[0])
        return {"type": "string"}

    if origin in (list, list):
        item = args[0] if args else str
        return {"type": "array", "items": _json_type(item)}

    if origin in (dict, dict):
        return {"type": "object"}

    if isinstance(annotation, type) and issubclass(annotation, bool):
        return {"type": "boolean"}

    for py_type, js_type in _JSON_TYPES.items():
        if annotation is py_type:
            return {"type": js_type}

    if isinstance(annotation, type) and issubclass(annotation, (int, float, str)):
        return {"type": _JSON_TYPES[annotation.__mro__[1]]}

    return {"type": "string"}


def _build_schema(fn: ToolFn) -> tuple:
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # 전방참조 실패 시에도 등록은 되게 한다
        hints = {}

    summary, arg_docs = _split_docstring(fn.__doc__ or "")
    if not summary:
        raise ValueError(
            f"도구 {fn.__name__} 에 docstring 요약이 없습니다. docstring 이 곧 프롬프트입니다."
        )

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        schema = _json_type(hints.get(name, param.annotation))
        desc = arg_docs.get(name)
        if desc:
            schema["description"] = desc
        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default
        else:
            required.append(name)
        properties[name] = schema

    parameters = {"type": "object", "properties": properties, "required": required}
    return summary, parameters


def tool(fn: ToolFn) -> ToolFn:
    """async 함수를 도구로 등록하는 데코레이터."""
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(f"도구 {fn.__name__} 는 async 함수여야 합니다.")

    description, parameters = _build_schema(fn)
    spec = ToolSpec(name=fn.__name__, description=description, parameters=parameters, fn=fn)
    if spec.name in _REGISTRY:
        raise ValueError(f"도구 이름 중복: {spec.name}")
    _REGISTRY[spec.name] = spec
    logger.debug("도구 등록: %s(%s)", spec.name, ", ".join(parameters["properties"]))
    return fn


def get_registry() -> dict[str, ToolSpec]:
    return dict(_REGISTRY)


def ollama_tool_schemas() -> list[dict[str, Any]]:
    """Ollama function calling 용 tools 배열."""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in _REGISTRY.values()
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """도구를 실행한다. **예외를 던지지 않고** 항상 dict 를 반환한다.

    LLM 이 결과를 읽고 스스로 복구해야 하므로 실패도 데이터로 돌려준다.
    """
    spec = _REGISTRY.get(name)
    if spec is None:
        return {"ok": False, "error": f"알 수 없는 도구: {name}", "available": list(_REGISTRY)}

    arguments = arguments or {}
    logger.info("[tool] → %s(%s)", name, arguments)
    try:
        # 모델이 스키마에 없는 인자를 만들어 보내는 경우가 있어 걸러낸다
        allowed = set(spec.parameters["properties"])
        cleaned = {k: v for k, v in arguments.items() if k in allowed}
        dropped = set(arguments) - allowed
        if dropped:
            logger.warning("[tool] %s: 미정의 인자 무시 %s", name, sorted(dropped))
        result = await spec.fn(**cleaned)
    except TypeError as exc:
        result = {"ok": False, "error": f"인자 오류: {exc}", "expected": spec.parameters}
    except Exception as exc:  # noqa: BLE001 - 도구 실패는 LLM 에게 전달되어야 한다
        logger.exception("[tool] %s 실행 실패", name)
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    logger.info("[tool] ← %s: %s", name, result)
    return result
