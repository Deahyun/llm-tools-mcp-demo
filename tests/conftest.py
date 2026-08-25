"""공용 픽스처 — mock 사이트 서버 기동."""

from __future__ import annotations

import socket
import threading
import time
from urllib.parse import urlparse

import pytest

from toolsdemo.config import settings


def _reachable(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def mock_server():
    """MOCK_SITE_URL 에 mock 사이트가 떠 있게 보장한다.

    이미 떠 있으면 그대로 재사용하고, 없으면 백그라운드 스레드로 띄운다.
    """
    parsed = urlparse(settings.mock_site_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765

    if _reachable(host, port):
        yield settings.mock_site_url
        return

    import uvicorn

    from toolsdemo.mocksite.server import app

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline and not _reachable(host, port):
        time.sleep(0.2)
    if not _reachable(host, port):
        server.should_exit = True
        pytest.skip(f"mock 사이트를 {host}:{port} 에 띄우지 못했습니다.")

    yield settings.mock_site_url

    server.should_exit = True
    thread.join(timeout=5)
