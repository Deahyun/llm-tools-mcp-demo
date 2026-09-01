"""환경변수 기반 설정. 모델명/호스트를 코드에 하드코딩하지 않기 위한 단일 창구."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _normalize_http_path(raw: str) -> str:
    """MCP HTTP 엔드포인트 경로를 `/mcp` 형태로 정규화한다."""
    path = (raw or "").strip() or "/mcp"
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/mcp"


def _normalize_ollama_host(raw: str) -> str:
    """Ollama 접속 주소를 정규화한다.

    Ollama 서버는 보통 `OLLAMA_HOST=0.0.0.0:11434` 로 **바인딩 주소**를 설정합니다.
    같은 환경변수를 클라이언트가 **접속 주소**로 그대로 쓰면 연결에 실패하므로,
    와일드카드 주소를 루프백으로 바꾸고 스킴이 없으면 붙여 줍니다.
    """
    host = (raw or "").strip()
    if not host:
        return "http://127.0.0.1:11434"
    if "://" not in host:
        host = "http://" + host

    scheme, _, rest = host.partition("://")
    hostport = rest.rstrip("/")
    for wildcard in ("0.0.0.0", "[::]", "::"):
        if hostport == wildcard or hostport.startswith(wildcard + ":"):
            hostport = "127.0.0.1" + hostport[len(wildcard) :]
            break
    return f"{scheme}://{hostport}"


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    ollama_model: str
    think: bool
    target_site: str
    mock_site_url: str
    korail_url: str
    headless: bool
    browser_timeout_ms: int
    screenshot_dir: Path
    max_tool_iterations: int
    log_level: str
    mcp_transport: str
    mcp_http_host: str
    mcp_http_port: int
    mcp_http_path: str
    mcp_http_url: str

    @property
    def target_base_url(self) -> str:
        return self.korail_url if self.target_site == "korail" else self.mock_site_url

    @property
    def mcp_http_endpoint(self) -> str:
        """클라이언트가 접속할 MCP HTTP 주소.

        MCP_HTTP_URL 을 직접 주면 그것을 쓰고, 없으면 host/port/path 로 조립합니다.
        서버는 0.0.0.0 에 바인딩할 수 있지만 접속은 루프백으로 해야 하므로
        `_normalize_ollama_host` 와 같은 이유로 와일드카드를 127.0.0.1 로 바꿉니다.
        """
        if self.mcp_http_url:
            return self.mcp_http_url
        host = self.mcp_http_host
        if host in ("0.0.0.0", "::", "[::]"):
            host = "127.0.0.1"
        return f"http://{host}:{self.mcp_http_port}{self.mcp_http_path}"


def get_settings() -> Settings:
    return Settings(
        ollama_host=_normalize_ollama_host(os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.6:27b"),
        think=_env_bool("THINK", False),
        target_site=os.getenv("TARGET_SITE", "mock").strip().lower(),
        mock_site_url=os.getenv("MOCK_SITE_URL", "http://127.0.0.1:8765").rstrip("/"),
        korail_url=os.getenv("KORAIL_URL", "https://www.letskorail.com").rstrip("/"),
        headless=_env_bool("HEADLESS", True),
        browser_timeout_ms=_env_int("BROWSER_TIMEOUT_MS", 15000),
        screenshot_dir=PROJECT_ROOT / os.getenv("SCREENSHOT_DIR", "screenshots"),
        max_tool_iterations=_env_int("MAX_TOOL_ITERATIONS", 8),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        mcp_transport=os.getenv("MCP_TRANSPORT", "stdio").strip().lower(),
        mcp_http_host=os.getenv("MCP_HTTP_HOST", "127.0.0.1").strip(),
        mcp_http_port=_env_int("MCP_HTTP_PORT", 8931),
        mcp_http_path=_normalize_http_path(os.getenv("MCP_HTTP_PATH", "/mcp")),
        mcp_http_url=os.getenv("MCP_HTTP_URL", "").strip().rstrip("/"),
    )


settings = get_settings()


def setup_logging(level: str | None = None) -> None:
    """루트 로거 구성.

    MCP 서버는 stdout 으로 JSON-RPC 를 주고받으므로 로그는 반드시 stderr 로 나가야 합니다.
    logging 기본 StreamHandler 가 stderr 를 쓰므로 stream 을 바꾸지 마세요.
    """
    logging.basicConfig(
        level=getattr(logging, (level or settings.log_level), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Playwright / httpx 의 과도한 디버그 로그 억제
    for noisy in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
