"""Scoped browser search and page-reading tools backed by Playwright."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from tools.windows_apps import _resolve_executable


class BrowserAutomation:
    def __init__(self, config: Any, project_dir: Path) -> None:
        self.config = config
        self.project_dir = project_dir
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = asyncio.Lock()

    async def _ensure_page(self):
        if self._page is not None and not self._page.is_closed():
            return self._page
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is not installed; run python -m pip install -r requirements.txt") from exc

        self._playwright = await async_playwright().start()
        executable = _resolve_executable("edge")
        launch_options: dict[str, Any] = {
            "headless": self.config.headless,
            "args": ["--disable-popup-blocking"],
        }
        if executable:
            launch_options["executable_path"] = executable
        self._browser = await self._playwright.chromium.launch(**launch_options)
        self._context = await self._browser.new_context(ignore_https_errors=False)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.config.page_timeout_seconds * 1000)
        return self._page

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def _validate_public_url(self, url: str) -> str:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url must be a non-empty string")
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise PermissionError("only public http(s) URLs are allowed")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
            raise PermissionError("local hostnames are not allowed")
        try:
            address = ipaddress.ip_address(hostname)
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                raise PermissionError("private or local IP addresses are not allowed")
        except ValueError:
            try:
                records = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
                for record in records:
                    resolved = ipaddress.ip_address(record[4][0])
                    if resolved.is_private or resolved.is_loopback or resolved.is_link_local or resolved.is_reserved:
                        raise PermissionError("URL resolves to a private or local address")
            except socket.gaierror as exc:
                raise ValueError(f"cannot resolve URL host: {hostname}") from exc

        allowed = [item.lower().lstrip("*.") for item in self.config.allowed_domains]
        if allowed and not any(hostname == domain or hostname.endswith("." + domain) for domain in allowed):
            raise PermissionError("domain is not in the browser allowlist")
        return url.strip()

    async def _navigate(self, url: str):
        safe_url = await self._validate_public_url(url)
        page = await self._ensure_page()
        await page.goto(safe_url, wait_until="domcontentloaded", timeout=self.config.page_timeout_seconds * 1000)
        return page

    @staticmethod
    async def _text(locator, limit: int) -> str:
        try:
            value = await locator.inner_text()
        except Exception:
            return ""
        return re.sub(r"\s+", " ", value).strip()[:limit]

    async def search(self, query: str, max_results: int | None = None) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return {"success": False, "message": "query must be a non-empty string"}
        if len(query) > 200:
            return {"success": False, "message": "query is too long"}
        engine = "https://www.google.com/search?q=" if self.config.search_engine == "google" else "https://www.bing.com/search?q="
        async with self._lock:
            page = await self._navigate(engine + quote_plus(query.strip()))
            results: list[dict[str, str]] = []
            limit = max_results or self.config.max_results
            # Search engines change wrapper classes frequently. Headings and
            # ordinary HTTP links are considerably more stable than result-card
            # class names, so collect both h2 and h3 result headings.
            headings = page.locator("h2, h3")
            for index in range(await headings.count()):
                if len(results) >= limit:
                    break
                heading = headings.nth(index)
                link = heading.locator("xpath=ancestor::a[1]")
                if await link.count() == 0:
                    link = heading.locator("a").first
                if await link.count() == 0:
                    continue
                title = await self._text(heading, 300)
                href = await link.get_attribute("href")
                if not href or not href.startswith(("http://", "https://")):
                    continue
                container = heading.locator("xpath=..")
                snippet = await self._text(container, 600)
                if not any(item["url"] == href for item in results):
                    results.append({"title": title, "url": href, "snippet": snippet})

            # Some localized layouts omit heading semantics. Use external
            # links as a conservative fallback, filtering search-engine links.
            if not results:
                links = page.locator("a[href^='http://'], a[href^='https://']")
                for index in range(await links.count()):
                    if len(results) >= limit:
                        break
                    link = links.nth(index)
                    href = await link.get_attribute("href")
                    title = await self._text(link, 300)
                    if not href or not title:
                        continue
                    host = (urlparse(href).hostname or "").lower()
                    if host.endswith(("bing.com", "google.com")):
                        continue
                    results.append({"title": title, "url": href, "snippet": title})
            return {"success": True, "query": query.strip(), "url": page.url, "results": results}

    async def open_url(self, url: str) -> dict[str, Any]:
        async with self._lock:
            page = await self._navigate(url)
            title = await page.title()
            body = await self._text(page.locator("body"), self.config.max_text_chars)
            return {"success": True, "url": page.url, "title": title[:300], "text": body}

    async def read_page(self) -> dict[str, Any]:
        async with self._lock:
            if self._page is None or self._page.is_closed():
                return {"success": False, "message": "No browser page is open"}
            return {
                "success": True,
                "url": self._page.url,
                "title": (await self._page.title())[:300],
                "text": await self._text(self._page.locator("body"), self.config.max_text_chars),
            }

    async def click(self, target: str) -> dict[str, Any]:
        """Click a visible link/button/text target on the current page only."""
        if not isinstance(target, str) or not target.strip() or len(target) > 200:
            return {"success": False, "message": "target must be a short non-empty string"}
        if any(token in target.lower() for token in ("javascript:", "file:", "data:", "<script", "/>")):
            return {"success": False, "message": "unsafe browser target"}
        async with self._lock:
            if self._page is None or self._page.is_closed():
                return {"success": False, "message": "No browser page is open"}
            page = self._page
            if target.startswith("css="):
                locator = page.locator(target[4:]).first
            elif target.startswith("text="):
                locator = page.get_by_text(target[5:], exact=True).first
            else:
                locator = page.get_by_role("link", name=target, exact=True).first
                if await locator.count() == 0:
                    locator = page.get_by_role("button", name=target, exact=True).first
                if await locator.count() == 0:
                    locator = page.get_by_text(target, exact=True).first
            if await locator.count() == 0:
                return {"success": False, "message": "Target was not found on the current page"}
            await locator.click(timeout=self.config.page_timeout_seconds * 1000)
            await page.wait_for_load_state("domcontentloaded", timeout=self.config.page_timeout_seconds * 1000)
            return {"success": True, "url": page.url, "title": (await page.title())[:300]}


BROWSER_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
    },
    "required": ["query"],
    "additionalProperties": False,
}

BROWSER_OPEN_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string", "description": "Public http(s) URL"}},
    "required": ["url"],
    "additionalProperties": False,
}

BROWSER_READ_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}

BROWSER_CLICK_SCHEMA = {
    "type": "object",
    "properties": {"target": {"type": "string", "description": "Visible link/button text, text=..., or css=... selector"}},
    "required": ["target"],
    "additionalProperties": False,
}
