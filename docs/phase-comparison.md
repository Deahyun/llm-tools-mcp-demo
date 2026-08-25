# Phase 1 (Native Tools) vs Phase 2 (MCP)

이 저장소의 존재 이유는 "**같은 도구를 native tool calling으로 쓸 때와 MCP로 쓸 때 무엇이
바뀌고 무엇이 그대로인가**"를 코드로 보여주는 것입니다.

## 결론부터

| | Phase 1 | Phase 2 |
|---|---|---|
| 도구 구현 (`tools/booking.py`) | 동일 | 동일 |
| 에이전트 루프 (`llm/ollama_client.py`) | 동일 | 동일 |
| 모델에게 넘기는 `tools` 배열 | 동일 | 동일 |
| 도구 스키마를 **어디서 얻는가** | registry (같은 프로세스) | MCP `list_tools()` (별도 프로세스) |
| 도구를 **어떻게 실행하는가** | `await spec.fn(**args)` | MCP `call_tool()` → stdio JSON-RPC |
| 프로세스 | 1개 | 2개 (클라이언트 + 서버) |
| 실행 결과 | 동일 | 동일 |

`tests/test_parity.py::test_ollama_schemas_are_identical_across_phases` 가 세 번째 행을
기계적으로 강제합니다. 새 도구를 추가하고 MCP 노출을 빼먹으면 이 테스트가 깨집니다.

## 코드로 보는 차이

전체 차이는 **두 곳**뿐입니다.

### 1) 도구 스키마 조달

```python
# Phase 1 — agent_tools.py
from .tools.registry import ollama_tool_schemas

schemas = ollama_tool_schemas()
```

```python
# Phase 2 — mcp_/client_agent.py
async with Client(server_params()) as client:
    listed = await client.list_tools()
    schemas = to_ollama_schemas(listed.tools)  # MCP Tool → Ollama function schema
```

### 2) 도구 실행

```python
# Phase 1
agent = OllamaAgent(tool_schemas=schemas, tool_caller=call_tool)  # 함수 직접 호출
```

```python
# Phase 2
async def caller(name, arguments):
    response = await client.call_tool(name, arguments)
    return json.loads(first_text(response))


agent = OllamaAgent(tool_schemas=schemas, tool_caller=caller)
```

`OllamaAgent` 는 `tool_caller` 가 무엇인지 모릅니다. 그래서 루프를 한 줄도 고치지 않고
두 방식을 갈아끼울 수 있습니다.

## 설계상 지켜야 하는 것들

### 도구 실패는 예외가 아니라 데이터

`registry.call_tool()` 은 어떤 경우에도 예외를 던지지 않고
`{"ok": false, "error": "..."}` 를 반환합니다. LLM이 error를 읽고 스스로 복구해야 하기 때문입니다.

MCP 쪽에서도 같은 원칙을 지키려고 **`CallToolResult.is_error` 를 쓰지 않습니다.**
`is_error=True` 로 보내면 클라이언트/SDK 계층에서 프로토콜 오류로 취급될 여지가 생겨
Phase 1과 동작이 달라집니다. 실패는 `ok:false` 페이로드로만 전달합니다.
(`tests/test_parity.py::test_tool_failure_travels_as_data_not_protocol_error`)

### stdout 은 JSON-RPC 전용

MCP 서버는 stdout으로 프로토콜을 주고받습니다. 서버 경로에서 `print()` 를 쓰면
프로토콜이 깨집니다. 로그는 `logging`(stderr)으로만 남깁니다.

### 브라우저 세션의 위치

Phase 2에서 Playwright 브라우저는 **MCP 서버 프로세스 안**에서 뜹니다.
`search_trains` 로 연 조회 결과 페이지 위에서 `select_train` 이 동작해야 하므로,
서버가 살아있는 동안 세션이 유지되어야 합니다 (`browser.py` 의 프로세스당 싱글턴).
서버가 죽으면 브라우저도 함께 정리됩니다 (`serve()` 의 `finally`).

## MCP로 옮겨서 얻는 것

이 데모 규모에서는 Phase 1이 더 단순합니다. MCP의 값어치는 다음에서 나옵니다.

- **재사용** — 같은 서버를 Claude Code, Claude Desktop 등 MCP를 지원하는 어떤 호스트에도
  그대로 붙일 수 있습니다. Phase 1의 도구는 이 파이썬 프로세스 안에서만 쓸 수 있습니다.
- **프로세스 격리** — 브라우저 자동화가 죽어도 에이전트 프로세스는 살아있습니다.
- **언어 독립** — 도구 서버를 다른 언어로 바꿔도 클라이언트는 그대로입니다.
- **명세된 계약** — 도구 목록/스키마/호출이 프로토콜로 규정되어 있어, 호스트가 도구를
  발견하고 검증하는 방식이 표준화됩니다.

반대로 치르는 비용은 프로세스 1개 추가, stdio 직렬화 오버헤드, 그리고 디버깅 시
로그가 두 프로세스로 나뉜다는 점입니다.

## MCP SDK 버전 주의

이 저장소는 **MCP Python SDK 2.x** 기준입니다. 1.x와 API가 다릅니다.

| | 1.x | 2.x (이 저장소) |
|---|---|---|
| 서버 핸들러 | `@server.list_tools()` 데코레이터 | `Server(on_list_tools=..., on_call_tool=...)` |
| Tool 스키마 필드 | `inputSchema=` | `input_schema=` |
| 반환 타입 | `list[Tool]` / `list[TextContent]` | `ListToolsResult` / `CallToolResult` |
| 클라이언트 | `stdio_client()` + `ClientSession` | `Client(StdioServerParameters(...))` |

1.x 예제 코드를 그대로 붙여넣으면 동작하지 않습니다.
