import asyncio
from types import SimpleNamespace

from main import build_registry


class FakeBrowser:
    async def search(self, query, max_results=None):
        return {"success": True, "query": query, "max_results": max_results}

    async def open_url(self, url):
        return {"success": True, "url": url}

    async def read_page(self):
        return {"success": True}

    async def click(self, target):
        return {"success": True, "target": target}


def test_browser_registry_adapts_mcp_argument_objects():
    config = SimpleNamespace(
        enabled_tools=["browser_search", "browser_open", "browser_read_page", "browser_click"],
        browser=SimpleNamespace(enabled=True),
        directories=SimpleNamespace(allowed_roots=["."], max_entries=10),
        commands=SimpleNamespace(allowed=[], timeout_seconds=1, max_output_chars=1000),
    )
    settings = SimpleNamespace(config=config)
    registry = build_registry(settings, FakeBrowser())
    search = asyncio.run(registry.execute("browser_search", {"query": "Python", "max_results": 3}))
    opened = asyncio.run(registry.execute("browser_open", {"url": "https://www.python.org"}))
    clicked = asyncio.run(registry.execute("browser_click", {"target": "Python"}))
    assert search["success"] is True and search["query"] == "Python" and search["max_results"] == 3
    assert opened["url"] == "https://www.python.org"
    assert clicked["target"] == "Python"


def test_registry_exposes_desktop_search_skills_and_task_status(tmp_path):
    config = SimpleNamespace(
        enabled_tools=["find_files", "list_skills", "get_task_status", "get_task_result", "cancel_task"],
        browser=SimpleNamespace(enabled=False),
        directories=SimpleNamespace(allowed_roots=[str(tmp_path)], max_entries=10),
        commands=SimpleNamespace(allowed=[], timeout_seconds=1, max_output_chars=1000),
        workspaces={},
    )
    settings = SimpleNamespace(config=config, project_dir=tmp_path)
    registry = build_registry(settings)
    assert registry.get_tool("find_files") is not None
    assert registry.get_tool("list_skills") is not None
    assert registry.get_tool("get_task_status") is not None
    assert registry.get_tool("get_task_result") is not None
    assert registry.get_tool("cancel_task") is not None


def test_registry_exposes_controlled_desktop_tools(tmp_path):
    config = SimpleNamespace(
        enabled_tools=["desktop_list_windows", "desktop_click", "desktop_type", "desktop_hotkey"],
        browser=SimpleNamespace(enabled=False),
        directories=SimpleNamespace(allowed_roots=[str(tmp_path)], max_entries=10),
        commands=SimpleNamespace(allowed=[], timeout_seconds=1, max_output_chars=1000),
        workspaces={},
        permissions=SimpleNamespace(profile="safe"),
    )
    settings = SimpleNamespace(config=config, project_dir=tmp_path)
    registry = build_registry(settings)
    assert all(registry.get_tool(name) is not None for name in config.enabled_tools)


def test_registry_exposes_screen_capture(tmp_path):
    config = SimpleNamespace(
        enabled_tools=["screen_capture"],
        browser=SimpleNamespace(enabled=False),
        directories=SimpleNamespace(allowed_roots=[str(tmp_path)], max_entries=10),
        commands=SimpleNamespace(allowed=[], timeout_seconds=1, max_output_chars=1000),
        workspaces={},
    )
    settings = SimpleNamespace(config=config, project_dir=tmp_path)
    registry = build_registry(settings)
    assert registry.get_tool("screen_capture") is not None
