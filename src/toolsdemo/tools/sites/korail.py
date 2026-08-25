"""실제 코레일 어댑터 — **opt-in. 예약(좌석 확보)까지 자동화, 결제는 사람이 진행.**

정책 (CLAUDE.md 의 "대상 사이트 정책" 참조):
  * 자동화 범위: 조회 → 열차 선택 → 예약 요청 → **예약 완료(결제 대기)** 까지.
  * **결제/발권은 자동화하지 않습니다.** 결제 도구 자체를 만들지 않으며,
    예약 완료 후 결제 기한과 함께 사람에게 넘깁니다.
  * 로그인 정보는 저장소에 두지 않습니다. `.env` 의 `KORAIL_ID` / `KORAIL_PW` 에서만 읽습니다.
  * 반복 폴링/재시도 루프를 만들지 않습니다.

주의: 아래 셀렉터는 상용 사이트 구조에 의존하므로 언제든 깨집니다. mock 어댑터와 달리
이 어댑터의 동작은 보장되지 않습니다. 실패하면 `describe_page` 로 현재 DOM 을 확인하고
`_CANDIDATES` 목록을 갱신하세요. 데모 전 반드시 실사이트에서 한 번 검증하십시오.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from playwright.async_api import Locator, Page

from .base import SiteAdapter

logger = logging.getLogger(__name__)

# 위에서부터 순서대로 시도하는 셀렉터 후보. 사이트 개편 시 여기만 고치면 됩니다.
_CANDIDATES: dict[str, list[str]] = {
    "departure": ["#start", "input[name='txtGoStart']", "#txtGoStart"],
    "arrival": ["#get", "input[name='txtGoEnd']", "#txtGoEnd"],
    "date": ["#s_year", "select[name='selGoStartDay']", "#selGoStartDay"],
    "time": ["#time", "select[name='selGoHour']", "#selGoHour"],
    "search_button": [
        "a:has-text('조회하기')",
        "input[alt='조회하기']",
        "button:has-text('조회')",
    ],
    "result_table": ["#tableResult", "table.tbl_line", "table"],
    "login_id": ["#txtMember", "input[name='txtMember']", "#srchDvNm01"],
    "login_pw": ["#txtPwd", "input[name='txtPwd']", "#hmpgPwdCphd01"],
    "login_button": ["a:has-text('로그인')", "input[alt='로그인']", "button:has-text('로그인')"],
    "reserve_done": [
        "text=예약이 완료",
        "text=결제하기",
        ".txt_point:has-text('예약')",
    ],
    "payment_deadline": ["text=/결제.*기한/", "text=/\\d+분 이내/"],
}


class KorailAdapter(SiteAdapter):
    name = "korail"
    #: 예약(좌석 확보)까지는 허용. 결제는 별도이며 도구 자체가 없다.
    allows_confirm = True
    #: 결제 단계는 어떤 경우에도 자동화하지 않는다.
    allows_payment = False

    async def _first(self, page: Page, key: str) -> Locator | None:
        for sel in _CANDIDATES[key]:
            loc = page.locator(sel).first
            try:
                if await loc.count():
                    return loc
            except Exception:  # noqa: BLE001 - 잘못된 셀렉터 후보는 건너뛴다
                continue
        return None

    async def open_search(self, page: Page) -> None:
        await page.goto(self.base_url + "/", wait_until="domcontentloaded")

    async def _ensure_login(self, page: Page) -> dict[str, Any]:
        """예약에는 로그인이 필요하다. 자격증명은 .env 에서만 읽는다."""
        korail_id = os.getenv("KORAIL_ID", "").strip()
        korail_pw = os.getenv("KORAIL_PW", "").strip()
        if not korail_id or not korail_pw:
            return {
                "ok": False,
                "error": (
                    "코레일 예약에는 로그인이 필요합니다. "
                    ".env 에 KORAIL_ID / KORAIL_PW 를 설정하거나, "
                    "HEADLESS=false 로 실행해 브라우저에서 직접 로그인한 뒤 다시 시도하세요."
                ),
            }

        id_field = await self._first(page, "login_id")
        pw_field = await self._first(page, "login_pw")
        if id_field is None or pw_field is None:
            return {
                "ok": False,
                "error": "로그인 폼을 찾지 못했습니다. describe_page 로 확인하세요.",
            }

        await id_field.fill(korail_id)
        await pw_field.fill(korail_pw)
        button = await self._first(page, "login_button")
        if button is not None:
            await button.click()
        else:
            await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded")
        logger.info("코레일 로그인 시도 완료")
        return {"ok": True}

    async def search(
        self, page: Page, departure: str, arrival: str, date: str, depart_after: str
    ) -> list[dict[str, Any]]:
        await self.open_search(page)

        dep = await self._first(page, "departure")
        arr = await self._first(page, "arrival")
        if dep is None or arr is None:
            raise RuntimeError(
                "코레일 조회 폼을 찾지 못했습니다. describe_page 로 현재 DOM 을 확인하고 "
                "korail.py 의 _CANDIDATES 를 갱신하세요."
            )

        await dep.fill(departure)
        await arr.fill(arrival)

        day = await self._first(page, "date")
        if day is not None:
            try:
                await day.fill(date)
            except Exception:  # noqa: BLE001 - select 요소면 fill 이 실패한다
                try:
                    await day.select_option(date)
                except Exception:  # noqa: BLE001
                    logger.warning("날짜 입력 실패 — 사이트 기본값으로 진행합니다.")

        if depart_after:
            hour = await self._first(page, "time")
            if hour is not None:
                try:
                    await hour.select_option(depart_after.split(":")[0])
                except Exception:  # noqa: BLE001
                    logger.warning("출발시각 선택 실패 — 전체 시간대로 조회합니다.")

        button = await self._first(page, "search_button")
        if button is not None:
            await button.click()
        else:
            await page.keyboard.press("Enter")
        await page.wait_for_load_state("domcontentloaded")

        table = await self._first(page, "result_table")
        if table is None:
            return []

        rows = await table.locator("tbody tr").all()
        options: list[dict[str, Any]] = []
        for idx, row in enumerate(rows[:30]):
            text = re.sub(r"\s+", " ", (await row.inner_text()).strip())
            if not text:
                continue
            options.append(
                {
                    # 실사이트는 열차번호 위치가 자주 바뀌므로 행 인덱스를 안정적인 키로 함께 준다
                    "train_no": _extract_train_no(text) or f"row{idx}",
                    "row_index": idx,
                    "raw": text,
                }
            )
        return options

    async def open_reserve(self, page: Page, train_no: str) -> dict[str, Any]:
        """열차 행의 '예약하기' 를 눌러 예약 화면으로 진입한다."""
        table = await self._first(page, "result_table")
        if table is None:
            return {
                "ok": False,
                "error": "조회 결과 표가 없습니다. search_trains 를 먼저 실행하세요.",
            }

        row = table.locator("tbody tr").filter(has_text=str(train_no)).first
        if not await row.count():
            if str(train_no).startswith("row"):
                idx = int(str(train_no)[3:])
                row = table.locator("tbody tr").nth(idx)
            else:
                return {"ok": False, "error": f"결과에서 {train_no} 를 찾지 못했습니다."}

        link = row.locator("a", has_text=re.compile("예약")).first
        if not await link.count():
            return {
                "ok": False,
                "error": (
                    "해당 행에 '예약하기' 링크가 없습니다. 매진이거나 구조가 바뀌었을 수 있습니다."
                ),
            }

        await link.click()
        await page.wait_for_load_state("domcontentloaded")

        # 예약 진입 시 로그인 페이지로 튕기는 경우가 많다
        if await page.locator(_CANDIDATES["login_id"][0]).count():
            login = await self._ensure_login(page)
            if not login.get("ok"):
                return login
            await page.wait_for_load_state("domcontentloaded")

        return {"ok": True, "url": page.url, "title": await page.title()}

    async def fill_passenger(
        self, page: Page, name: str, phone: str, passengers: int
    ) -> dict[str, Any]:
        """코레일은 로그인 계정 정보로 예약자가 결정되므로 별도 입력이 없다."""
        return {
            "ok": True,
            "skipped": True,
            "message": (
                "코레일은 로그인 계정이 예약자가 되므로 이름/연락처 입력 단계가 없습니다. "
                "바로 confirm_booking 을 호출해 예약을 확정하세요."
            ),
        }

    async def confirm(self, page: Page) -> dict[str, Any]:
        """예약(좌석 확보)까지만 확정한다. 결제 버튼은 절대 누르지 않는다."""
        button = (
            page.locator("a, input, button").filter(has_text=re.compile("예약하기|다음|확인")).first
        )
        if await button.count():
            await button.click()
            await page.wait_for_load_state("domcontentloaded")

        done = await self._first(page, "reserve_done")
        if done is None:
            return {
                "ok": False,
                "error": (
                    "예약 완료 화면을 확인하지 못했습니다. describe_page 로 현재 상태를 확인하세요."
                ),
                "url": page.url,
            }

        body = re.sub(r"\s+", " ", await page.inner_text("body"))
        deadline = re.search(r"(\d+\s*분\s*이내|결제[^.]{0,30}기한[^.]{0,30})", body)
        return {
            "ok": True,
            "stage": "예약 완료 (결제 대기)",
            "url": page.url,
            "reservation_no": _extract_reservation_no(body),
            "payment_deadline": deadline.group(1) if deadline else "사이트 안내 참조",
            "message": (
                "좌석이 확보되었습니다. **결제와 발권은 자동화하지 않습니다.** "
                "기한 내에 코레일 앱/웹에서 직접 결제하세요."
            ),
        }


def _extract_train_no(text: str) -> str | None:
    m = re.search(r"\b(\d{3,5})\b", text)
    return m.group(1) if m else None


def _extract_reservation_no(text: str) -> str | None:
    m = re.search(r"([0-9]{6,}-?[0-9]{0,6})", text)
    return m.group(1) if m else None
