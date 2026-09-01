"""예제 13 (서버) — 도구를 **MCP Streamable HTTP 서버**로 노출한다.

    python demo/13_mcp_http_server.py                 # http://127.0.0.1:8932/mcp
    python demo/13_mcp_http_server.py --port 9000

이 프로세스를 먼저 띄워 두고, 다른 터미널에서 클라이언트를 실행합니다.

    python demo/13_mcp_http_client.py

**이 파일에만 도구가 있습니다.** `test()` 도, 도구 명세도 여기 있고 여기서 실행됩니다.
짝이 되는 `13_mcp_http_client.py` 에는 도구 코드가 한 줄도 없습니다 — 어떤 도구가 있는지는
`list_tools()` 로 물어보고, 실행은 `call_tool()` 로 이 서버에 맡깁니다.
그것이 MCP를 쓰는 이유이고, 파일을 둘로 나눈 이유입니다.

12번(stdio)과 비교하면 **핸들러와 도구는 그대로이고 트랜스포트만 다릅니다.**
그리고 stdout 금지 규칙이 사라집니다 — 프로토콜이 소켓으로 가므로 `test()` 의 print 가
JSON-RPC 를 깨지 않습니다. (12번에서 redirect_stdout 이 필요했던 이유)

주의: 인증이 없는 서버입니다. 기본 바인딩은 루프백(127.0.0.1)이며 로컬 학습용입니다.
      `--host 0.0.0.0` 으로 열면 네트워크의 누구나 이 도구를 호출할 수 있게 됩니다.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

import mcp.types as types
import uvicorn
from mcp.server import Server, ServerRequestContext

logger = logging.getLogger(__name__)

SERVER_NAME = "demo-test-tool-http"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8932
HTTP_PATH = "/mcp"


# ---------------------------------------------------------------------------
# 도구 — 11/12 번과 완전히 같은 구현
# ---------------------------------------------------------------------------


def test(a: str) -> str:
    res = "123---" + a + "---456"
    print(f"{res}")
    return res


TOOL_NAME = "test"
TOOL_DESCRIPTION = (
    "문자열 하나를 받아 앞에 '123---', 뒤에 '---456' 을 붙여 돌려준다. "
    "사용자가 어떤 값을 test 해 달라고 하면 반드시 이 도구를 호출한다. "
    "직접 문자열을 만들어 답하지 말고 도구의 반환값을 그대로 사용한다."
)
TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "a": {"type": "string", "description": "가공할 문자열. 예: 안녕하세요"},
    },
    "required": ["a"],
}


# ---------------------------------------------------------------------------
# MCP 핸들러 — 서버가 답해야 하는 두 가지 질문
# ---------------------------------------------------------------------------


async def on_list_tools(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """어떤 도구가 있나 — 클라이언트는 이 응답으로만 도구를 알게 된다."""
    logger.info("[mcp] list_tools -> %s", TOOL_NAME)
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name=TOOL_NAME,
                description=TOOL_DESCRIPTION,
                input_schema=TOOL_INPUT_SCHEMA,  # SDK 2.x 는 inputSchema 가 아니라 input_schema
            )
        ]
    )


async def on_call_tool(
    ctx: ServerRequestContext, params: types.CallToolRequestParams
) -> types.CallToolResult:
    """이 도구를 이 인자로 실행해 달라 — 실제 실행은 오직 여기서 일어난다.

    HTTP 트랜스포트라 stdout 을 막을 필요가 없습니다. test() 의 print 는
    이 서버 콘솔에 그대로 찍힙니다.
    """
    args = dict(params.arguments or {})
    logger.info("[mcp] call_tool %s(%s)", params.name, args)

    if params.name != TOOL_NAME:
        payload: dict[str, Any] = {"ok": False, "error": f"알 수 없는 도구입니다: {params.name}"}
    else:
        a = args.get("a")
        if not isinstance(a, str) or not a:
            payload = {"ok": False, "error": "인자 a 는 비어 있지 않은 문자열이어야 합니다."}
        else:
            payload = {"ok": True, "result": test(a)}

    # 실패도 예외가 아니라 데이터로 보낸다. is_error 를 쓰지 않는 이유이고,
    # 그래야 11번(native)의 동작과 정확히 같아진다.
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    )


server = Server(
    SERVER_NAME,
    version="0.1.0",
    title="문자열 test 도구 (HTTP)",
    instructions="문자열 앞뒤에 표식을 붙이는 도구 하나만 제공합니다.",
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


# ---------------------------------------------------------------------------
# 기동
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP Streamable HTTP 서버 (예제 13)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="바인딩 주소 (기본 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="포트 (기본 8932)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # MCP SDK 가 우리 server 객체를 ASGI 앱으로 감싸 준다. uvicorn 이 그 앱을 포트에 물린다.
    app = server.streamable_http_app(streamable_http_path=HTTP_PATH, host=args.host)

    print(f"[server] {SERVER_NAME}")
    print(f"[server] http://{args.host}:{args.port}{HTTP_PATH} 에서 대기 중 (Ctrl+C 로 종료)")
    print(
        f"[server] 클라이언트: python demo/13_mcp_http_client.py --url "
        f"http://{args.host}:{args.port}{HTTP_PATH}"
    )

    # uvicorn.run 이 자체 이벤트 루프를 돌린다. 그래서 이 함수는 async 가 아니고,
    # asyncio.run() 으로 감싸서도 안 된다 (루프 중첩 에러).
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
