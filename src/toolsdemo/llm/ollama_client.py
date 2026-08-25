"""Ollama tool-calling 에이전트 루프.

Phase 1(native tools)과 Phase 2(MCP)가 **이 루프를 공유**합니다.
두 Phase의 유일한 차이는 생성자에 넘기는 `tool_schemas` / `tool_caller` 의 출처입니다.

  * Phase 1: registry 에서 바로 얻은 스키마 + registry.call_tool
  * Phase 2: MCP 서버가 list_tools 로 알려준 스키마 + session.call_tool
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ollama import AsyncClient

from ..config import settings

logger = logging.getLogger(__name__)

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

SYSTEM_PROMPT = """당신은 기차 예약을 대신 처리하는 에이전트입니다.

당신의 작업 범위는 **좌석 확보(예약)까지**입니다.
결제와 발권은 사람이 직접 하며 자동화하지 않습니다.

규칙:
1. 반드시 제공된 도구를 호출해서 실제로 예약을 진행하세요. 말로만 설명하지 마세요.
2. 예약 순서는 search_trains → select_train → fill_passenger → confirm_booking 입니다.
3. 날짜는 항상 YYYY-MM-DD 형식이어야 합니다. '내일' 같은 표현은 get_today 를 호출해 계산하세요.
4. 사용자가 시간대를 말했으면 depart_after 에 HH:MM 으로 넘기세요. (예: '오전 9시쯤' -> 09:00)
5. 사용자가 열차를 지정하지 않았다면 조건에 맞으면서
   잔여석(seats_left)이 있는 가장 이른 열차를 고르세요.
6. 예약자 이름이 주어지지 않았으면 '{passenger}' 를 사용하세요.
   fill_passenger 가 skipped:true 를 돌려주면 그냥 다음 단계로 넘어가세요.
7. 도구가 ok:false 를 돌려주면 error 메시지를 읽고 스스로 고쳐서 다시 시도하세요.
8. 결제를 시도하지 마세요. 결제 도구는 존재하지 않습니다.
9. 모든 단계가 끝나면 예약번호, 열차, 구간, 시각, 결제예정금액, 결제 기한을
   한국어로 간결히 요약하고,
   결제는 사용자가 직접 해야 한다고 안내하세요."""


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    stopped_by_limit: bool = False


class OllamaAgent:
    def __init__(
        self,
        tool_schemas: list[dict[str, Any]],
        tool_caller: ToolCaller,
        system_prompt: str | None = None,
        default_passenger: str = "홍길동",
    ) -> None:
        self.client = AsyncClient(host=settings.ollama_host)
        self.tool_schemas = tool_schemas
        self.tool_caller = tool_caller
        self.system_prompt = (system_prompt or SYSTEM_PROMPT).format(passenger=default_passenger)

    async def _chat(self, messages: list[dict[str, Any]]):
        kwargs: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": messages,
            "tools": self.tool_schemas,
            "options": {"temperature": 0},
        }
        try:
            return await self.client.chat(think=settings.think, **kwargs)
        except TypeError:
            # 구버전 ollama-python 은 think 인자를 모른다
            return await self.client.chat(**kwargs)

    async def run(self, user_message: str) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        trace: list[dict[str, Any]] = []

        logger.info("모델=%s  도구=%d개", settings.ollama_model, len(self.tool_schemas))

        for step in range(1, settings.max_tool_iterations + 1):
            response = await self._chat(messages)
            message = response.message
            tool_calls = getattr(message, "tool_calls", None) or []

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            if not tool_calls:
                logger.info("도구 호출 없음 → 종료 (step %d)", step)
                return AgentResult(
                    answer=(message.content or "").strip(), tool_calls=trace, iterations=step
                )

            for tc in tool_calls:
                name = tc.function.name
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = await self.tool_caller(name, dict(args or {}))
                trace.append({"step": step, "tool": name, "arguments": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "name": name,
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        logger.warning("MAX_TOOL_ITERATIONS(%d) 도달 — 루프 중단", settings.max_tool_iterations)
        return AgentResult(
            answer="도구 호출 횟수 상한에 도달해 중단했습니다.",
            tool_calls=trace,
            iterations=settings.max_tool_iterations,
            stopped_by_limit=True,
        )
