"""예제 11 — Native tool calling. LLM 이 직접 파이썬 함수를 호출한다.

실행 (이 파일 하나로 끝. 준비할 것 없음):

    python demo/11_tool_call.py
    python demo/11_tool_call.py "hello 로 test 해줘"

흐름:

    사용자 질의
        │
        ▼
    ollama.chat(model=..., tools=[TOOL_SCHEMA])   ← 도구 목록을 같이 넘긴다
        │
        ├─ tool_calls 있음 → test() 실행 → 결과를 messages 에 append → 다시 chat
        └─ tool_calls 없음 → 최종 자연어 답변. 종료

12/13 번 예제와 **도구도 에이전트 루프도 똑같습니다.** 달라지는 것은 도구를 어디서
조달하느냐(직접 함수 / MCP stdio / MCP HTTP)뿐입니다. 비교하기 쉽도록 세 파일 모두
의존성 없이 각자 완결되게 썼습니다. 중복은 의도된 것입니다.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from ollama import AsyncClient

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

MODEL = os.getenv("OLLAMA_MODEL", "qwen3.8-local:27b")
MAX_ITERATIONS = 5
DEFAULT_QUERY = "안녕하세요 라는 문자열로 test 도구를 실행하고 결과를 알려줘."


def normalize_host(raw: str) -> str:
    """Ollama 접속 주소 정규화.

    이 PC 의 시스템 환경변수는 `OLLAMA_HOST=0.0.0.0:11434` 입니다. 이건 서버가
    *바인딩* 하는 주소인데, 클라이언트가 *접속* 주소로 그대로 쓰면 ConnectionError 가
    납니다. 와일드카드를 루프백으로 바꿔 줍니다.
    """
    host = (raw or "").strip() or "http://127.0.0.1:11434"
    if "://" not in host:
        host = "http://" + host
    return host.replace("//0.0.0.0:", "//127.0.0.1:").replace("//[::]:", "//127.0.0.1:")


OLLAMA_HOST = normalize_host(os.getenv("OLLAMA_HOST", ""))


# ---------------------------------------------------------------------------
# 도구 — 세 예제가 공유하는 기본 구현
# ---------------------------------------------------------------------------


def test(a: str) -> str:
    res = "123---" + a + "---456"
    print(f"{res}")
    return res


#: 모델에게 보여 줄 도구 명세. description 과 인자 설명이 곧 LLM 이 읽는 사용 설명서다.
TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "test",
        "description": (
            "문자열 하나를 받아 앞에 '123---', 뒤에 '---456' 을 붙여 돌려준다. "
            "사용자가 어떤 값을 test 해 달라고 하면 반드시 이 도구를 호출한다. "
            "직접 문자열을 만들어 답하지 말고 도구의 반환값을 그대로 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "a": {
                    "type": "string",
                    "description": "가공할 문자열. 예: 안녕하세요",
                }
            },
            "required": ["a"],
        },
    },
}


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """도구 이름으로 실제 함수를 부른다.

    예외를 던지지 않고 {"ok": false, "error": ...} 로 돌려주는 것이 핵심입니다.
    LLM 이 그 메시지를 읽고 스스로 고쳐 다시 시도할 수 있어야 합니다.
    """
    if name != "test":
        return {"ok": False, "error": f"알 수 없는 도구입니다: {name}"}
    a = arguments.get("a")
    if not isinstance(a, str) or not a:
        return {"ok": False, "error": "인자 a 는 비어 있지 않은 문자열이어야 합니다."}

    # test() 는 동기 함수다. 지금은 즉시 끝나므로 그냥 호출한다.
    # 만약 오래 걸리는 블로킹 함수라면 await asyncio.to_thread(test, a) 로 감싼다.
    return {"ok": True, "result": test(a)}


SYSTEM_PROMPT = (
    "당신은 도구를 사용하는 에이전트입니다. "
    "사용자가 문자열 가공을 요청하면 반드시 test 도구를 호출하세요. "
    "추측해서 답하지 말고, 도구가 돌려준 result 값을 그대로 인용해 한국어로 간결히 답하세요."
)


# ---------------------------------------------------------------------------
# 에이전트 루프
# ---------------------------------------------------------------------------


async def chat(client: AsyncClient, messages: list[dict[str, Any]]):
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "tools": [TOOL_SCHEMA],
        "options": {"temperature": 0},  # 인자 파싱에 창의성은 필요 없다
    }
    try:
        return await client.chat(think=False, **kwargs)  # thinking 끄면 응답이 빠르다
    except TypeError:
        return await client.chat(**kwargs)  # 구버전 ollama-python 은 think 를 모른다


async def run_agent(query: str) -> str:
    client = AsyncClient(host=OLLAMA_HOST)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    for step in range(1, MAX_ITERATIONS + 1):
        response = await chat(client, messages)
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
            print(f"[{step}] 도구 호출 없음 → 종료")
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

            print(f"[{step}] 도구 호출: {name}({args})")
            result = await call_tool(name, args)
            print(f"[{step}] 도구 결과: {result}")

            # 결과는 반드시 문자열로 직렬화해서 messages 에 되돌려 준다
            messages.append(
                {
                    "role": "tool",
                    "name": name,
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return "도구 호출 횟수 상한에 도달해 중단했습니다."


async def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or DEFAULT_QUERY

    print("=" * 70)
    print(f"[11] Native tool calling   model={MODEL}   host={OLLAMA_HOST}")
    print(f"질의: {query}")
    print("=" * 70)
    print("(27B 모델 첫 로딩은 1분 이상 걸릴 수 있습니다)")

    answer = await run_agent(query)

    print("-" * 70)
    print(answer or "(응답 없음)")


if __name__ == "__main__":
    asyncio.run(main())
