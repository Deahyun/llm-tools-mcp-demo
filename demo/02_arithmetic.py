"""예제 2 — 사칙연산을 async 함수로.

실행: python demo/02_arithmetic.py

배울 것:
  - async 함수도 평범한 함수처럼 인자를 받고 값을 돌려준다.
  - await 로 부른 코루틴은 '순차적으로' 실행된다 (아직 동시성은 없다).
  - 동시에 실행하려면 스레드가 아니라 asyncio.gather() 를 쓴다.
  - await 할 수 없는 '블로킹' 함수를 만났을 때만 스레드(asyncio.to_thread)로 도망간다.
  - 예외 처리는 동기 코드와 똑같이 try/except.
"""

import asyncio
import threading
import time

# ---------------------------------------------------------------- async 버전
# await asyncio.sleep() 은 '기다리는 동안 제어권을 이벤트 루프에 넘긴다'.
# 그래서 이 함수들은 gather 로 묶으면 동시에 진행된다.


async def add(a: float, b: float) -> float:
    await asyncio.sleep(0.2)  # 계산에 시간이 걸린다고 가정
    return a + b


async def sub(a: float, b: float) -> float:
    await asyncio.sleep(0.2)
    return a - b


async def mul(a: float, b: float) -> float:
    await asyncio.sleep(0.2)
    return a * b


async def div(a: float, b: float) -> float:
    await asyncio.sleep(0.2)
    if b == 0:
        raise ZeroDivisionError("0 으로 나눌 수 없습니다")
    return a / b


# ------------------------------------------------------------- 블로킹 버전
# async 가 아닌 평범한 함수. time.sleep 은 await 할 수 없고, 스레드를 통째로 멈춘다.
# async 함수 안에서 이걸 그냥 호출하면 이벤트 루프 전체가 그 시간만큼 얼어붙는다.


def blocking_add(a: float, b: float) -> float:
    time.sleep(0.2)
    return a + b


def blocking_mul(a: float, b: float) -> float:
    time.sleep(0.2)
    return a * b


async def main() -> None:
    a, b = 12, 4

    # --- 1) 순차 실행: await 를 하나씩 → 0.2초 x 4 = 약 0.8초 ---
    print("[1] 순차 실행 (await 를 줄줄이)")
    t0 = time.perf_counter()
    print(f"  {a} + {b} = {await add(a, b)}")
    print(f"  {a} - {b} = {await sub(a, b)}")
    print(f"  {a} * {b} = {await mul(a, b)}")
    print(f"  {a} / {b} = {await div(a, b)}")
    print(f"  걸린 시간 {time.perf_counter() - t0:.2f}초\n")

    # --- 2) 동시 실행: gather 로 묶어서 → 약 0.2초 ---
    # 스레드를 쓰지 않는다. 아래 출력의 '스레드 수'가 그 증거.
    print("[2] 동시 실행 (asyncio.gather)")
    t0 = time.perf_counter()
    results = await asyncio.gather(add(a, b), sub(a, b), mul(a, b), div(a, b))
    print(f"  결과 {results}  (넘긴 순서대로 반환된다)")
    print(f"  걸린 시간 {time.perf_counter() - t0:.2f}초")
    print(
        f"  스레드 수 {threading.active_count()} / 실행 스레드 {threading.current_thread().name}\n"
    )

    # --- 3) await 할 수 없는 블로킹 함수를 동시에 돌리기 ---
    # time.sleep 은 await 가 안 되므로 gather 로 묶어도 소용없다.
    # asyncio.to_thread() 가 별도 스레드로 떠넘겨 주고, 그 대기를 await 할 수 있게 만든다.
    print("[3] 블로킹 함수 동시 실행 (asyncio.to_thread)")
    t0 = time.perf_counter()
    blocked = await asyncio.gather(
        asyncio.to_thread(blocking_add, a, b),
        asyncio.to_thread(blocking_mul, a, b),
    )
    print(f"  결과 {blocked}")
    print(f"  걸린 시간 {time.perf_counter() - t0:.2f}초")
    print(f"  스레드 수 {threading.active_count()} (워커 스레드가 늘어난다)\n")

    # 참고: 같은 블로킹 함수를 to_thread 없이 부르면 0.2초씩 더해진다.
    t0 = time.perf_counter()
    blocking_add(a, b)
    blocking_mul(a, b)
    print(f"  (비교) to_thread 없이 그냥 호출 {time.perf_counter() - t0:.2f}초\n")

    # --- 4) 예외 처리는 동기 코드와 똑같다 ---
    print("[4] 예외 처리")
    try:
        await div(a, 0)
    except ZeroDivisionError as e:
        print("  ", e)

    # gather 안에서 예외가 나면 기본적으로 그대로 전파된다.
    # return_exceptions=True 를 주면 예외 '객체'가 결과 리스트에 담겨 온다.
    mixed = await asyncio.gather(div(a, b), div(a, 0), return_exceptions=True)
    print("   return_exceptions=True →", mixed)


if __name__ == "__main__":
    asyncio.run(main())
