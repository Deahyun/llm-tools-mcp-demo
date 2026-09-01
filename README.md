# ToolsDemo — 로컬 LLM으로 브라우저를 조작하는 에이전트 (Tools → MCP)

자연어 기차 예약 요청을 **로컬 LLM(Ollama · qwen3.6)** 이 해석하고, LLM이 스스로 도구를
호출해 **Playwright** 로 브라우저를 조작합니다. 사람이 흐름을 짜 주지 않습니다 —
무엇을 언제 부를지는 모델이 정하고, 도구는 그 결정에 답할 뿐입니다.

그 위에서 **도구를 조달하는 경로를 두 단계로 구현해 비교**합니다. 같은 에이전트를
native tool calling으로 한 번, MCP로 한 번 돌려 **무엇이 바뀌고 무엇이 그대로인지**를
실제로 돌아가는 코드로 보여줍니다.

| | Phase 1 | Phase 2 |
|---|---|---|
| 방식 | Ollama **native tool calling** | **MCP** (Model Context Protocol) |
| 도구 스키마 출처 | 프로세스 내부 registry | MCP 서버의 `list_tools()` |
| 도구 실행 | 함수 직접 호출 | MCP `call_tool()` (stdio, 별도 프로세스) |
| 진입점 | `python -m toolsdemo.agent_tools` | `python -m toolsdemo.mcp_.client_agent` |

대상 사이트는 기본이 **로컬 mock 예매 사이트**라 아무것도 실제로 예약되지 않습니다.
실제 코레일은 opt-in이며, 어느 쪽이든 자동화는 **예약(좌석 확보)까지**이고
결제·발권은 사람이 합니다.

---

## 핵심 — 도구는 한 번만 정의한다

도구 로직은 `src/toolsdemo/tools/` **한 곳에만** 존재합니다. Phase 1과 Phase 2는 그것을
감싸는 얇은 어댑터일 뿐입니다. 로직이 양쪽에 복사되는 순간 비교의 의미가 사라집니다.

```python
@tool
async def get_today() -> dict[str, Any]:
    """오늘 날짜와 요일을 알려준다. '내일', '이번 주말' 같은 표현을 날짜로 바꿀 때 먼저 호출한다.

    Returns:
        today: 오늘 날짜 (YYYY-MM-DD), weekday: 요일, tomorrow: 내일 날짜
    """
```

`@tool` 데코레이터가 **타입 힌트와 docstring에서 JSON Schema를 자동 생성**합니다.
JSON Schema를 손으로 쓰는 곳은 이 저장소에 없습니다. 도구를 하나 추가하면
Phase 1과 MCP 양쪽에 **동시에** 노출됩니다.

```
             @tool 등록
                 │
        tools/registry.py  ← 단일 진실 원천
           │           │
   ollama_tool_schemas   mcp_/server.py (list_tools 로 번역)
           │           │
      Phase 1 에이전트   Phase 2 에이전트
           └─────┬─────┘
        llm/ollama_client.py  ← 에이전트 루프는 공유
```

## MCP 전환에서 바뀌는 것 / 그대로인 것

| 바뀌는 것 | 그대로인 것 |
|---|---|
| 도구 스키마의 출처 (registry → `list_tools()`) | 도구 구현 코드 |
| 실행 위치 (같은 프로세스 → 별도 프로세스) | 에이전트 루프와 시스템 프롬프트 |
| 직렬화 경계 (dict → JSON 텍스트 왕복) | **모델에게 보이는 tools 배열** |
| 로그 채널 (stdout 금지, stderr 강제) | 실패를 표현하는 방식 (`{"ok": false, ...}`) |
| 프로세스 lifecycle (클라이언트가 서버 기동) | 같은 질의 → 같은 결과 |

MCP 서버는 registry를 프로토콜로 번역하는 것 외에 하는 일이 없습니다. 새 도구를 추가해도
[`mcp_/server.py`](src/toolsdemo/mcp_/server.py)는 손대지 않습니다.

```python
tools = [
    types.Tool(name=spec.name, description=spec.description, input_schema=spec.parameters)
    for spec in get_registry().values()
]
```

## 동일성은 말이 아니라 테스트로 강제한다

[`tests/test_parity.py`](tests/test_parity.py)가 MCP 서버를 stdio로 띄워 `list_tools()` 응답을
registry와 **스키마 단위로 대조**합니다. 두 Phase가 모델에게 보여주는 tools 배열이 완전히
같아야 통과합니다. LLM 없이 돌아가므로 CI에서도 매번 검증됩니다.

```python
assert set(got) == set(expected)  # 도구 집합
assert got[name].description == spec.description  # 설명
assert got[name].input_schema == spec.parameters  # 입력 스키마
```

MCP 쪽 노출을 빠뜨린 채 도구를 추가하면 여기서 깨집니다.

---

## 실전 노트 — 도구를 설계하며 배운 것

**1. docstring이 곧 프롬프트다.**
모델이 도구를 호출하지 않거나 인자를 틀리면 시스템 프롬프트가 아니라 **docstring을 먼저
의심**하세요. 도구 설명과 인자 설명은 모델이 읽는 유일한 사용 설명서입니다.
날짜는 `YYYY-MM-DD`, 시각은 `HH:MM` 처럼 형식을 반드시 명시해야 합니다.

**2. 도구는 예외를 던지지 않는다.**
실패도 `{"ok": false, "error": "..."}` 라는 **데이터**로 돌려줍니다. 그래야 모델이 읽고
스스로 고쳐 재시도합니다. 예외로 죽으면 루프가 거기서 끝납니다.

**3. 모델은 스키마에 없는 인자를 만들어 보낸다.**
registry가 정의되지 않은 인자를 걸러내고 warning으로 남깁니다. 안 그러면 `TypeError`로
죽습니다. 방어는 도구마다가 아니라 호출 계층에서 한 번만 합니다.

**4. 응답을 조용히 자르지 마라.**
조회 결과 22편 중 12편만 넘기면서 `count`만 22로 주면, 모델은 12편이 전부라고 믿고
"밤 열차는 없다"고 답합니다. 자를 거라면 잘랐다는 사실과 **회복 방법**을 함께 줘야 합니다.

```python
{"count": 22, "returned": 12, "truncated": True, "last_depart_time": "22:16",
 "message": "... 12편만 표시했습니다 (마지막 14:05, 막차 22:16).
             더 늦은 열차가 필요하면 depart_after 를 늦춰 다시 조회하세요."}
```

**5. 하고 싶지 않은 일은 도구를 만들지 않는다.**
"결제하지 마"라고 프롬프트로 막는 것보다 **결제 도구가 존재하지 않는 편**이 확실합니다.
도구가 없으면 모델은 시도조차 하지 못합니다. 프롬프트는 우회되지만 도구 부재는 우회되지 않습니다.

**6. 상태를 가진 도구는 세션 소유자를 정해라.**
브라우저는 프로세스당 하나의 싱글턴을 재사용합니다. MCP에서는 서버가 별도 프로세스이므로
브라우저 세션도 **서버 쪽**에 삽니다. 도구 호출마다 새로 띄우면 다단계 흐름이 깨집니다.

**7. MCP stdio 서버에서 `print()` 한 줄이 프로토콜을 깨뜨린다.**
stdout은 JSON-RPC 전용입니다. 로그는 반드시 `logging`(stderr)으로만 남기세요.

**8. MCP 실패를 `is_error`로 표현하지 마라.**
그러면 Phase 1과 동작이 달라집니다. 실패는 Phase 1과 **똑같이** `{"ok": false, "error": ...}`
페이로드로 전달하고, 그 동일성을 parity 테스트가 지킵니다.

**9. MCP SDK 2.x는 1.x와 API가 다르다.** 웹의 1.x 예제를 붙여넣으면 동작하지 않습니다.

| | 1.x | 2.x (이 저장소) |
|---|---|---|
| 서버 핸들러 | `@server.list_tools()` 데코레이터 | `Server(on_list_tools=..., on_call_tool=...)` |
| Tool 스키마 필드 | `inputSchema=` | `input_schema=` |
| 핸들러 반환 | `list[Tool]` / `list[TextContent]` | `ListToolsResult` / `CallToolResult` |
| 클라이언트 | `stdio_client()` + `ClientSession` | `Client(StdioServerParameters(...))` |

**10. LLM 없이 도구만 돌리는 경로를 항상 유지하라.**
[`tests/test_booking_flow.py`](tests/test_booking_flow.py)는 모델 없이 도구만으로 전 과정을
검증합니다. 에이전트가 실패했을 때 원인이 **도구인지 모델인지** 가르는 기준선이 됩니다.

---

## 자동화 경계 — 어디까지 시키고 어디서 멈추는가

```
조회 → 열차 선택 → 예약자 정보 → 예약 확정(좌석 확보)  │  결제 → 발권
└──────────────── 에이전트가 자동화 ───────────────┘  └── 사람이 직접 ──┘
```

**결제를 수행하는 도구는 아예 존재하지 않습니다.** 에이전트는 좌석을 확보하고 예약번호와
결제 기한을 돌려준 뒤 사람에게 넘깁니다. mock 사이트도 같은 경계를 모델링해 완료 화면이
"예약 완료(결제 대기)"이며 결제 버튼이 없습니다. 위 실전 노트 5번의 실제 적용 사례입니다.

기차 예약을 소재로 고른 이유도 여기에 있습니다. **여러 단계에 걸쳐 상태가 이어지는 흐름**이라
앞 호출의 결과가 다음 호출의 전제가 되고, 순서를 어기면 실패합니다 — 단발성 도구에서는
드러나지 않는 문제들이 그대로 나옵니다.

## 요구사항

- Windows 11 (네이티브 실행. WSL 불필요)
- Python 3.10+
- [Ollama](https://ollama.com) 실행 중 + tool calling 지원 모델
  - 기본: `qwen3.6:27b` (약 17GB, VRAM 24GB 권장)
  - 대안: `gpt-oss:20b`, `qwen3.8:27b`
- 최초 1회 Playwright Chromium 다운로드 (~150MB)

## 설치

```powershell
git clone <이 저장소>
cd ToolsDemo
.\scripts\setup.ps1        # venv + 의존성 + Chromium + .env 생성
```

수동으로 하려면:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m playwright install chromium
Copy-Item .env.example .env
```

## 실행

터미널 1 — mock 예약 사이트:

```powershell
python -m toolsdemo.mocksite.server        # http://127.0.0.1:8765
```

터미널 2 — 에이전트:

```powershell
# Phase 1: native tool calling
python -m toolsdemo.agent_tools "내일 오전 9시쯤 서울에서 부산 가는 기차 예약해줘"

# Phase 2: MCP 경유 (같은 질의 → 같은 결과)
python -m toolsdemo.mcp_.client_agent "내일 오전 9시쯤 서울에서 부산 가는 기차 예약해줘"
```

브라우저 창을 보면서 데모하려면 `.env` 에서 `HEADLESS=false` 로 바꾸세요.

LLM 없이 도구만 직접 호출할 수도 있습니다 — 도구 계층만 점검할 때 가장 빠른 경로입니다:

```python
from toolsdemo.tools import booking  # registry 채우기. 필수
from toolsdemo.tools.registry import call_tool

today = await call_tool("get_today", {})
await call_tool(
    "search_trains",
    {"departure": "서울", "arrival": "부산", "date": today["tomorrow"], "depart_after": "09:00"},
)
```

## 실행 결과

`qwen3.6:27b` 로 실제 실행한 결과입니다. 두 Phase가 **같은 도구 순서, 같은 예약번호**로 끝납니다.

```
[Phase 1 · native tools]  model=qwen3.6:27b  target=mock
[tool] → get_today({})
[tool] → search_trains({'departure': '서울', 'arrival': '부산',
                        'date': '2026-08-27', 'depart_after': '09:00'})
[tool] → select_train({'train_no': '3105'})
[tool] → fill_passenger({'name': '홍길동', 'passengers': 1})
[tool] → confirm_booking({})
도구 호출 5회 / 반복 6회

예약이 완료되었습니다.
- 예약번호: R34708865
- 열차: 무궁화호 3105편
- 구간: 서울 → 부산
- 출발: 2026-08-27 09:15
- 결제 예정 금액: 25,100원 / 결제 기한: 10분 이내
⚠️ 결제와 발권은 직접 진행해 주세요.
```

```
[Phase 2 · MCP]  model=qwen3.6:27b  target=mock  mcp_tools=7
[mcp] list_tools → 7개: get_today, search_trains, select_train,
                        fill_passenger, confirm_booking, describe_page, take_screenshot
... 동일한 도구 순서 ...
도구 호출 5회 / 반복 6회 → 예약번호 R34708865
```

도구 호출과 응답은 항상 INFO 레벨로 남습니다(`[tool] → ...` / `[tool] ← ...`).
데모에서는 이 로그 자체가 설명 자료가 됩니다.

## 도구 목록

| 도구 | 설명 |
|------|------|
| `get_today` | 오늘/내일 날짜와 요일. '내일' 같은 표현을 날짜로 바꿀 때 사용 |
| `search_trains` | 출발역/도착역/날짜/시각 이후로 열차 조회 |
| `select_train` | 열차번호로 예약 화면 진입 |
| `fill_passenger` | 예약자 이름·연락처·인원 입력 (확정 아님) |
| `confirm_booking` | 예약 확정 → 예약번호·결제 기한 반환 (**결제 없음**) |
| `describe_page` | 현재 화면 URL/제목/본문 요약 — 흐름이 꼬였을 때 복구용 |
| `take_screenshot` | 현재 화면 PNG 저장 (데모 기록용) |

앞의 4개는 `search_trains → select_train → fill_passenger → confirm_booking` 순서에 의존합니다.
순서를 어기면 예외 대신 `{"ok": false, "error": "search_trains 를 먼저 호출하세요."}` 가 돌아오고,
모델이 그것을 읽고 스스로 복구합니다. 나머지 3개는 순서와 무관합니다.

## 프로젝트 구조

```
src/toolsdemo/
  config.py            환경변수 → 설정
  llm/ollama_client.py 에이전트 루프 (Phase 1/2 공용)
  tools/
    registry.py        @tool 데코레이터 · 스키마 자동 생성 · 안전한 실행
    booking.py         예약 도메인 도구
    browser.py         Playwright 세션 (프로세스당 하나)
    sites/             mock.py · korail.py 어댑터 (셀렉터는 여기에만)
  agent_tools.py       Phase 1 진입점
  mcp_/                Phase 2: MCP 서버 + 클라이언트 에이전트
  mocksite/            FastAPI 기반 mock 예약 사이트
```

> 패키지명이 `mcp_` 인 이유는 MCP 공식 SDK 패키지명 `mcp` 와의 이름 충돌을 피하기 위함입니다.

셀렉터는 `tools/sites/*.py` 어댑터에만 둡니다. `booking.py` 에 CSS 셀렉터가 등장하면
잘못된 설계입니다 — 사이트가 바뀌어도 도구 스키마는 그대로여야 하기 때문입니다.

## 테스트

```powershell
pytest -q                                  # 전체 (22개)
pytest -q -m "not browser"                 # 브라우저 없이
pytest -q -m browser                       # Playwright end-to-end
ruff check . ; ruff format .
```

- `test_registry.py` — 스키마 자동 생성, 도구 실패가 예외가 아닌 데이터로 전달되는지
- `test_mocksite.py` — mock 시간표의 결정성
- `test_parity.py` — **Phase 1과 Phase 2가 모델에게 보여주는 tools 배열이 완전히 동일한지**
- `test_booking_flow.py` — LLM 없이 도구만으로 예약 전 과정 (실패 원인이 도구인지 모델인지 가르는 기준선)

## 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama 주소 |
| `OLLAMA_MODEL` | `qwen3.6:27b` | 사용 모델 |
| `THINK` | `false` | qwen3.6 thinking 모드 (켜면 느려짐) |
| `TARGET_SITE` | `mock` | `mock` \| `korail` |
| `HEADLESS` | `true` | 데모 녹화 시 `false` |
| `MAX_TOOL_ITERATIONS` | `8` | 에이전트 루프 상한 |

> Ollama 서버를 `OLLAMA_HOST=0.0.0.0:11434` 로 띄운 경우, 같은 환경변수를 클라이언트가
> 접속 주소로 읽으면 연결에 실패합니다. `config.py` 가 와일드카드 주소를 루프백으로
> 자동 정규화하므로 그대로 두어도 동작합니다.

모델명은 `OLLAMA_MODEL` 로만 바꿉니다. 코드에 모델명을 하드코딩하지 마세요.

## 실제 코레일 사용 (opt-in)

```powershell
# .env
TARGET_SITE=korail
KORAIL_ID=...      # 저장소에 커밋하지 마세요
KORAIL_PW=...
```

- 자동화 범위는 **예약(좌석 확보)까지**입니다. 결제·발권 도구는 제공하지 않습니다.
- **예약은 실제 좌석을 점유합니다.** 사용하지 않을 예약은 반드시 취소하세요.
- 반복 실행·상시 실행·매크로성 폴링을 하지 마세요.
- `tools/sites/korail.py` 의 셀렉터는 상용 사이트 구조에 의존하므로 **언제든 깨질 수 있고,
  동작이 보장되지 않습니다.** 사용 전 실사이트에서 검증하고, 깨지면 `describe_page` 로
  DOM을 확인해 `_CANDIDATES` 를 갱신하세요.

## 참고 — 원본 아이디어

[Deahyun/korail-booking-llm-agent](https://github.com/Deahyun/korail-booking-llm-agent)
— Selenium + `gemma3:27b` + Ubuntu 로 실제 코레일을 조작하는 컨셉입니다. 코드는 없고
[데모 영상](https://www.youtube.com/watch?v=vuokYXSmWLM)으로만 동작을 확인할 수 있습니다.

원본은 LLM 이 `TOOL_CALL(reserve_train_ticket):{...}` 문자열을 출력하면 스크립트가 이를 파싱해
고정된 Selenium 시나리오를 한 번 실행하는 **자체 텍스트 프로토콜** 방식입니다. 도구는 1개이고,
정보가 부족하면 LLM 이 사용자에게 되물어 2차 입력을 받습니다. 예약(좌석 확보)에서 멈추는
경계는 이 저장소와 같습니다.

이 저장소는 그 아이디어를 **Playwright + qwen3.6 + Windows 11** 로 다시 구현하면서,
텍스트 파싱 대신 **모델이 직접 도구를 고르는 에이전트 루프**와 **MCP 전환 단계**를 더한 것입니다.
나란히 두면 **"직접 파싱 → 네이티브 tool calling → MCP"** 세 세대를 한자리에서 볼 수 있습니다.

## 면책

도구 연동 기술을 설명하기 위한 실험용 예제입니다. 실제 서비스 용도가 아니며, 대상 사이트의
이용 약관 및 자동화 정책을 반드시 확인한 뒤 사용하세요. 이 코드로 발생한 결과에 대한 책임은
사용자에게 있습니다.

## 라이선스

MIT
