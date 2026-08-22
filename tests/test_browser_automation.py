import asyncio
from types import SimpleNamespace

import pytest

from tools.browser_automation import BrowserAutomation


def make_browser():
    config = SimpleNamespace(
        headless=True,
        search_engine="bing",
        page_timeout_seconds=5,
        max_results=5,
        max_text_chars=1000,
        allowed_domains=[],
    )
    return BrowserAutomation(config, __import__("pathlib").Path.cwd())


def test_browser_rejects_local_and_non_http_urls():
    browser = make_browser()
    for url in ("file:///C:/secret.txt", "javascript:alert(1)", "http://localhost:8000", "http://127.0.0.1"):
        with pytest.raises(PermissionError):
            asyncio.run(browser._validate_public_url(url))


def test_browser_rejects_private_ip():
    browser = make_browser()
    with pytest.raises(PermissionError):
        asyncio.run(browser._validate_public_url("http://192.168.1.1"))
