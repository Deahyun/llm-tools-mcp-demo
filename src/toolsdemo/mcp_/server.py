"""Phase 2 — 도구 레지스트리를 **MCP 서버**로 노출한다 (stdio 트랜스포트).

Phase 1 과 도구 구현은 완전히 동일합니다. 이 파일은 registry 를 MCP 프로토콜로
번역하는 얇은 래퍼일 뿐입니다. 새 도구를 추가해도 이 파일은 손댈 필요가 없습니다.

    python -m toolsdemo.mcp_.server      # 보통 클라이언트가 자동 기동. 단독 실행은 디버깅용

주의 1: stdout 은 JSON-RPC 전용입니다. **이 경로에서 print() 를 쓰지 마세요.**
        로그는 logging(stderr)으로만 남깁니다.
주의 2: MCP SDK 2.x 기준입니다. 1.x 의 `@server.list_tools()` 데코레이터 방식이 아니라
        `Server(on_list_tools=..., on_call_tool=...)` 콜백 방식을 씁니다.
"""

from __future__ import annotations

import asyncio
import json
import logging

import mcp.types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from .. import __version__
from ..config import setup_logging
from ..tools import booking  # noqa: F401 - import 시점에 도구가 registry 에 등록된다
from ..tools.browser import close_browser
from ..tools.registry import call_tool, get_registry

logger = logging.getLogger(__name__)

SERVER_NAME = "toolsdemo-booking"


async def on_list_tools(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    tools = [
        types.Tool(
            name=spec.name,
            description=spec.description,
            input_schema=spec.parameters,
        )
        for spec in get_registry().values()
    ]
    logger.info("[mcp] list_tools → %d개: %s", len(tools), ", ".join(t.name for t in tools))
    return types.ListToolsResult(tools=tools)


async def on_call_tool(
    ctx: ServerRequestContext, params: types.CallToolRequestParams
) -> types.CallToolResult:
    result = await call_tool(params.name, dict(params.arguments or {}))

    # is_error 를 쓰지 않는 이유: 도구 실패는 {"ok": false, "error": ...} 라는 **데이터**로
    # LLM 에게 전달되어야 하며, 이는 Phase 1 의 동작과 정확히 같아야 합니다.
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))
        ]
    )


server = Server(
    SERVER_NAME,
    version=__version__,
    title="기차 예약 도구",
    instructions=(
        "기차 조회부터 예약(좌석 확보)까지 수행하는 도구 모음입니다. "
        "결제와 발권은 제공하지 않으며 사람이 직접 진행해야 합니다."
    ),
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


async def serve() -> None:
    logger.info("[mcp] %s 시작 (stdio)", SERVER_NAME)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await close_browser()
        logger.info("[mcp] %s 종료", SERVER_NAME)


def main() -> None:
    setup_logging()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
