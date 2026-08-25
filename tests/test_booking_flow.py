"""LLM 없이 도구만으로 예약 흐름 전체를 검증한다 (mock 사이트 + Playwright).

에이전트가 실패할 때 원인이 '도구'인지 '모델'인지 가르는 기준선입니다.
모델 없이 이 테스트가 통과하면 도구 계층은 정상입니다.

    pytest -q -m browser
"""

from __future__ import annotations

import pytest

from toolsdemo.config import settings
from toolsdemo.tools import booking
from toolsdemo.tools.browser import close_browser
from toolsdemo.tools.registry import call_tool

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        settings.target_site != "mock",
        reason="TARGET_SITE=mock 일 때만 실행합니다 (실사이트 좌석을 점유하지 않기 위해).",
    ),
]


@pytest.fixture(autouse=True)
async def _clean(mock_server):
    booking.reset_state()
    yield
    await close_browser()


async def test_full_reservation_flow():
    today = await call_tool("get_today", {})
    assert today["ok"] is True

    found = await call_tool(
        "search_trains",
        {
            "departure": "서울",
            "arrival": "부산",
            "date": today["tomorrow"],
            "depart_after": "09:00",
        },
    )
    assert found["ok"] is True and found["count"] > 0
    assert all(o["depart_time"] >= "09:00" for o in found["options"])

    available = [o for o in found["options"] if o["seats_left"] > 0]
    assert available, "잔여석 있는 열차가 없습니다"
    train_no = available[0]["train_no"]

    selected = await call_tool("select_train", {"train_no": train_no})
    assert selected["ok"] is True
    assert train_no in selected["train"]

    filled = await call_tool("fill_passenger", {"name": "홍길동", "phone": "010-1234-5678"})
    assert filled["ok"] is True

    confirmed = await call_tool("confirm_booking", {})
    assert confirmed["ok"] is True
    assert confirmed["reservation_no"].startswith("R")
    assert confirmed["passenger"] == "홍길동"
    assert confirmed["total_price"] > 0
    # 자동화 경계: 예약까지만. 결제 기한을 사람에게 넘긴다.
    assert confirmed["stage"] == "예약 완료 (결제 대기)"
    assert confirmed["payment_deadline"]


async def test_sold_out_train_is_rejected():
    today = await call_tool("get_today", {})
    found = await call_tool(
        "search_trains",
        {"departure": "서울", "arrival": "부산", "date": today["tomorrow"]},
    )
    sold_out = [o for o in found["options"] if o["seats_left"] == 0]
    if not sold_out:
        pytest.skip("이 날짜에는 매진 열차가 없습니다")

    result = await call_tool("select_train", {"train_no": sold_out[0]["train_no"]})
    assert result["ok"] is False
    assert "매진" in result["error"]


async def test_out_of_order_calls_return_actionable_errors():
    # 조회 없이 선택
    assert (await call_tool("select_train", {"train_no": "1100"}))["ok"] is False
    # 선택 없이 확정
    result = await call_tool("confirm_booking", {})
    assert result["ok"] is False and "select_train" in result["error"]


async def test_bad_date_format_is_rejected_with_hint():
    result = await call_tool(
        "search_trains", {"departure": "서울", "arrival": "부산", "date": "내일모레"}
    )
    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["error"]
    assert "get_today" in result["hint"]
