"""예제 13 (서버 · 고수준 API) — `13_mcp_http_server.py` 와 **같은 일을 15줄로**.

    python demo/13_mcp_fastapi_style.py               # http://127.0.0.1:8932/mcp
    python demo/13_mcp_fastapi_style.py --port 9000

클라이언트는 그대로입니다. 포트도 같으므로 **아무것도 고치지 않고** 붙습니다.

    python demo/13_mcp_http_client.py

그리고 클라이언트는 이 서버가 저수준으로 짜였는지 고수준으로 짜였는지 **구별할 수 없습니다.**
프로토콜로 나가는 것이 같기 때문입니다. 그것이 이 예제가 보여 주려는 것입니다.

---

`13_mcp_http_server.py` 는 프로토콜을 손으로 다룹니다 (저수준 `Server`).

    on_list_tools()  →  types.ListToolsResult(tools=[types.Tool(...)])
    on_call_tool()   →  types.CallToolResult(content=[types.TextContent(...)])
    uvicorn.run(server.streamable_http_app(...))

이 파일은 SDK 에게 맡깁니다 (고수준 `MCPServer`). FastAPI 에서 `@app.get` 하나로
라우트가 만들어지는 것과 같은 감각이라 흔히 'FastAPI 스타일'이라고 부릅니다.

    @mcp.tool()              →  스키마 자동 생성 + list_tools 자동 응답
    def test(a: str) -> str  →  반환값 자동 포장 + call_tool 자동 처리
    mcp.run("streamable-http")

**요즘 새로 MCP 서버를 만들 때는 대개 이쪽입니다.** 저수준은 프로토콜을 세밀하게
제어해야 하거나, 이 저장소 본체처럼 도구 정의를 다른 곳(registry)이 갖고 있어서
번역만 하면 될 때 씁니다.

주의: 인증이 없는 서버입니다. 기본 바인딩은 루프백(127.0.0.1)이며 로컬 학습용입니다.
"""

from __future__ import annotations

import argparse
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

SERVER_NAME = "demo-test-tool-http"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8932
HTTP_PATH = "/mcp"

mcp = MCPServer(
    SERVER_NAME,
    version="0.1.0",
    title="문자열 test 도구 (HTTP · 고수준 API)",
    instructions="문자열 앞뒤에 표식을 붙이는 도구 하나만 제공합니다.",
)


# ---------------------------------------------------------------------------
# 도구 — 이 데코레이터 하나가 저수준 판의 핸들러 두 개를 대신한다
# ---------------------------------------------------------------------------


def test(a: str) -> str:
    """11/12/13 저수준 판과 완전히 같은 도구 본체. 여기는 MCP 를 모른다."""
    res = "123---" + a + "---456"
    print(f"{res}")
    return res


@mcp.tool(
    name="test",
    description=(
        "문자열 하나를 받아 앞에 '123---', 뒤에 '---456' 을 붙여 돌려준다. "
        "사용자가 어떤 값을 test 해 달라고 하면 반드시 이 도구를 호출한다. "
        "직접 문자열을 만들어 답하지 말고 도구의 반환값을 그대로 사용한다."
    ),
)
def test_tool(a: Annotated[str, Field(description="가공할 문자열. 예: 안녕하세요")]) -> dict:
    """저수준 판의 on_call_tool 과 **같은 페이로드 규약**을 유지한다.

    str 을 그대로 반환하면 SDK 가 평문 텍스트로 포장해 보내고, 클라이언트는
    JSON 파싱에 실패해 {"ok": true, "text": ...} 로 받습니다. dict 를 반환하면
    JSON 으로 직렬화되어 {"ok": true, "result": ...} 가 그대로 건너갑니다.
    """
    return {"ok": True, "result": test(a)}


# 위 데코레이터 한 덩어리가 대신해 주는 것:
#
#   1. 타입 힌트 `a: str` → JSON Schema {"a": {"type": "string"}} 생성
#   2. Annotated[..., Field(description=...)] → 그 인자의 description 채우기
#   3. list_tools 요청이 오면 이 도구를 목록에 담아 응답
#   4. call_tool 요청이 오면 인자를 검증해 함수 호출
#   5. 반환값을 TextContent 로 포장 (+ structured_content 도 함께)
#   6. 함수가 예외를 던지면 is_error 결과로 변환
#
# 함정 1 — 인자 설명은 **자동으로 안 나옵니다.** docstring 의 Args: 절을 파싱하지 않으므로
# Annotated + Field 로 직접 붙여야 합니다. 안 붙이면 스키마가 {"title": "A"} 만 남고
# 모델이 그 인자가 무엇인지 알 방법이 사라집니다. "docstring 이 곧 프롬프트"라는
# 원칙을 지키려면 이 한 줄이 필요합니다.
#
# 함정 2 — 위 6번은 저수준 판과 **다른 동작**입니다. 저수준 판은 실패를
# {"ok": false, "error": ...} 라는 데이터로 돌려줘 LLM 이 읽고 복구하게 했습니다.
# 고수준 판에서 예외를 던지면 is_error 결과가 되어 그 복구 경로가 끊깁니다.
# 같은 동작을 원하면 예외를 던지지 말고 dict 를 반환하세요 — 위 test_tool 처럼.


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP 고수준 API 서버 (예제 13)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="바인딩 주소 (기본 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="포트 (기본 8932)")
    args = parser.parse_args()

    print(f"[server] {SERVER_NAME} (고수준 MCPServer)")
    print(f"[server] http://{args.host}:{args.port}{HTTP_PATH} 에서 대기 중 (Ctrl+C 로 종료)")
    print("[server] 클라이언트: python demo/13_mcp_http_client.py")

    # uvicorn 을 직접 부르지 않는다. run() 이 ASGI 앱 생성부터 서빙까지 처리한다.
    # transport 만 바꾸면 같은 서버가 stdio 로도 뜬다 — mcp.run("stdio")
    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path=HTTP_PATH,
    )


if __name__ == "__main__":
    main()
