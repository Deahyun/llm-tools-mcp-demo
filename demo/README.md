# demo — async / await 학습용 예제

Python `asyncio` 의 `async` / `await` 를 손으로 돌려보기 위한 최소 예제 모음입니다.
이 프로젝트의 본체(`src/toolsdemo/`)와는 무관하며, 의존성도 표준 라이브러리뿐입니다.

## 실행

```powershell
python demo/01_hello_async.py
python demo/02_arithmetic.py
python demo/03_gather.py
```

## 파일

| 파일 | 다루는 것 |
|------|-----------|
| `01_hello_async.py` | `async def` / `await` / `asyncio.run()` 의 기본. async 함수는 호출만으로는 실행되지 않는다 |
| `02_arithmetic.py` | 사칙연산을 async 함수로. 순차 실행 → `gather` → `to_thread` 를 한 파일에서 비교 |
| `03_gather.py` | `asyncio.gather()` 로 동시 실행. 순차 3초 → 동시 1.5초 |

## 핵심 세 줄

1. `async def` 로 만든 함수를 호출하면 **코루틴 객체**가 나올 뿐, 몸통은 아직 실행되지 않는다.
   실행시키는 것은 `await` 또는 `asyncio.run()`.
2. `await` 를 만나면 그 자리에서 제어권을 이벤트 루프에 넘긴다. 그래서 **기다리는 동안 다른 코루틴이 돈다.**
3. 그러므로 이득은 **기다리는 일(I/O)** 에서만 난다. CPU 계산을 async 로 감싸도 빨라지지 않는다
   (그건 `multiprocessing` 또는 `run_in_executor` 의 영역).

## 동시에 실행하려면 스레드가 필요한가?

아니요. `asyncio.gather()` 는 **단일 스레드**에서 동시성을 만듭니다.
`02_arithmetic.py` 를 실행하면 실제 측정값이 나옵니다:

```
[1] 순차 실행 (await 를 줄줄이)        0.82초   스레드 1개
[2] 동시 실행 (asyncio.gather)         0.20초   스레드 1개
[3] 블로킹 함수 (asyncio.to_thread)    0.22초   스레드 3개
    (비교) to_thread 없이 그냥 호출    0.41초
```

스레드는 **`await` 할 수 없는 코드**를 만났을 때만 씁니다.

| 상황 | 도구 | 스레드 |
|------|------|--------|
| `asyncio.sleep`, `aiohttp`, Playwright async API 등 await 가능한 I/O | `asyncio.gather` | 불필요 |
| `time.sleep`, `requests.get`, 동기 DB 드라이버 등 블로킹 호출 | `asyncio.to_thread` | 필요 |
| 무거운 CPU 계산 (GIL 에 막힘) | `ProcessPoolExecutor` | 스레드로도 안 됨 |

## 자주 하는 실수

```python
# X — await 를 빼먹음. 아무 일도 일어나지 않고 경고만 뜬다.
add(1, 2)

# O
await add(1, 2)
```

```python
# X — async 함수를 동기 함수에서 그냥 부를 수 없다.
def main():
    result = await add(1, 2)  # SyntaxError


# O — 진입점 하나를 asyncio.run() 으로 연다.
async def main():
    result = await add(1, 2)


asyncio.run(main())
```

```python
# X — 동시 실행처럼 보이지만 순차 실행이다. (await 를 즉시 하니까)
a = await slow(1)
b = await slow(2)

# O — 동시 실행
a, b = await asyncio.gather(slow(1), slow(2))
```

```python
# X — async 함수 안에서 동기 sleep. 이벤트 루프 전체가 멈춘다.
time.sleep(1)

# O
await asyncio.sleep(1)
```
