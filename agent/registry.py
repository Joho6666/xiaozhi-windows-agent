"""Extensible local tool registry."""

from __future__ import annotations

import inspect
import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


ToolHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    risk_level: RiskLevel
    category: str = "system"
    timeout: float = 30.0

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    register_tool = register

    def unregister_tool(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.definition() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.get_tool(name)
        if tool is None:
            raise KeyError(name)
        started = time.perf_counter()
        if inspect.iscoroutinefunction(tool.handler):
            result = await asyncio.wait_for(tool.handler(arguments), timeout=tool.timeout)
        else:
            result = await asyncio.wait_for(asyncio.to_thread(tool.handler, arguments), timeout=tool.timeout)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=tool.timeout)
        if not isinstance(result, dict):
            result = {"success": False, "message": "Tool returned an invalid result"}
        result.setdefault("success", True)
        result.setdefault("tool", name)
        result.setdefault("message", f"{name} completed")
        result.setdefault("duration_ms", int((time.perf_counter() - started) * 1000))
        return result

    def __len__(self) -> int:
        return len(self._tools)
