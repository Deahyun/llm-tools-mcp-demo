"""예제 13 (클라이언트) — MCP HTTP 서버에 URL 로 붙어 LLM 에이전트를 돌린다.

먼저 다른 터미널에서 서버를 띄웁니다.

    python demo/13_mcp_http_server.py

그다음 이 파일을 실행합니다.

    python demo/13_mcp_http_client.py
    python demo/13_mcp_http_client.py "hello 로 test 해줘"
    python demo/13_mcp_http_client.py --url http://127.0.0.1:9000/mcp

**이 파일에는 도구 코드가 한 줄도 없습니다.** `test()` 도, 도구 명세도 없습니다.
그래서 이 파일만 보면 어떤 도구가 있는지 알 수 없습니다 — 알아내는 방법은 하나뿐입니다.

    listed = await mcp.list_tools()      # 서버에게 물어본다
    schemas = to_ollama_schemas(listed.tools)

그리고 실행도 직접 하지 않고 서버에 맡깁니다.

    response = await mcp.call_tool(name, arguments)

11번(native)에서는 이 두 가지가 코드 안에 있었습니다. 그것을 프로세스 밖으로 밀어낸 것이
MCP 이고, 파일이 둘로 나뉘어 있어야 그 경계가 눈에 보입니다.

**그대로인 것**: 에이전트 루프. 아래 run_agent 부분은 11/12 번과 구조가 같습니다.
바뀌는 것은 도구를 조달하는 경로뿐입니다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from mcp import Client
from ollama import AsyncClient

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

MODEL = os.getenv("OLLAMA_MODEL", "qwen3.8-local:27b")
MAX_ITERATIONS = 5
DEFAULT_MCP_URL = "http://127.0.0.1:8932/mcp"
DEFAULT_QUERY = "안녕하세요 라는 문자열로 test 도구를 실행하고 결과를 알려줘."


def normalize_host(raw: str) -> str:
    """Ollama 접속 주소 정규화.

    이 PC 의 시스템 환경변수는 `OLLAMA_HOST=0.0.0.0:11434` 입니다. 이건 서버가
    *바인딩* 하는 주소인데 클라이언트가 *접속* 주소로 그대로 쓰면 ConnectionError 가 납니다.
    """
    host = (raw or "").strip() or "http://127.0.0.1:11434"
    if "://" not in host:
        host = "http://" + host
    return host.replace("//0.0.0.0:", "//127.0.0.1:").replace("//[::]:", "//127.0.0.1:")


OLLAMA_HOST = normalize_host(os.getenv("OLLAMA_HOST", ""))


SYSTEM_PROMPT = (
    "당신은 도구를 사용하는 에이전트입니다. "
    "사용자가 문자열 가공을 요청하면 반드시 test 도구를 호출하세요. "
    "추측해서 답하지 말고, 도구가 돌려준 result 값을 그대로 인용해 한국어로 간결히 답하세요."
)


# ---------------------------------------------------------------------------
# MCP → Ollama 번역
# ---------------------------------------------------------------------------


def to_ollama_schemas(mcp_tools) -> list[dict[str, Any]]:
    """MCP Tool 목록 → Ollama function calling 스키마.

    이 번역을 거치고 나면 모델에게 보내는 tools 배열은 11번(native)의 것과 사실상
    같아집니다. **모델은 MCP 를 쓰는지 모릅니다.**
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema or {"type": "object", "properties": {}},
            },
        }
        for t in mcp_tools
    ]


def first_text(response) -> str | None:
    """MCP 응답 콘텐츠 목록에서 첫 번째 텍스트를 꺼낸다."""
    for item in getattr(response, "content", None) or []:
        if getattr(item, "type", None) == "text":
            return item.text
    return None


# ---------------------------------------------------------------------------
# 에이전트 루프
# ---------------------------------------------------------------------------


async def chat(client: AsyncClient, messages: list[dict[str, Any]], schemas: list[dict[str, Any]]):
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "tools": schemas,
        "options": {"temperature": 0},  # 인자 파싱에 창의성은 필요 없다
    }
    try:
        return await client.chat(think=False, **kwargs)  # thinking 끄면 응답이 빠르다
    except TypeError:
        return await client.chat(**kwargs)  # 구버전 ollama-python 은 think 를 모른다


async def run_agent(url: str, query: str) -> str:
    ollama = AsyncClient(host=OLLAMA_HOST)

    # 12번(stdio)은 여기에 StdioServerParameters 를 넣었다. URL 문자열로 바뀐 것이 전부다.
    async with Client(url) as mcp:
        listed = await mcp.list_tools()
        schemas = to_ollama_schemas(listed.tools)
        print(f"[mcp] list_tools -> {[t.name for t in listed.tools]}")

        async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            """도구 실행을 서버에 위임한다. 이 프로세스는 도구 구현을 모른다."""
            try:
                response = await mcp.call_tool(name, arguments)
            except Exception as exc:  # noqa: BLE001 - 실패도 LLM 에게 데이터로 넘긴다
                return {"ok": False, "error": f"MCP 호출 실패: {type(exc).__name__}: {exc}"}
            text = first_text(response)
            if text is None:
                return {"ok": False, "error": "MCP 응답에 텍스트 콘텐츠가 없습니다."}
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"ok": True, "text": text}

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        for step in range(1, MAX_ITERATIONS + 1):
            response = await chat(ollama, messages, schemas)
            message = response.message
            tool_calls = getattr(message, "tool_calls", None) or []

            assistant: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            if tool_calls:
                assistant["tool_calls"] = [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ]
            messages.append(assistant)

            if not tool_calls:
                print(f"[{step}] 도구 호출 없음 -> 종료")
                return (message.content or "").strip()

            for tc in tool_calls:
                name = tc.function.name
                args = tc.function.arguments
                if isinstance(args, str):  # 모델이 JSON 문자열로 줄 때가 있다
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                args = dict(args or {})

                print(f"[{step}] 도구 호출: {name}({args})  <- MCP over HTTP")
                result = await call_tool(name, args)
                print(f"[{step}] 도구 결과: {result}")

                messages.append(
                    {
                        "role": "tool",
                        "name": name,
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return "도구 호출 횟수 상한에 도달해 중단했습니다."


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def _root_cause(exc: BaseException) -> str:
    """가장 안쪽 원인 예외를 한 줄로 요약한다.

    MCP/anyio 는 예외를 그룹으로 감싸 던지므로 겉면만 보면 원인을 알 수 없습니다.
    ExceptionGroup 은 3.11+ 문법이라 `except*` 대신 속성으로 풀어 봅니다.
    """
    seen = exc
    for _ in range(10):  # 순환 참조 방어
        inner = getattr(seen, "exceptions", None)  # ExceptionGroup
        if inner:
            seen = inner[0]
            continue
        if seen.__cause__ is not None:
            seen = seen.__cause__
            continue
        break
    return f"{type(seen).__name__}: {seen}"


async def main() -> int:
    parser = argparse.ArgumentParser(description="MCP HTTP 클라이언트 + LLM 에이전트 (예제 13)")
    parser.add_argument(
        "--url", default=DEFAULT_MCP_URL, help=f"MCP 서버 주소 (기본 {DEFAULT_MCP_URL})"
    )
    parser.add_argument("query", nargs="*", help="LLM 에게 보낼 질의")
    args = parser.parse_args()

    query = " ".join(args.query).strip() or DEFAULT_QUERY

    print("=" * 70)
    print(f"[13] MCP (streamable http)   model={MODEL}   host={OLLAMA_HOST}")
    print(f"[13] MCP 서버: {args.url}")
    print(f"질의: {query}")
    print("=" * 70)

    try:
        answer = await run_agent(args.url, query)
    except Exception as exc:  # noqa: BLE001 - 원인을 알려 주는 것이 traceback 보다 낫다
        # 서버가 안 떠 있으면 여기로 온다. SDK 가 던지는 예외는 중첩이 깊어 traceback 이
        # 수십 줄 나오고 정작 원인("서버가 없다")이 묻힌다. 그래서 짧게 요약해서 알린다.
        print(f"\n[오류] MCP 서버에 붙지 못했습니다: {args.url}", file=sys.stderr)
        print(f"       원인: {_root_cause(exc)}", file=sys.stderr)
        print("       다른 터미널에서 서버를 먼저 띄우세요:", file=sys.stderr)
        print("       python demo/13_mcp_http_server.py", file=sys.stderr)
        return 1

    print("-" * 70)
    print(answer or "(응답 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
