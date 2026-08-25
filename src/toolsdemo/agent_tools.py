"""Phase 1 진입점 — Ollama **native tool calling**.

도구 스키마를 registry 에서 직접 얻고, 도구도 같은 프로세스에서 직접 실행합니다.
Phase 2(MCP)와 비교해 보세요: 에이전트 루프는 동일하고 도구 조달 경로만 다릅니다.

    python -m toolsdemo.agent_tools "내일 오전 9시쯤 서울에서 부산 가는 KTX 예매해줘"
"""

from __future__ import annotations

import asyncio
import sys

from .config import settings, setup_logging
from .llm.ollama_client import OllamaAgent
from .tools import booking  # noqa: F401 - import 시점에 도구가 registry 에 등록된다
from .tools.browser import close_browser
from .tools.registry import call_tool, ollama_tool_schemas

DEFAULT_QUERY = "내일 오전 9시쯤 서울에서 부산 가는 기차 예약해줘"


async def run(query: str) -> int:
    agent = OllamaAgent(tool_schemas=ollama_tool_schemas(), tool_caller=call_tool)

    print(
        f"\n[Phase 1 · native tools]  model={settings.ollama_model}  target={settings.target_site}"
    )
    print(f"질의: {query}\n" + "-" * 70)

    try:
        result = await agent.run(query)
    finally:
        await close_browser()

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
