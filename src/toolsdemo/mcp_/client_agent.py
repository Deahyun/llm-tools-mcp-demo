"""Phase 2 진입점 — **MCP 클라이언트**를 통해 같은 도구를 사용한다.

Phase 1(`agent_tools.py`)과 비교하면 차이는 두 가지뿐입니다:
  * 도구 스키마를 registry 가 아니라 MCP `list_tools()` 응답에서 얻는다
  * 도구 실행을 함수 직접 호출이 아니라 MCP `call_tool()` 로 위임한다

에이전트 루프(`OllamaAgent`)와 도구 구현은 Phase 1 과 완전히 동일합니다.

    python -m toolsdemo.mcp_.client_agent "내일 오전 9시쯤 서울에서 부산 가는 KTX 예약해줘"

트랜스포트는 `MCP_TRANSPORT` 로 고릅니다. 에이전트 루프와 도구는 어느 쪽이든 동일합니다.

  * `stdio`(기본) — 클라이언트가 서버를 자식 프로세스로 직접 띄운다. 준비할 것이 없다.
  * `http`        — 미리 띄워 둔 Streamable HTTP 서버에 URL 로 접속한다.
                    `python -m toolsdemo.mcp_.http_server` 를 먼저 실행해야 한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import Client, StdioServerParameters

from ..config import PROJECT_ROOT, settings, setup_logging
from ..llm.ollama_client import OllamaAgent

DEFAULT_QUERY = "내일 오전 9시쯤 서울에서 부산 가는 기차 예약해줘"


def server_params() -> StdioServerParameters:
    env = dict(os.environ)
    # editable 설치가 안 되어 있어도 서버 프로세스가 패키지를 찾을 수 있게 한다
    src = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "toolsdemo.mcp_.server"],
        env=env,
        cwd=str(PROJECT_ROOT),
    )


def client_target() -> StdioServerParameters | str:
    """MCP 접속 대상. 문자열이면 Streamable HTTP URL, 아니면 stdio 로 띄울 서버 파라미터.

    SDK 의 `Client` 는 둘 다 받습니다. 그래서 트랜스포트를 바꿔도 아래 `run()` 은
    한 줄도 달라지지 않습니다.
    """
    if settings.mcp_transport == "http":
        return settings.mcp_http_endpoint
    return server_params()


def to_ollama_schemas(mcp_tools) -> list[dict[str, Any]]:
    """MCP Tool 목록 → Ollama function calling 스키마."""
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


def _first_text(response) -> Any:
    for item in getattr(response, "content", None) or []:
        if getattr(item, "type", None) == "text":
            return item.text
    return None


async def run(query: str) -> int:
    async with Client(client_target()) as client:
        listed = await client.list_tools()
        schemas = to_ollama_schemas(listed.tools)

        async def caller(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            try:
                response = await client.call_tool(name, arguments)
            except Exception as exc:  # noqa: BLE001 - 실패도 LLM 에게 데이터로 전달한다
                return {"ok": False, "error": f"MCP 호출 실패: {type(exc).__name__}: {exc}"}

            text = _first_text(response)
            if text is None:
                return {"ok": False, "error": "MCP 응답에 텍스트 콘텐츠가 없습니다."}
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"ok": True, "text": text}

        agent = OllamaAgent(tool_schemas=schemas, tool_caller=caller)

        print(
            f"\n[Phase 2 · MCP]  model={settings.ollama_model}  "
            f"target={settings.target_site}  transport={settings.mcp_transport}  "
            f"mcp_tools={len(schemas)}"
        )
        print(f"질의: {query}\n" + "-" * 70)

        result = await agent.run(query)

        print("-" * 70)
        print(f"도구 호출 {len(result.tool_calls)}회 / 반복 {result.iterations}회")
        print(result.answer or "(응답 없음)")
        return 1 if result.stopped_by_limit else 0


def main() -> None:
    setup_logging()
    query = " ".join(sys.argv[1:]).strip() or DEFAULT_QUERY
    sys.exit(asyncio.run(run(query)))


if __name__ == "__main__":
    main()
