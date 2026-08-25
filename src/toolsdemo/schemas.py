"""도구가 주고받는 데이터 구조."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrainOption(BaseModel):
    """조회된 열차 한 편."""

    train_type: str = Field(description="열차 종류 (KTX, ITX-새마을, 무궁화호 ...)")
    train_no: str = Field(description="열차 번호")
    departure: str
    arrival: str
    depart_time: str = Field(description="출발 시각, HH:MM")
    arrive_time: str = Field(description="도착 시각, HH:MM")
    duration_min: int
    price: int = Field(description="일반실 운임 (원)")
    seats_left: int = Field(description="잔여 좌석 수. 0 이면 매진")

    @property
    def sold_out(self) -> bool:
        return self.seats_left <= 0


class SearchResult(BaseModel):
    ok: bool = True
    query: dict
    options: list[TrainOption] = []
    message: str | None = None


class BookingResult(BaseModel):
    ok: bool
    reservation_no: str | None = None
    train_no: str | None = None
    passenger: str | None = None
    passengers: int = 1
    total_price: int | None = None
    message: str | None = None
