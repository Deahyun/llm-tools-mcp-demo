"""mock 사이트의 시간표 생성 로직 검증. 서버 기동·브라우저 불필요."""

from __future__ import annotations

from toolsdemo.mocksite.server import generate_schedule, resolve_station


def test_resolve_station_handles_aliases_and_suffix():
    assert resolve_station("서울") == "서울"
    assert resolve_station("서울역") == "서울"
    assert resolve_station("대구") == "동대구"
    assert resolve_station(" 부산 ") == "부산"


def test_schedule_is_deterministic():
    a = generate_schedule("서울", "부산", "2026-09-01")
    b = generate_schedule("서울", "부산", "2026-09-01")
    assert a == b
    assert len(a) > 5


def test_schedule_changes_with_date():
    a = generate_schedule("서울", "부산", "2026-09-01")
    b = generate_schedule("서울", "부산", "2026-09-02")
    assert [r["seats_left"] for r in a] != [r["seats_left"] for r in b]


def test_schedule_rows_are_well_formed():
    rows = generate_schedule("서울", "부산", "2026-09-01")
    for r in rows:
        assert r["departure"] == "서울" and r["arrival"] == "부산"
        assert len(r["depart_time"]) == 5 and r["depart_time"][2] == ":"
        assert r["arrive_time"] > r["depart_time"] or r["duration_min"] > 0
        assert r["price"] > 0
        assert r["seats_left"] >= 0
    # 매진 케이스가 섞여 있어야 '매진 → 다른 열차 선택' 흐름을 시연할 수 있다
    assert any(r["seats_left"] == 0 for r in rows)


def test_unknown_or_identical_stations_return_empty():
    assert generate_schedule("없는역", "부산", "2026-09-01") == []
    assert generate_schedule("서울", "서울", "2026-09-01") == []


def test_ktx_is_faster_than_mugunghwa():
    rows = generate_schedule("서울", "부산", "2026-09-01")
    ktx = min(r["duration_min"] for r in rows if r["train_type"] == "KTX")
    slow = min(r["duration_min"] for r in rows if r["train_type"] == "무궁화호")
    assert ktx < slow
