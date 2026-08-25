"""사이트 어댑터 인터페이스.

**CSS 셀렉터는 오직 어댑터에만 존재합니다.** `booking.py` 는 이 인터페이스만 호출합니다.
새 사이트를 붙이려면 이 클래스를 구현하고 `get_adapter()` 에 등록하세요.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from playwright.async_api import Page


class SiteAdapter(ABC):
    #: 사람이 읽는 사이트 식별자
    name: str = "base"
    #: 예약 확정(좌석 확보) 자동화 허용 여부. 결제는 어떤 어댑터에서도 자동화하지 않는다.
    allows_confirm: bool = False

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    async def open_search(self, page: Page) -> None:
        """조회 화면을 연다."""

    @abstractmethod
    async def search(
        self, page: Page, departure: str, arrival: str, date: str, depart_after: str
    ) -> list[dict[str, Any]]:
        """조회 폼을 채우고 실행한 뒤 열차 목록을 반환한다."""

    @abstractmethod
    async def open_reserve(self, page: Page, train_no: str) -> dict[str, Any]:
        """결과 목록에서 특정 열차의 예약 화면으로 진입한다."""

    @abstractmethod
    async def fill_passenger(
        self, page: Page, name: str, phone: str, passengers: int
    ) -> dict[str, Any]:
        """예약자 정보를 입력한다 (제출하지 않는다)."""

    @abstractmethod
    async def confirm(self, page: Page) -> dict[str, Any]:
        """예약을 확정해 좌석을 확보한다. 결제는 포함하지 않는다."""


def get_adapter(target_site: str, mock_url: str, korail_url: str) -> SiteAdapter:
    from .korail import KorailAdapter
    from .mock import MockSiteAdapter

    if target_site == "korail":
        return KorailAdapter(korail_url)
    return MockSiteAdapter(mock_url)
