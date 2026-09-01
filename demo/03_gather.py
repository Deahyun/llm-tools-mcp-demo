"""예제 3 — asyncio.gather 로 동시에 실행하기. (async/await 를 쓰는 진짜 이유)

실행: python demo/03_gather.py

배울 것:
  - await 를 줄줄이 늘어놓으면 '순차 실행'이라 시간이 더해진다.
  - asyncio.gather() 로 묶으면 '동시 대기'라 가장 느린 것 하나만큼만 걸린다.
  - 단, 이 이득은 기다리는 일(I/O: 네트워크·파일·sleep)에만 해당한다.
    CPU 를 태우는 계산은 async 로 바꿔도 빨라지지 않는다.
"""

import asyncio
import time


async def slow_add(a: float, b: float, delay: float) -> float:
    """delay 초 기다린 뒤 a + b 를 돌려준다."""
    print(f"  시작: {a} + {b} (예상 {delay}초)")
    await asyncio.sleep(delay)
    print(f"  완료: {a} + {b} = {a + b}")
    return a + b


async def main() -> None:
    jobs = [(1, 2, 1.0), (10, 20, 1.5), (100, 200, 0.5)]

    # --- 순차 실행: 1.0 + 1.5 + 0.5 = 약 3초 ---
    print("[순차 실행]")
    t0 = time.perf_counter()
    sequential = []
    for a, b, delay in jobs:
        sequential.append(await slow_add(a, b, delay))
    print(f"결과 {sequential} / 걸린 시간 {time.perf_counter() - t0:.2f}초\n")

    # --- 동시 실행: max(1.0, 1.5, 0.5) = 약 1.5초 ---
    print("[동시 실행 - gather]")
    t0 = time.perf_counter()
    concurrent = await asyncio.gather(*(slow_add(a, b, d) for a, b, d in jobs))
    print(f"결과 {concurrent} / 걸린 시간 {time.perf_counter() - t0:.2f}초")

    # gather 는 넘긴 순서대로 결과를 돌려준다 (끝난 순서가 아님).
    assert sequential == concurrent


if __name__ == "__main__":
    asyncio.run(main())
