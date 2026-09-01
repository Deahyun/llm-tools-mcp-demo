# CLAUDE.md

이 파일은 Claude Code(claude.ai/code)가 이 저장소에서 작업할 때 참고하는 지침서입니다.

## 프로젝트 개요

**로컬 LLM으로 브라우저를 조작하는 에이전트 데모.** 자연어 기차 예매 요청을 로컬 LLM이 해석하고, LLM이 스스로 도구(tool)를 호출해 Playwright로 실제 브라우저를 조작합니다.

핵심 목적은 "동일한 기능을 **두 가지 도구 연동 방식**으로 구현하고 비교하는 것"입니다. GitHub에 공개하는 **기술 예제이자 작업 기록**이며, 독자가 가져갈 것은 도구 설계 방법과 MCP 전환에서 무엇이 바뀌고 무엇이 그대로인지입니다.

기차 예약은 소재입니다 — "여러 단계에 걸쳐 상태가 이어지는 도구"라는 조건을 만족해서 골랐습니다. 문서가 예매 서비스 기능 소개로 흐르지 않게 하되, 브라우저 자동화는 이 데모의 본체이므로 축소하지도 마세요.

| 단계 | 방식 | 진입점 |
|------|------|--------|
| Phase 1 | **Native Tools** — Ollama function calling(`tools=[...]`)으로 직접 호출 | `src/toolsdemo/agent_tools.py` |
| Phase 2 | **MCP** — 동일 도구를 MCP 서버로 노출하고 MCP 클라이언트 경유로 호출 | `src/toolsdemo/mcp_/client_agent.py` |

두 경로는 **도구 구현체를 공유**합니다. 도구 로직은 `src/toolsdemo/tools/` 한 곳에만 존재하고, Phase 1/2는 그것을 감싸는 어댑터일 뿐입니다. 이 원칙을 깨지 마세요 — 로직이 양쪽에 복사되면 데모의 의미가 사라집니다. MCP 전환으로 무엇이 바뀌고 무엇이 그대로인지 보여주는 게 이 저장소의 존재 이유입니다.

### 레퍼런스 대비 변경 사항

원본 아이디어: https://github.com/Deahyun/korail-booking-llm-agent (README만 존재하는 컨셉 저장소, 코드 없음)

원본의 실제 동작은 **데모 영상으로만** 확인할 수 있습니다:
https://www.youtube.com/watch?v=vuokYXSmWLM (51초, 무음). 아래 "원본" 열은 추측이 아니라
그 영상 화면에서 직접 읽어낸 사실입니다. 수정할 때는 영상을 다시 확인하세요.

| 항목 | 원본 | 이 프로젝트 |
|------|------|-------------|
| 브라우저 자동화 | Selenium | **Playwright (async, Chromium)** |
| LLM 모델 | `gemma3:27b` (미리 `ollama run` 으로 상주) | **qwen3.6:27b** (tools/vision/thinking) |
| OS | Ubuntu 20.04 | **Windows 11 네이티브** |
| 도구 연동 | LLM 이 `TOOL_CALL(name):{json}` 문자열을 출력하면 스크립트가 파싱하는 **자체 텍스트 프로토콜** | **Native tool calling → MCP** 2단계 |
| 도구 개수 | 1개 (`reserve_train_ticket`, 인자 3개) | 7개. 무엇을 언제 부를지 모델이 결정 |
| 제어 흐름 | 1회 파싱 후 **고정 시나리오** 실행 | **에이전트 루프** (tool_calls 가 없을 때까지 반복) |
| 정보가 부족할 때 | LLM 이 사용자에게 되묻고 2차 입력을 받음 | `get_today` 등으로 스스로 해석 |
| 대상 사이트 | 실제 코레일 (**로그인된 세션 전제**) | **로컬 mock 사이트(기본)** + 실제 코레일(opt-in) |
| 자동화 범위 | 예약(좌석 확보)까지. `결제하기` 미클릭 | 동일. 단 **결제 도구를 만들지 않아 설계로 강제** |

> 자동화 범위는 원본과 이 프로젝트가 **같습니다**. 영상에서도 좌석(KTX 007, 10호차 11A)만
> 확보하고 결제기한 10분을 남긴 채 끝납니다. 차이는 범위가 아니라 **강제력**입니다 — 원본은
> 결제 도구가 없어 멈춘 것에 가깝고, 이 저장소는 `allows_payment=False` 와 "결제 도구 부재"를
> 설계 원칙으로 못박습니다. 이 행을 "이 프로젝트가 범위를 좁혔다"로 되돌리지 마세요.

## 실행 환경 (중요)

**모든 것을 Windows 11 네이티브에서 실행합니다. WSL을 사용하지 마세요.**

WSL(Ubuntu 22.04/24.04)에도 ollama가 설치되어 있지만 버전이 낮고(0.13.1) 모델이 없으며, 11434 포트를 점유해 혼란을 유발합니다. WSL 안에서 `localhost:11434`를 호출하면 Windows가 아니라 빈 WSL ollama가 응답합니다. **WSL 경로로 우회하지 말고 Windows에서 직접 실행하세요.**

### 확인된 환경 (2026-08-25 기준)

- OS: Windows 11 Pro 26200
- GPU: **NVIDIA RTX 3090 24GB** (드라이버 591.86) — 27B Q4_K_M 모델이 VRAM에 온전히 적재됨
- Python: `3.10.11` (`C:\Users\duckking\AppData\Local\Programs\Python\Python310\python.exe`)
  → **Python 3.10 문법 상한**을 지킵니다. 3.11+ 전용 기능(`ExceptionGroup`, `tomllib`, `typing.Self`) 금지.
- Ollama: **0.32.15** 네이티브, `OLLAMA_HOST=0.0.0.0:11434` (전체 인터페이스 리슨)
- 보유 모델: `qwen3.6:27b` (17GB, tools/vision/thinking), `gpt-oss:20b` (13GB, tools/thinking)
- Playwright Chromium 151.0.7922.34 설치 완료, 가상환경은 `.venv`

Phase 1 / Phase 2 모두 `qwen3.6:27b` 로 end-to-end 검증 완료 (같은 질의 → 같은 예약번호,
도구 호출 5회 / 반복 6회). 27B 첫 로딩에 **약 70초**가 걸리므로 첫 실행의 타임아웃을 짧게 잡지 마세요.

셸은 **PowerShell** 기준입니다. `&&` 체이닝이 안 되므로 `;` 또는 `if ($?) { }` 를 씁니다.

## 자주 쓰는 명령

```powershell
# 최초 1회 셋업 (venv + 의존성 + playwright chromium)
.\scripts\setup.ps1

# 개발 셸
.\.venv\Scripts\Activate.ps1

# --- 실행 ---
# 1) Mock 예매 사이트 (별도 터미널, http://127.0.0.1:8765)
python -m toolsdemo.mocksite.server

# 2) Phase 1: Native tool calling 에이전트
python -m toolsdemo.agent_tools "내일 오전 9시쯤 서울에서 부산 가는 KTX 예매해줘"

# 3) Phase 2: MCP 클라이언트 에이전트 (같은 질의 → 같은 결과여야 함)
python -m toolsdemo.mcp_.client_agent "내일 오전 9시쯤 서울에서 부산 가는 KTX 예매해줘"

# MCP 서버 단독 기동 (stdio) — 보통 클라이언트가 자동 기동하므로 디버깅용
python -m toolsdemo.mcp_.server

# --- 검증 ---
pytest -q                          # 전체
pytest -q -m "not llm"             # LLM 불필요한 빠른 확인
pytest -q -m "not llm and not browser"
ruff check . ; ruff format .
```

### Ollama 점검

```powershell
ollama list          # 보유 모델
ollama ps            # 현재 VRAM 에 적재된 모델
curl.exe -s http://127.0.0.1:11434/api/tags
```

## 아키텍처

```
사용자 자연어
      │
      ▼
┌────────────────────────────────────────────────────────────┐
│  Agent Loop (Phase 1: agent_tools / Phase 2: client_agent)  │
│  - ollama.chat(model=qwen3.6:27b, tools=[...], think=False) │
│  - tool_calls 수신 → 실행 → 결과를 messages 에 append        │
│  - tool_calls 가 없을 때까지 반복 (MAX_TOOL_ITERATIONS 상한)  │
└────────────────────────────────────────────────────────────┘
      │ (Phase 1) 직접 호출          │ (Phase 2) MCP stdio
      ▼                              ▼
┌──────────────────┐         ┌──────────────────┐
│ tools/registry   │◀────────│ mcp_/server.py   │
│  (단일 진실 원천) │         │  MCP 서버 래퍼    │
└──────────────────┘         └──────────────────┘
      │
      ▼
┌────────────────────────────────────────────────────────────┐
│  tools/booking.py  — 예매 도메인 도구 구현                   │
│  tools/browser.py  — Playwright 세션 lifecycle (싱글턴)       │
│  tools/sites/*.py  — 사이트별 셀렉터·플로우 어댑터             │
└────────────────────────────────────────────────────────────┘
      │
      ▼
  Mock 사이트(기본)  /  실제 코레일(opt-in)
```

### 디렉터리

```
src/toolsdemo/
  config.py          환경변수 → 설정 객체 (모델명, ollama host, 타깃 사이트, headless ...)
  schemas.py         Pydantic 모델 (TrainOption, BookingResult ...)
  llm/
    ollama_client.py Ollama chat 래퍼 + tool-calling 루프 (Phase 1/2 공용)
  tools/
    registry.py      @tool 데코레이터. 타입힌트 + docstring → JSON Schema 자동 생성
    booking.py       search_trains / select_train / fill_passenger / confirm_booking ...
    browser.py       Playwright 브라우저 컨텍스트 lifecycle
    sites/
      base.py        SiteAdapter 인터페이스 (셀렉터/플로우 추상화)
      mock.py        로컬 mock 사이트 어댑터
      korail.py      실제 코레일 어댑터 (opt-in, 예약까지. 결제 없음)
  agent_tools.py     Phase 1 진입점
  mcp_/
    server.py        Phase 2: registry 를 MCP tool 로 노출 (stdio)
    client_agent.py  Phase 2: MCP 클라이언트 + Ollama 에이전트 루프
  mocksite/
    server.py        FastAPI 기반 코레일 유사 mock 예매 사이트
    templates/       조회/결과/예매/완료 페이지
scripts/             setup.ps1, run_*.ps1
tests/
docs/                Phase 1 vs Phase 2 비교 문서
```

> 패키지명이 `mcp_` 인 이유: MCP 공식 SDK 패키지명이 `mcp` 라서 이름 충돌을 피하기 위함입니다. 바꾸지 마세요.

## 코드 규칙

- **도구는 `registry.py` 의 `@tool` 데코레이터로만 등록합니다.** JSON Schema를 손으로 쓰지 마세요 — 타입 힌트와 docstring에서 생성합니다. 새 도구를 추가하면 Phase 1과 MCP 양쪽에 자동 노출되어야 합니다.
- **도구 함수는 async 이고 항상 직렬화 가능한 dict 를 반환합니다.** 예외를 던지지 말고 `{"ok": False, "error": "..."}` 형태로 반환하세요. LLM이 읽고 스스로 복구해야 합니다.
- **docstring이 곧 프롬프트입니다.** 도구 설명과 인자 설명은 LLM이 읽는 유일한 사용 설명서입니다. 인자 형식(예: 날짜는 `YYYY-MM-DD`, 시간은 `HH:MM`)을 반드시 명시하세요.
- **셀렉터는 어댑터에만 둡니다.** `booking.py` 에 CSS 셀렉터가 등장하면 잘못된 설계입니다. 사이트별 차이는 `tools/sites/*.py` 에서 흡수합니다.
- Playwright는 `page.get_by_role()` / `get_by_label()` 우선, XPath는 최후 수단.
- 브라우저는 프로세스당 하나의 세션을 재사용합니다(`browser.py` 싱글턴). 도구 호출마다 새로 띄우지 마세요.
- 로깅은 `logging` 모듈 사용. **도구 호출/응답은 항상 INFO 레벨로 남깁니다** — 데모에서 이 로그가 곧 설명 자료입니다.
- Windows 경로는 `pathlib.Path` 로만 다룹니다. 문자열 슬래시 조립 금지.

## LLM 관련 주의사항

- **모델 전환은 `OLLAMA_MODEL` 환경변수로만.** 코드에 모델명을 하드코딩하지 마세요.
  - `qwen3.6:27b` — **기본값**. 이미 로컬에 존재하며 tools/vision/thinking 지원.
  - `gpt-oss:20b` — 대안. tools 지원, 더 가벼움.
  - `qwen3.8:27b` — 최신 세대. 쓰려면 `ollama pull qwen3.8:27b` (18GB) 선행 필요.
  - 주의: `qwen3.6` / `qwen3.8` 은 **모델 세대명**이지 파라미터 크기가 아닙니다. `qwen3:8b` 같은 구세대 태그와 혼동하지 마세요.
- qwen3.6/3.8은 thinking이 기본 ON입니다. 도구 호출 지연을 줄이려면 `think=False` 를 넘깁니다. **기본값 `think=False`**, 필요 시 `THINK=true` 로 켭니다.
- `temperature=0` 고정. 파라미터 파싱에 창의성은 필요 없습니다.
- 27B 모델의 첫 로딩은 수십 초 걸립니다. 타임아웃을 짧게 잡지 마세요. `ollama ps` 로 적재 여부를 먼저 확인하세요.
- 모델이 도구를 호출하지 않고 자연어로만 답하면, 시스템 프롬프트가 아니라 **도구 docstring**을 먼저 의심하세요.
- 에이전트 루프 최대 반복은 `MAX_TOOL_ITERATIONS`(기본 8)로 제한합니다. 무한 루프 방지.
- **`OLLAMA_HOST` 함정**: 이 PC의 시스템 환경변수는 `OLLAMA_HOST=0.0.0.0:11434` 입니다. 이건 서버의
  *바인딩* 주소인데 클라이언트가 *접속* 주소로 그대로 읽으면 `ConnectionError` 가 납니다.
  `config._normalize_ollama_host()` 가 와일드카드를 루프백으로 바꿔 주므로 그대로 두면 됩니다.
  이 정규화를 지우지 마세요.

## MCP SDK 버전 (중요)

설치된 SDK는 **`mcp` 2.x** 이며 1.x와 API가 다릅니다. 웹의 1.x 예제를 붙여넣으면 동작하지 않습니다.

| | 1.x | 2.x (이 저장소) |
|---|---|---|
| 서버 핸들러 | `@server.list_tools()` 데코레이터 | `Server(on_list_tools=..., on_call_tool=...)` |
| Tool 스키마 필드 | `inputSchema=` | `input_schema=` |
| 핸들러 반환 | `list[Tool]` / `list[TextContent]` | `ListToolsResult` / `CallToolResult` |
| 클라이언트 | `stdio_client()` + `ClientSession` | `Client(StdioServerParameters(...))` |

- **`CallToolResult.is_error` 를 쓰지 마세요.** 도구 실패는 `{"ok": false, "error": ...}` 페이로드로만
  전달합니다. Phase 1의 동작과 정확히 같아야 하며, `test_parity.py` 가 이를 강제합니다.

## 자동화 범위 경계 (반드시 준수)

**자동화는 "예약(좌석 확보)"까지. 결제와 발권은 사람이 합니다.**

```
조회 → 열차 선택 → 예약자 정보 → 예약 확정(좌석 확보)  │  결제 → 발권
└─────────────── 에이전트가 자동화 ───────────────┘  └── 사람이 직접 ──┘
```

- **결제를 수행하는 도구를 만들지 마세요.** 도구가 없어야 LLM이 시도조차 하지 않습니다.
  `confirm_booking` 은 좌석 확보까지만 하고, 예약번호와 결제 기한을 돌려주며 끝납니다.
- mock 사이트도 같은 경계를 모델링합니다 — 완료 화면은 "예약 완료(결제 대기)"이며
  결제 버튼이 존재하지 않습니다. 이 대칭을 유지하세요.
- 어댑터의 `allows_confirm` 은 예약 확정 허용 여부, `allows_payment` 는 항상 `False` 입니다.

### 타깃별 정책

- **`TARGET_SITE=mock` (기본)** — 로컬 mock 사이트. 테스트/CI/데모 녹화는 여기서 완결되어야 합니다.
- **`TARGET_SITE=korail` (opt-in)** — 실제 코레일. 예약까지 자동화하되:
  - 로그인이 필요합니다. 자격증명은 코드/저장소에 넣지 않고 `.env` 의 `KORAIL_ID` / `KORAIL_PW`
    에서만 읽습니다. 미설정 시 `HEADLESS=false` 로 사람이 직접 로그인하는 경로를 안내합니다.
  - **예약은 좌석을 실제로 점유합니다.** 데모 후 사용하지 않을 예약은 반드시 취소하세요.
    테스트를 반복 실행하지 말고, 상시 실행/스케줄링하지 마세요.
  - 요청 간격을 두고, 매크로성 반복 폴링·재시도 루프를 만들지 않습니다.
  - `korail.py` 의 셀렉터는 상용 사이트 구조에 의존하므로 **데모 전 실사이트에서 한 번 검증**하세요.
    깨졌을 때는 `describe_page` 로 DOM을 확인하고 `_CANDIDATES` 만 갱신합니다.
- 실 사이트 자동화 코드를 추가·수정할 때는 README의 면책 문구를 함께 갱신하세요.

## 환경변수

`.env.example` 참고.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama 엔드포인트 |
| `OLLAMA_MODEL` | `qwen3.6:27b` | 사용 모델 |
| `THINK` | `false` | qwen3.6 thinking 모드 |
| `TARGET_SITE` | `mock` | `mock` \| `korail` |
| `MOCK_SITE_URL` | `http://127.0.0.1:8765` | mock 사이트 주소 |
| `HEADLESS` | `true` | Playwright headless 여부 (데모 녹화 시 `false`) |
| `MAX_TOOL_ITERATIONS` | `8` | 에이전트 루프 상한 |
| `LOG_LEVEL` | `INFO` | 로깅 레벨 |

## 커밋 / 공개 저장소 규칙

이 저장소는 **도구 연동 / MCP 기술 예제**로 GitHub에 공개합니다. 문서의 초점은 "로컬 LLM이 도구를 호출해 브라우저를 조작하는 방법"과 "그 도구 연동을 native → MCP 로 옮길 때의 차이"이며, 예매 서비스 기능 자체가 아닙니다.

- README의 **실전 노트** 절이 이 저장소의 핵심 가치입니다. 도구 설계에서 시행착오를 겪었다면 그 항목을 추가하세요 — 겪은 함정과 그 이유를 남기는 것이 코드보다 오래 갑니다.
- `.env`, 로그인 정보, 스크린샷 속 개인정보, `screenshots/`, `.venv/`, `traces/` 커밋 금지 (`.gitignore` 확인).
- 커밋 메시지 접두사로 어느 Phase의 변경인지 표시: `phase1:`, `phase2:`, `mock:`, `docs:`, `chore:`.
- Phase 1 기능을 추가했다면 Phase 2에서도 동일 동작하는지 확인 후 커밋합니다 (`tests/test_parity.py`).
- 사용자가 명시적으로 요청하기 전에는 커밋/푸시하지 마세요.

## 작업 시 체크리스트

새 도구를 추가할 때:
1. `tools/booking.py` 에 async 함수 + `@tool` 데코레이터 + 명확한 docstring
2. mock 사이트 어댑터에 대응 플로우 구현
3. `pytest tests/test_tools.py` — LLM 없이 도구 단독 동작 검증
4. Phase 1 실행 → Phase 2 실행 → 결과 동일 확인
5. README의 도구 목록 표 갱신
