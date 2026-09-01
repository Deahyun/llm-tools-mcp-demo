"""예제 1 — async / await 의 가장 작은 형태.

실행: python demo/01_hello_async.py

배울 것:
  - `async def` 로 정의한 함수는 호출해도 바로 실행되지 않고 '코루틴 객체'를 돌려준다.
  - 실제로 실행하려면 `await` 하거나 `asyncio.run()` 에 넘겨야 한다.
"""

import asyncio


async def hello() -> str:
    print("hello ...")
    await asyncio.sleep(1)  # 1초 '기다림'. 그동안 이벤트 루프는 다른 일을 할 수 있다.
    print("... world")
    return "hello world"


async def main() -> None:
    # async def 를 그냥 호출하면? 실행되지 않는다.
    coro = hello()
    print("호출 결과 타입:", type(coro).__name__)  # coroutine

    # await 를 붙여야 비로소 실행되고, return 값이 나온다.
    result = await coro
    print("반환값:", result)


if __name__ == "__main__":
    # asyncio.run() 이 이벤트 루프를 만들고, main() 을 끝까지 돌린 뒤 정리한다.
    asyncio.run(main())
