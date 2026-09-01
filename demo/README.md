# demo — async/await, tool calling, MCP 학습용 예제

손으로 돌려보며 익히기 위한 최소 예제 모음입니다. 이 프로젝트의 본체(`src/toolsdemo/`)를
 import 하지 않으며, **각 파일이 단독으로 실행됩니다.**

- `01~03` — `asyncio` 기초. 표준 라이브러리만 사용
- `11~13` — LLM 이 도구를 호출하는 세 가지 경로. `ollama` / `mcp` 패키지 필요

## 실행

```powershell
# 기초 — 준비물 없음
python demo/01_hello_async.py
python demo/02_arithmetic.py
python demo/03_gather.py

# 도구 호출 — Ollama 가 떠 있어야 하고 모델이 있어야 한다
python demo/11_tool_call.py
python demo/12_mcp_local.py

# 13 은 터미널 2개. 서버를 먼저 띄운다
python demo/13_mcp_http_server.py          # 터미널 A (계속 떠 있음)
python demo/13_mcp_http_client.py          # 터미널 B

# 같은 서버를 고수준 API 로 다시 쓴 판. 클라이언트는 그대로 붙는다
python demo/13_mcp_fastapi_style.py        # 터미널 A 대신

# 질의를 직접 주려면
python demo/11_tool_call.py "hello 로 test 해줘"
```

11/12 는 준비할 것이 없습니다. 12 는 자기 자신을 `--server` 모드의 자식 프로세스로
기동했다가 끝나면 정리합니다. **13 만 서버를 직접 띄워야 합니다** — 도구가 어느
프로세스에 사는지 눈에 보이도록 서버와 클라이언트를 다른 파일로 나눴기 때문입니다.

## 파일

| 파일 | 다루는 것 |
|------|-----------|
| `01_hello_async.py` | `async def` / `await` / `asyncio.run()` 의 기본. async 함수는 호출만으로는 실행되지 않는다 |
| `02_arithmetic.py` | 사칙연산을 async 함수로. 순차 실행 → `gather` → `to_thread` 를 한 파일에서 비교 |
| `03_gather.py` | `asyncio.gather()` 로 동시 실행. 순차 3초 → 동시 1.5초 |
| `11_tool_call.py` | **Native tool calling** — 모델이 파이썬 함수를 직접 호출 · [상세 설명](../docs/11_코드설명.md) |
| `12_mcp_local.py` | **MCP (stdio)** — 같은 도구를 자식 프로세스 MCP 서버로 노출 · [상세 설명](../docs/12_코드설명.md) |
| `13_mcp_http_server.py` | **MCP (Streamable HTTP) 서버** — 도구는 이 파일에만 있다 · [상세 설명](../docs/13_코드설명.md) |
| `13_mcp_http_client.py` | **MCP (Streamable HTTP) 클라이언트** — 도구 코드가 한 줄도 없다 |
| `13_mcp_fastapi_style.py` | 위 서버를 **고수준 API(`MCPServer`)로 다시 쓴 것** — 요즘 방식 |

## 핵심 세 줄

1. `async def` 로 만든 함수를 호출하면 **코루틴 객체**가 나올 뿐, 몸통은 아직 실행되지 않는다.
   실행시키는 것은 `await` 또는 `asyncio.run()`.
2. `await` 를 만나면 그 자리에서 제어권을 이벤트 루프에 넘긴다. 그래서 **기다리는 동안 다른 코루틴이 돈다.**
3. 그러므로 이득은 **기다리는 일(I/O)** 에서만 난다. CPU 계산을 async 로 감싸도 빨라지지 않는다
   (그건 `multiprocessing` 또는 `run_in_executor` 의 영역).

## 11~13 — 도구를 조달하는 세 가지 경로

셋 다 **같은 도구, 같은 에이전트 루프, 같은 결과**입니다. 달라지는 것은 도구가
어디서 오고 어디서 실행되느냐뿐입니다.

```python
def test(a: str) -> str:  # 세 파일에 그대로 복사돼 있는 도구
    res = "123---" + a + "---456"
    print(f"{res}")
    return res
```

| | 11 native | 12 MCP stdio | 13 MCP http |
|---|---|---|---|
| 파일 수 | 1 | 1 (서버 겸용) | 2 (서버/클라이언트 분리) |
| 도구 명세 | 코드에 쓴 dict | `list_tools()` 응답 | `list_tools()` 응답 |
| 도구 실행 | 함수 직접 호출 | `call_tool()` + 파이프 | `call_tool()` + 소켓 |
| 도구가 도는 곳 | 같은 프로세스 | 자식 프로세스 | 서버 프로세스(원격 가능) |
| 서버 준비 | 없음 | 클라이언트가 자동 기동 | **직접 띄운다** |
| 동시 접속 | 해당 없음 | 1:1 | 1:N |
| `print()` | 자유 | **금지**(stdout=JSON-RPC) | 자유 |
| 모델이 보는 tools | — 셋 다 같음 — | | |

실행하면 세 파일 모두 같은 답을 냅니다.

```
[1] 도구 호출: test({'a': '안녕하세요'})
123---안녕하세요---456
[1] 도구 결과: {'ok': True, 'result': '123---안녕하세요---456'}
[2] 도구 호출 없음 -> 종료
```

세 파일에서 반복해서 나오는 규칙 세 가지:

1. **도구 실패를 예외로 던지지 않는다.** `{"ok": false, "error": ...}` 로 돌려줘야
   LLM 이 읽고 스스로 고쳐 다시 시도합니다.
2. **docstring/description 이 곧 프롬프트다.** 모델이 도구를 안 부르면 시스템 프롬프트가
   아니라 도구 설명을 먼저 의심하세요.
3. **stdio MCP 서버에서 `print()` 는 금지.** stdout 이 JSON-RPC 전용이라 프로토콜이 깨집니다.
   `12_mcp_local.py` 는 `contextlib.redirect_stdout(sys.stderr)` 로 이를 피해 갑니다.
   13번(HTTP)에는 이 제약이 없습니다.
4. **도구는 서버 프로세스에서만 실행된다.** `13_mcp_http_client.py` 에는 `test()` 가
   아예 없습니다. 어떤 도구가 있는지는 `list_tools()` 로 물어보고, 실행은 서버에 맡깁니다.
   13번을 두 파일로 나눈 이유가 이 경계를 눈에 보이게 하기 위해서입니다.

> 모델은 `OLLAMA_MODEL` 환경변수로 바꿉니다(기본 `qwen3.8-local:27b`).
> 27B 첫 로딩은 1분 이상 걸릴 수 있습니다.

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
