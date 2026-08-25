"""코레일 유사 mock 예약 사이트 (FastAPI).

실제 사이트를 건드리지 않고 전체 예매 흐름을 재현하기 위한 로컬 서버입니다.
테스트/CI/데모 녹화는 전부 여기서 완결되어야 합니다.

실행:
    python -m toolsdemo.mocksite.server
"""

from __future__ import annotations

import hashlib
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import settings

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

app = FastAPI(title="Mock 기차 예약", docs_url=None, redoc_url=None)

# 서울 기점 누적 거리(km). 소요시간/운임 계산에만 쓰는 근사치입니다.
STATIONS: dict[str, int] = {
    "서울": 0,
    "용산": 3,
    "수서": 10,
    "광명": 22,
    "천안아산": 96,
    "오송": 128,
    "대전": 166,
    "김천구미": 253,
    "동대구": 294,
    "신경주": 351,
    "울산": 391,
    "부산": 442,
    "익산": 240,
    "광주송정": 350,
    "목포": 400,
    "여수엑스포": 420,
    "강릉": 223,
    "포항": 340,
    "창원": 400,
}

# (열차종류, 표정속도 km/h, km당 운임, 기본운임)
TRAIN_TYPES = [
    ("KTX", 180, 100, 8000),
    ("ITX-새마을", 110, 70, 5000),
    ("무궁화호", 85, 50, 3000),
]

RESERVATIONS: dict[str, dict] = {}


def _seed(*parts: str) -> int:
    raw = "|".join(parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


def resolve_station(name: str) -> str:
    """사용자 입력 역명을 표준 역명으로. 못 찾으면 원문을 그대로 돌려준다."""
    name = (name or "").strip()
    if name in STATIONS:
        return name
    aliases = {"서울역": "서울", "부산역": "부산", "대구": "동대구", "광주": "광주송정"}
    if name in aliases:
        return aliases[name]
    for station in STATIONS:
        if name and (name in station or station in name):
            return station
    return name


def generate_schedule(departure: str, arrival: str, day: str) -> list[dict]:
    """(출발역, 도착역, 날짜) 에 대해 항상 동일한 시간표를 생성한다."""
    dep = resolve_station(departure)
    arr = resolve_station(arrival)
    if dep not in STATIONS or arr not in STATIONS or dep == arr:
        return []

    distance = abs(STATIONS[dep] - STATIONS[arr])
    seed = _seed(dep, arr, day)
    rows: list[dict] = []

    slot = 0
    cursor = datetime.strptime("05:10", "%H:%M")
    end = datetime.strptime("22:30", "%H:%M")
    while cursor <= end:
        kind, speed, per_km, base = TRAIN_TYPES[slot % len(TRAIN_TYPES)]
        duration = max(20, round(distance / speed * 60) + (seed >> (slot % 5)) % 7)
        arrive = cursor + timedelta(minutes=duration)
        price = round((base + distance * per_km) / 100) * 100
        seats = (seed // (slot + 3)) % 42
        if slot % 11 == 0:
            seats = 0  # 매진 케이스도 섞어 둔다
        rows.append(
            {
                "train_type": kind,
                "train_no": f"{(slot % len(TRAIN_TYPES)) + 1}{100 + slot:03d}",
                "departure": dep,
                "arrival": arr,
                "depart_time": cursor.strftime("%H:%M"),
                "arrive_time": arrive.strftime("%H:%M"),
                "duration_min": duration,
                "price": price,
                "seats_left": seats,
            }
        )
        cursor += timedelta(minutes=35 + (seed >> slot % 7) % 20)
        slot += 1

    return rows


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    today = date_cls.today().isoformat()
    return templates.TemplateResponse(
        request, "index.html", {"stations": list(STATIONS), "today": today}
    )


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    departure: str = "",
    arrival: str = "",
    date: str = "",
    depart_after: str = "",
):
    day = date or date_cls.today().isoformat()
    rows = generate_schedule(departure, arrival, day)
    if depart_after:
        rows = [r for r in rows if r["depart_time"] >= depart_after]
    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "departure": resolve_station(departure),
            "arrival": resolve_station(arrival),
            "date": day,
            "depart_after": depart_after,
            "rows": rows,
        },
    )


@app.get("/reserve", response_class=HTMLResponse)
async def reserve(
    request: Request,
    train_no: str = "",
    date: str = "",
    departure: str = "",
    arrival: str = "",
):
    day = date or date_cls.today().isoformat()
    rows = generate_schedule(departure, arrival, day)
    train = next((r for r in rows if r["train_no"] == train_no), None)
    return templates.TemplateResponse(
        request,
        "reserve.html",
        {"train": train, "date": day, "train_no": train_no},
        status_code=200 if train else 404,
    )


@app.post("/confirm", response_class=HTMLResponse)
async def confirm(
    request: Request,
    train_no: str = Form(""),
    date: str = Form(""),
    departure: str = Form(""),
    arrival: str = Form(""),
    name: str = Form(""),
    phone: str = Form(""),
    passengers: int = Form(1),
):
    rows = generate_schedule(departure, arrival, date)
    train = next((r for r in rows if r["train_no"] == train_no), None)
    if train is None:
        return templates.TemplateResponse(
            request,
            "done.html",
            {"error": "존재하지 않는 열차입니다.", "reservation": None},
            status_code=404,
        )
    if train["seats_left"] < passengers:
        return templates.TemplateResponse(
            request,
            "done.html",
            {"error": "잔여 좌석이 부족합니다.", "reservation": None},
            status_code=409,
        )

    reservation_no = f"R{_seed(train_no, date, name, phone, str(passengers)) % 100000000:08d}"
    reservation = {
        "reservation_no": reservation_no,
        "train": train,
        "name": name,
        "phone": phone,
        "passengers": passengers,
        "total_price": train["price"] * passengers,
        "date": date,
    }
    RESERVATIONS[reservation_no] = reservation
    return templates.TemplateResponse(
        request, "done.html", {"reservation": reservation, "error": None}
    )


def main() -> None:
    import uvicorn

    parsed = urlparse(settings.mock_site_url)
    uvicorn.run(
        app,
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 8765,
        log_level="info",
    )


if __name__ == "__main__":
    main()
