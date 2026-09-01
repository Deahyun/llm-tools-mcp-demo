"""예제 12 — 같은 도구를 **MCP 서버(stdio)** 로 노출하고 MCP 클라이언트로 호출한다.

실행 (이 파일 하나로 끝. 서버를 따로 띄울 필요 없음):

    python demo/12_mcp_local.py
    python demo/12_mcp_local.py "hello 로 test 해줘"

한 파일이 두 역할을 겸합니다. 클라이언트가 **자기 자신을 `--server` 인자로 자식
프로세스로 띄우고**, 그 프로세스의 stdin/stdout 파이프로 JSON-RPC 를 주고받습니다.

    [이 프로세스: 클라이언트]                    [자식 프로세스: MCP 서버]
      Client(StdioServerParameters(  ──spawn──▶   python 12_mcp_local.py --server
        command=python,
        args=[__file__, "--server"]))
             │  list_tools()  ──── stdin ───▶  on_list_tools → 도구 명세
             │  call_tool()   ──── stdin ───▶  on_call_tool  → test() 실행
             ◀────────────────── stdout ─────  JSON 결과

11번(native)과 비교해 **달라지는 것**:
  * 도구 명세를 코드에 쓴 dict 가 아니라 list_tools() 응답에서 받는다
  * 도구 실행이 함수 직접 호출이 아니라 call_tool() 프로토콜 왕복이다
  * 도구가 별도 프로세스에서 돈다

**그대로인 것**: test() 구현, 에이전트 루프, 모델에게 보이는 tools 배열, 최종 결과.

주의: stdio 트랜스포트에서 stdout 은 JSON-RPC 전용입니다. 서버 쪽에서 print() 를 하면
프로토콜이 깨집니다. 이 예제의 test() 는 print 를 하므로 아래 on_call_tool 에서
stdout 을 stderr 로 돌려 놓고 실행합니다. (MCP SDK 2.x 기준)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp import Client, StdioServerParameters
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from ollama import AsyncClient

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

MODEL = os.getenv("OLLAMA_MODEL", "qwen3.8-local:27b")
MAX_ITERATIONS = 5
SERVER_NAME = "demo-test-tool"
DEFAULT_QUERY = "안녕하세요 라는 문자열로 test 도구를 실행하고 결과를 알려줘."


def normalize_host(raw: str) -> str:
    """Ollama 접속 주소 정규화 (0.0.0.0 은 바인딩 주소이지 접속 주소가 아니다)."""
    host = (raw or "").strip() or "http://127.0.0.1:11434"
    if "://" not in host:
        host = "http://" + host
    return host.replace("//0.0.0.0:", "//127.0.0.1:").replace("//[::]:", "//127.0.0.1:")


OLLAMA_HOST = normalize_host(os.getenv("OLLAMA_HOST", ""))


# ---------------------------------------------------------------------------
# 도구 — 11/13 번과 완전히 같은 구현
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


# ===========================================================================
# 1) 서버 쪽 —  python 12_mcp_local.py --server  로 실행될 때
# ===========================================================================


async def on_list_tools(
    ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    """클라이언트가 '어떤 도구가 있나' 물을 때 답한다."""
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
    """실제 도구 실행. 결과는 JSON 텍스트 콘텐츠로 돌려준다."""
    args = dict(params.arguments or {})

    if params.name != TOOL_NAME:
        payload: dict[str, Any] = {"ok": False, "error": f"알 수 없는 도구입니다: {params.name}"}
    else:
        a = args.get("a")
        if not isinstance(a, str) or not a:
            payload = {"ok": False, "error": "인자 a 는 비어 있지 않은 문자열이어야 합니다."}
        else:
            # test() 안의 print 가 stdout 으로 나가면 JSON-RPC 가 깨진다.
            # stdout 을 stderr 로 돌려 놓고 실행하면 화면에는 그대로 보이면서 안전하다.
            with contextlib.redirect_stdout(sys.stderr):
                payload = {"ok": True, "result": test(a)}

    # 실패도 예외가 아니라 데이터로 보낸다. is_error 를 쓰지 않는 이유이고,
    # 그래야 11번(native)의 동작과 정확히 같아진다.
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    )


server = Server(
    SERVER_NAME,
    version="0.1.0",
    title="문자열 test 도구",
    instructions="문자열 앞뒤에 표식을 붙이는 도구 하나만 제공합니다.",
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


async def serve() -> None:
    """stdin/stdout 을 JSON-RPC 파이프로 쓰는 MCP 서버."""
    print(f"[server] {SERVER_NAME} 시작 (stdio)", file=sys.stderr)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ===========================================================================
# 2) 클라이언트 쪽 — 인자 없이 실행될 때
# ===========================================================================


def server_params() -> StdioServerParameters:
    """자기 자신을 --server 모드로 띄우기 위한 파라미터."""
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")  # 자식 프로세스의 한글 깨짐 방지
    return StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve()), "--server"],
        env=env,
    )


def to_ollama_schemas(mcp_tools) -> list[dict[str, Any]]:
    """MCP Tool 목록 → Ollama function calling 스키마.

    이 번역을 거치고 나면 모델이 보는 tools 배열은 11번과 사실상 같습니다.
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
    for item in getattr(response, "content", None) or []:
        if getattr(item, "type", None) == "text":
            return item.text
    return None


SYSTEM_PROMPT = (
    "당신은 도구를 사용하는 에이전트입니다. "
    "사용자가 문자열 가공을 요청하면 반드시 test 도구를 호출하세요. "
    "추측해서 답하지 말고, 도구가 돌려준 result 값을 그대로 인용해 한국어로 간결히 답하세요."
)


async def chat(client: AsyncClient, messages: list[dict[str, Any]], schemas: list[dict[str, Any]]):
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "tools": schemas,
        "options": {"temperature": 0},
    }
    try:
        return await client.chat(think=False, **kwargs)
    except TypeError:
        return await client.chat(**kwargs)


async def run_client(query: str) -> str:
    ollama = AsyncClient(host=OLLAMA_HOST)

    # async with 를 벗어나면 자식 서버 프로세스도 함께 정리된다
    async with Client(server_params()) as mcp:
        listed = await mcp.list_tools()
        schemas = to_ollama_schemas(listed.tools)
        print(f"[mcp] list_tools -> {[t.name for t in listed.tools]}")

        async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            """MCP 왕복. 11번의 직접 호출이 여기서는 프로토콜 호출로 바뀐다."""
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

        # --- 여기서부터 아래는 11번의 에이전트 루프와 같다 ---
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
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                args = dict(args or {})

                print(f"[{step}] 도구 호출: {name}({args})  <- MCP 경유")
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


# ===========================================================================
# 진입점 — 인자로 서버/클라이언트 모드를 가른다
# ===========================================================================


async def main() -> None:
    argv = sys.argv[1:]

    if "--server" in argv:
        await serve()
        return

    query = " ".join(argv).strip() or DEFAULT_QUERY
    print("=" * 70)
    print(f"[12] MCP (stdio)   model={MODEL}   host={OLLAMA_HOST}")
    print(f"질의: {query}")
    print("=" * 70)
    print("(MCP 서버는 이 파일이 자식 프로세스로 자동 기동합니다)")

    answer = await run_client(query)

    print("-" * 70)
    print(answer or "(응답 없음)")


if __name__ == "__main__":
    asyncio.run(main())
