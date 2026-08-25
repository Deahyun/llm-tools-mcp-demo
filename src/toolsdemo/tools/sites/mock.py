"""로컬 mock 사이트 어댑터. 기본 타깃이며 예약(좌석 확보)까지 전 흐름을 지원한다."""

from __future__ import annotations

import logging
import re
from typing import Any

from playwright.async_api import Page

from .base import SiteAdapter

logger = logging.getLogger(__name__)

_ROW_EXTRACTOR = """
rows => rows.map(tr => ({
  train_type: tr.querySelector('.train-type')?.innerText.trim() ?? '',
  train_no: tr.dataset.trainNo ?? '',
  depart_time: tr.querySelector('.depart-time')?.innerText.trim() ?? '',
  arrive_time: tr.querySelector('.arrive-time')?.innerText.trim() ?? '',
  duration: tr.querySelector('.duration')?.innerText.trim() ?? '',
  price: tr.querySelector('.price')?.innerText.trim() ?? '',
  seats: tr.querySelector('.seats')?.innerText.trim() ?? '',
}))
"""


def _to_int(text: str) -> int:
    digits = re.sub(r"[^0-9]", "", text or "")
    return int(digits) if digits else 0


class MockSiteAdapter(SiteAdapter):
    name = "mock"
    allows_confirm = True

    async def open_search(self, page: Page) -> None:
        if not page.url.startswith(self.base_url):
            await page.goto(self.base_url + "/", wait_until="domcontentloaded")
        elif "/search" in page.url or "/reserve" in page.url or "/confirm" in page.url:
            await page.goto(self.base_url + "/", wait_until="domcontentloaded")
        await page.wait_for_selector("#search-form")

    async def search(
        self, page: Page, departure: str, arrival: str, date: str, depart_after: str
    ) -> list[dict[str, Any]]:
        await self.open_search(page)

        await page.get_by_label("출발역").fill(departure)
        await page.get_by_label("도착역").fill(arrival)
        await page.get_by_label("출발일").fill(date)
        if depart_after:
            await page.get_by_label("출발시각 이후").fill(depart_after)

        await page.get_by_role("button", name="조회하기").click()
        await page.wait_for_load_state("domcontentloaded")

        if await page.locator("#no-result").count():
            return []

        await page.wait_for_selector("#results tbody tr")
        raw = await page.eval_on_selector_all("#results tbody tr", _ROW_EXTRACTOR)

        options: list[dict[str, Any]] = []
        for r in raw:
            options.append(
                {
                    "train_type": r["train_type"],
                    "train_no": r["train_no"],
                    "departure": departure,
                    "arrival": arrival,
                    "depart_time": r["depart_time"],
                    "arrive_time": r["arrive_time"],
                    "duration_min": _to_int(r["duration"]),
                    "price": _to_int(r["price"]),
                    "seats_left": _to_int(r["seats"]),
                }
            )
        return options

    async def open_reserve(self, page: Page, train_no: str) -> dict[str, Any]:
        row = page.locator(f'#results tbody tr[data-train-no="{train_no}"]')
        if not await row.count():
            return {
                "ok": False,
                "error": (
                    f"현재 조회 결과에 열차번호 {train_no} 가 없습니다. "
                    "search_trains 를 먼저 실행하세요."
                ),
            }

        button = row.get_by_role("button", name="예매")
        if await button.is_disabled():
            return {"ok": False, "error": f"열차 {train_no} 는 매진입니다. 다른 열차를 선택하세요."}

        await button.click()
        await page.wait_for_load_state("domcontentloaded")

        if await page.locator("#reserve-error").count():
            return {"ok": False, "error": await page.locator("#reserve-error").inner_text()}

        await page.wait_for_selector("#reserve-form")
        return {
            "ok": True,
            "train": await page.locator("#s-train").inner_text(),
            "route": await page.locator("#s-route").inner_text(),
            "when": await page.locator("#s-when").inner_text(),
            "price": await page.locator("#s-price").inner_text(),
            "seats_left": _to_int(await page.locator("#s-seats").inner_text()),
        }

    async def fill_passenger(
        self, page: Page, name: str, phone: str, passengers: int
    ) -> dict[str, Any]:
        if not await page.locator("#reserve-form").count():
            return {"ok": False, "error": "예약 화면이 아닙니다. select_train 을 먼저 실행하세요."}

        await page.get_by_label("예매자 이름").fill(name)
        if phone:
            await page.get_by_label("연락처").fill(phone)
        await page.get_by_label("인원").fill(str(passengers))
        return {"ok": True, "name": name, "phone": phone, "passengers": passengers}

    async def confirm(self, page: Page) -> dict[str, Any]:
        if not await page.locator("#reserve-form").count():
            return {"ok": False, "error": "예약 화면이 아닙니다. select_train 을 먼저 실행하세요."}

        await page.get_by_role("button", name="예약하기").click()
        await page.wait_for_load_state("domcontentloaded")

        if await page.locator("#confirm-error").count():
            return {"ok": False, "error": await page.locator("#confirm-error").inner_text()}

        await page.wait_for_selector("#reservation-no")
        return {
            "ok": True,
            "stage": "예약 완료 (결제 대기)",
            "reservation_no": await page.locator("#reservation-no").inner_text(),
            "train": await page.locator("#r-train").inner_text(),
            "route": await page.locator("#r-route").inner_text(),
            "when": await page.locator("#r-when").inner_text(),
            "passenger": await page.locator("#r-name").inner_text(),
            "passengers": _to_int(await page.locator("#r-passengers").inner_text()),
            "total_price": _to_int(await page.locator("#r-total").inner_text()),
            "payment_deadline": await page.locator("#payment-deadline").inner_text(),
            "message": (
                "좌석이 확보되었습니다. 결제와 발권은 자동화하지 않으므로 "
                "기한 내에 사람이 직접 결제해야 합니다."
            ),
        }
