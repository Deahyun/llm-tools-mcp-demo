"""Phase 2 (변형) — 같은 MCP 서버를 **Streamable HTTP** 로 노출한다.

stdio 판(`server.py`)과 다른 것은 **트랜스포트뿐**입니다. 핸들러(`on_list_tools` /
`on_call_tool`)도, 도구 구현도, registry 도 전부 그대로 재사용합니다. 새 도구를 추가해도
이 파일은 손댈 필요가 없습니다.

    python -m toolsdemo.mcp_.http_server          # 기본 http://127.0.0.1:8931/mcp

클라이언트는 URL 만 있으면 붙습니다.

    $env:MCP_TRANSPORT="http"
    python -m toolsdemo.mcp_.client_agent "내일 오전 9시쯤 서울에서 부산 가는 기차 예약해줘"

stdio 와의 차이:

  * stdio 는 클라이언트가 서버를 **자식 프로세스로 직접 띄웁니다.** 서버를 미리 켜 둘
    필요가 없고, 클라이언트가 끝나면 서버도 함께 사라집니다.
  * HTTP 는 서버를 **먼저 띄워 두고** 여러 클라이언트가 접속합니다. 로컬 데모에서
    "서버가 살아 있는 상태"를 보여주거나, 브라우저 세션을 여러 실행에 걸쳐 재사용하거나,
    다른 머신/다른 언어의 클라이언트를 붙일 때 유용합니다.
  * stdout 금지 규칙은 HTTP 에서는 해당하지 않습니다(프로토콜이 소켓으로 갑니다).
    그래도 로그는 stdio 판과 동일하게 `logging` 으로 남깁니다.

주의: 인증이 없는 서버입니다. **로컬 테스트/데모 전용**이며 기본 바인딩은 루프백입니다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import uvicorn

from ..config import settings, setup_logging
from ..tools.browser import close_browser
from .server import SERVER_NAME, server

if TYPE_CHECKING:  # pragma: no cover - 타입 힌트 전용
    from starlette.applications import Starlette

logger = logging.getLogger(__name__)


def _attach_browser_cleanup(app: Starlette) -> None:
    """서버가 내려갈 때 Playwright 브라우저도 정리한다.

    SDK 가 만들어 준 Starlette 앱은 이미 자체 lifespan(세션 매니저 구동)을 갖고 있어
    `on_shutdown` 을 추가해도 실행되지 않습니다. 그래서 기존 lifespan 을 감싸고
    빠져나올 때 `close_browser()` 를 부릅니다. stdio 판 `serve()` 의 finally 와 같은 역할입니다.
    """
    base_lifespan = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(app_):
        async with base_lifespan(app_):
            try:
                yield
            finally:
                await close_browser()

    app.router.lifespan_context = lifespan


def build_app() -> Starlette:
    """registry 를 그대로 노출하는 Streamable HTTP ASGI 앱을 만든다."""
    app = server.streamable_http_app(
        streamable_http_path=settings.mcp_http_path,
        host=settings.mcp_http_host,
    )
    _attach_browser_cleanup(app)
    return app


def serve() -> None:
    logger.info(
        "[mcp] %s 시작 (streamable http) — http://%s:%d%s",
        SERVER_NAME,
        settings.mcp_http_host,
        settings.mcp_http_port,
        settings.mcp_http_path,
    )
    uvicorn.run(
        build_app(),
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    setup_logging()
    try:
        serve()
    except KeyboardInterrupt:  # pragma: no cover - 사람이 Ctrl+C 로 종료
        logger.info("[mcp] %s 종료", SERVER_NAME)
        with contextlib.suppress(Exception):
            asyncio.run(close_browser())


if __name__ == "__main__":
    main()
