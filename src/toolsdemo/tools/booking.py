"""예약 도메인 도구.

여기에 등록된 도구는 Phase 1(native tools)과 Phase 2(MCP) **양쪽에 자동 노출**됩니다.
CSS 셀렉터는 절대 이 파일에 두지 마세요 — `sites/` 어댑터의 몫입니다.

docstring 이 곧 LLM 이 읽는 사용 설명서입니다. 인자 형식을 반드시 명시하세요.
"""

from __future__ import annotations

import logging
import re
from datetime import date as date_cls
from datetime import timedelta
from typing import Any

from ..config import settings
from .browser import get_page
from .registry import tool
from .sites.base import get_adapter

logger = logging.getLogger(__name__)

_adapter = get_adapter(settings.target_site, settings.mock_site_url, settings.korail_url)

#: 마지막 조회 컨텍스트. 다단계 흐름에서 LLM 이 인자를 다시 안 줘도 되게 한다.
_state: dict[str, Any] = {"last_query": None, "options": [], "selected": None}


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _normalize_date(value: str) -> str | None:
    value = (value or "").strip()
    if _DATE_RE.match(value):
        return value
    today = date_cls.today()
    relative = {"오늘": 0, "내일": 1, "모레": 2}
    if value in relative:
        return (today + timedelta(days=relative[value])).isoformat()
    return None


@tool
async def get_today() -> dict[str, Any]:
    """오늘 날짜와 요일을 알려준다. '내일', '이번 주말' 같은 표현을 날짜로 바꿀 때 먼저 호출한다.

    Returns:
        today: 오늘 날짜 (YYYY-MM-DD), weekday: 요일, tomorrow: 내일 날짜
    """
    today = date_cls.today()
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return {
        "ok": True,
        "today": today.isoformat(),
        "weekday": weekdays[today.weekday()],
        "tomorrow": (today + timedelta(days=1)).isoformat(),
    }


@tool
async def search_trains(
    departure: str,
    arrival: str,
    date: str,
    depart_after: str = "",
) -> dict[str, Any]:
    """출발역/도착역/날짜로 기차를 조회한다. 예약의 첫 단계이며 반드시 가장 먼저 호출한다.

    Args:
        departure: 출발역 이름. 예: 서울
        arrival: 도착역 이름. 예: 부산
        date: 출발 날짜. 반드시 YYYY-MM-DD 형식. 모르면 get_today 를 먼저 호출한다.
        depart_after: 이 시각 이후 열차만 조회. HH:MM 형식(24시간제). 예: 09:00. 비우면 전체.
    """
    day = _normalize_date(date)
    if day is None:
        return {
            "ok": False,
            "error": f"날짜 형식이 잘못되었습니다: {date!r}. YYYY-MM-DD 로 주세요.",
            "hint": "get_today 를 호출해 오늘 날짜를 확인한 뒤 계산하세요.",
        }
    if depart_after and not _TIME_RE.match(depart_after.strip()):
        return {
            "ok": False,
            "error": f"시각 형식이 잘못되었습니다: {depart_after!r}. HH:MM 로 주세요.",
        }

    page = await get_page()
    options = await _adapter.search(page, departure, arrival, day, depart_after.strip())

    _state["last_query"] = {
        "departure": departure,
        "arrival": arrival,
        "date": day,
        "depart_after": depart_after,
    }
    _state["options"] = options
    _state["selected"] = None

    if not options:
        return {
            "ok": True,
            "count": 0,
            "options": [],
            "message": "조회 결과가 없습니다. 역 이름이나 날짜를 확인하세요.",
        }

    available = [o for o in options if o.get("seats_left", 1) > 0]
    return {
        "ok": True,
        "count": len(options),
        "available_count": len(available),
        "options": options[:12],
        "message": (
            "예약하려면 select_train 에 train_no 를 넘기세요. seats_left 가 0 인 열차는 매진입니다."
        ),
    }


@tool
async def select_train(train_no: str) -> dict[str, Any]:
    """조회 결과에서 열차 한 편을 골라 예약 화면으로 이동한다. search_trains 이후에만 호출한다.

    Args:
        train_no: search_trains 결과의 train_no 값. 예: 1100
    """
    if not _state["options"]:
        return {"ok": False, "error": "조회 결과가 없습니다. search_trains 를 먼저 호출하세요."}

    page = await get_page()
    result = await _adapter.open_reserve(page, str(train_no).strip())
    if result.get("ok"):
        _state["selected"] = str(train_no).strip()
        result["message"] = "다음으로 fill_passenger 에 예약자 이름을 넘기세요."
    return result


@tool
async def fill_passenger(name: str, phone: str = "", passengers: int = 1) -> dict[str, Any]:
    """예약자 정보를 입력한다. 아직 확정되지 않으며 confirm_booking 을 호출해야 예약이 끝난다.

    사이트에 따라 이 단계가 없을 수 있으며, 그때는 skipped:true 로 응답합니다.

    Args:
        name: 예약자 이름
        phone: 연락처. 예: 010-1234-5678. 모르면 비워 둔다.
        passengers: 탑승 인원 수. 기본 1명.
    """
    if not _state["selected"]:
        return {"ok": False, "error": "선택된 열차가 없습니다. select_train 을 먼저 호출하세요."}
    if not name.strip():
        return {"ok": False, "error": "예약자 이름이 필요합니다. 사용자에게 이름을 물어보세요."}
    try:
        count = max(1, int(passengers))
    except (TypeError, ValueError):
        count = 1

    page = await get_page()
    result = await _adapter.fill_passenger(page, name.strip(), phone.strip(), count)
    if result.get("ok"):
        result["message"] = "정보 입력 완료. confirm_booking 을 호출해 예약을 확정하세요."
    return result


@tool
async def confirm_booking() -> dict[str, Any]:
    """예약을 확정해 좌석을 확보하고 예약번호를 받는다. 마지막 단계이며 한 번만 호출한다.

    이 도구는 **좌석 확보(예약)까지만** 수행합니다. 결제와 발권은 자동화 대상이 아니며
    사람이 직접 진행합니다. 결제를 수행하는 도구는 존재하지 않으니 찾지 마세요.
    """
    if not _state["selected"]:
        return {"ok": False, "error": "선택된 열차가 없습니다. select_train 을 먼저 호출하세요."}
    if not _adapter.allows_confirm:
        return {
            "ok": False,
            "error": f"{_adapter.name} 사이트에서는 예약 확정 자동화가 금지되어 있습니다.",
        }

    page = await get_page()
    return await _adapter.confirm(page)


@tool
async def describe_page() -> dict[str, Any]:
    """현재 브라우저 화면의 URL/제목/본문 요약을 돌려준다. 흐름이 꼬였을 때 상황 파악용."""
    page = await get_page()
    try:
        body = await page.inner_text("main")
    except Exception:  # noqa: BLE001
        body = await page.inner_text("body")
    return {
        "ok": True,
        "url": page.url,
        "title": await page.title(),
        "text": re.sub(r"\n{2,}", "\n", body)[:1500],
    }


@tool
async def take_screenshot(label: str = "step") -> dict[str, Any]:
    """현재 화면을 PNG 로 저장한다. 데모 기록용이며 예약 흐름에는 영향을 주지 않는다.

    Args:
        label: 파일 이름에 붙일 짧은 영문/숫자 라벨. 예: search_result
    """
    page = await get_page()
    safe = re.sub(r"[^0-9A-Za-z가-힣_-]", "_", label)[:40] or "step"
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    path = settings.screenshot_dir / f"{safe}.png"
    await page.screenshot(path=str(path), full_page=True)
    return {"ok": True, "path": str(path)}


def reset_state() -> None:
    """테스트용 — 조회/선택 컨텍스트 초기화."""
    _state.update({"last_query": None, "options": [], "selected": None})
