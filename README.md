# ToolsDemo — 로컬 LLM으로 브라우저를 조작하는 에이전트 (Tools → MCP)

자연어 기차 예약 요청을 **로컬 LLM(Ollama · qwen3.6)** 이 해석하고, LLM이 스스로 도구를 호출해
**Playwright** 로 브라우저를 자동 조작하는 데모입니다.

핵심은 **같은 기능을 두 가지 도구 연동 방식으로 구현하고 비교하는 것** 입니다.

| | Phase 1 | Phase 2 |
|---|---|---|
| 방식 | Ollama **native tool calling** | **MCP** (Model Context Protocol) |
| 도구 스키마 출처 | 프로세스 내부 registry | MCP 서버의 `list_tools()` |
| 도구 실행 | 함수 직접 호출 | MCP `call_tool()` (stdio, 별도 프로세스) |
| 진입점 | `python -m toolsdemo.agent_tools` | `python -m toolsdemo.mcp_.client_agent` |

> 두 Phase는 **도구 구현체와 에이전트 루프를 100% 공유**합니다. 바뀌는 것은 도구를
> *조달하는 경로*뿐이며, 같은 질의는 같은 결과를 냅니다 (아래 [실행 결과](#실행-결과) 참고).

원본 아이디어: [Deahyun/korail-booking-llm-agent](https://github.com/Deahyun/korail-booking-llm-agent)
(Selenium + gemma3 + Ubuntu 컨셉). 이 저장소는 이를 **Playwright + qwen3.6 + Windows 11**
로 다시 구현하고, 여기에 **MCP 전환 단계**를 추가한 것입니다.

---

## 자동화 범위 — 예약까지, 결제는 사람이

```
조회 → 열차 선택 → 예약자 정보 → 예약 확정(좌석 확보)  │  결제 → 발권
└──────────────── 에이전트가 자동화 ───────────────┘  └── 사람이 직접 ──┘
```

**결제를 수행하는 도구는 아예 존재하지 않습니다.** 에이전트는 좌석을 확보하고 예약번호와
결제 기한을 돌려준 뒤 사람에게 넘깁니다. mock 사이트도 동일한 경계를 모델링합니다.

---

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

도구는 `src/toolsdemo/tools/booking.py` 에 `@tool` 데코레이터로 한 번만 등록하면
타입 힌트와 docstring에서 JSON Schema가 자동 생성되어 **Phase 1과 MCP 양쪽에 동시에 노출**됩니다.

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

## 면책

데모 목적의 실험용 프로젝트입니다. 실제 서비스 용도가 아니며, 대상 사이트의 이용 약관 및
자동화 정책을 반드시 확인한 뒤 사용하세요. 이 코드로 발생한 결과에 대한 책임은 사용자에게 있습니다.

## 라이선스

MIT
