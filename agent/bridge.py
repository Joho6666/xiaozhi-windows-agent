"""MCP bridge lifecycle, request handling, and reconnect loop."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any

from .connection import MCPConnection
from .protocol import make_error, make_notification, make_request, make_result, validate_jsonrpc
from .registry import RiskLevel, ToolRegistry
from security.permissions import PermissionDecision, PermissionManager
from security.audit import redact

logger = logging.getLogger(__name__)


class MCPBridge:
    def __init__(self, connection: MCPConnection, registry: ToolRegistry, permissions: PermissionManager, reconnect_delays: list[float], shutdown_callbacks: list[Any] | None = None, audit_logger: Any | None = None) -> None:
        self.connection = connection
        self.registry = registry
        self.permissions = permissions
        self.reconnect_delays = reconnect_delays
        self._ids = itertools.count(1)
        self._stop = asyncio.Event()
        self.initialized = False
        self.shutdown_callbacks = shutdown_callbacks or []
        self.audit_logger = audit_logger

    async def stop(self) -> None:
        self._stop.set()
        await self.connection.close()
        for callback in self.shutdown_callbacks:
            result = callback()
            if hasattr(result, "__await__"):
                await result

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = next(self._ids)
        await self.connection.send(make_request(request_id, method, params))
        while True:
            message = validate_jsonrpc(await asyncio.wait_for(self.connection.receive(), self.connection.request_timeout))
            if message.get("id") != request_id:
                await self._handle_message(message)
                continue
            if "error" in message:
                raise RuntimeError(message["error"].get("message", "MCP request failed"))
            return message.get("result", {})

    async def initialize(self) -> None:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": False}, "sampling": {}},
                "clientInfo": {"name": "XiaoZhiWindowsAgentBridge", "version": "0.1.0"},
            },
        )
        logger.info("MCP initialized: %s", result.get("serverInfo", {}))
        await self.connection.send(make_notification("notifications/initialized"))
        tools_result = await self._request("tools/list", {})
        logger.info("Endpoint reports %d upstream tools", len(tools_result.get("tools", [])))
        self.initialized = True

    async def accept_initialize(self) -> None:
        """Act as the MCP server expected by the XiaoZhi cloud endpoint.

        The public XiaoZhi endpoint opens the socket and sends `initialize` to
        the local tool provider. It is therefore the opposite direction from
        a conventional MCP client connecting to a server.
        """
        while True:
            message = validate_jsonrpc(await asyncio.wait_for(self.connection.receive(), self.connection.request_timeout))
            if message.get("method") == "initialize":
                await self.connection.send(
                    make_result(
                        message.get("id"),
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "XiaoZhiWindowsAgentBridge", "version": "0.1.0"},
                        },
                    )
                )
                self.initialized = True
                await self.connection.send(make_notification("notifications/initialized"))
                logger.info("MCP server handshake completed")
                return
            await self._handle_message(message)

    async def _handle_tools_call(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        params = message.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            await self.connection.send(make_error(request_id, -32602, "tools/call requires params.name"))
            return
        name = params["name"]
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            await self.connection.send(make_error(request_id, -32602, "tools/call arguments must be an object"))
            return
        tool = self.registry.get_tool(name)
        if tool is None:
            await self.connection.send(make_error(request_id, -32601, f"Unknown tool: {name}"))
            return
        logger.info("USER tool call: %s %s", name, json.dumps(redact(arguments), ensure_ascii=False))
        decision = await self.permissions.check(tool.risk_level, f'{name}({json.dumps(redact(arguments), ensure_ascii=False)})')
        if decision is not PermissionDecision.ALLOW:
            if self.audit_logger:
                self.audit_logger.record(tool=name, workspace=arguments.get("workspace"), risk=tool.risk_level.value, approved=False, success=False, details={"message": "Permission denied"})
            await self.connection.send(make_result(request_id, {"content": [{"type": "text", "text": json.dumps({"success": False, "message": "Permission denied"})}], "isError": True}))
            return
        try:
            result = await self.registry.execute(name, arguments)
            logger.info("Tool result: %s success=%s message=%s", name, result.get("success"), result.get("message", ""))
            if self.audit_logger:
                self.audit_logger.record(tool=name, workspace=arguments.get("workspace"), risk=tool.risk_level.value, approved=True, success=bool(result.get("success")), details={"message": result.get("message", "")})
            payload = self._tool_payload(result)
            await self.connection.send(make_result(request_id, payload))
        except Exception as exc:  # tool failures must not kill the connection
            logger.exception("Tool execution failed: %s", name)
            if self.audit_logger:
                self.audit_logger.record(tool=name, workspace=arguments.get("workspace"), risk=tool.risk_level.value, approved=True, success=False, details={"message": str(exc)})
            await self.connection.send(make_result(request_id, {"content": [{"type": "text", "text": json.dumps({"success": False, "message": str(exc)})}], "isError": True}))

    @staticmethod
    def _tool_payload(result: dict[str, Any]) -> dict[str, Any]:
        """Encode text metadata plus optional MCP image/audio/resource blocks."""
        extra_content = result.get("content")
        metadata = {key: value for key, value in result.items() if key != "content"}
        content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(metadata, ensure_ascii=False)}]
        if isinstance(extra_content, list):
            content.extend(block for block in extra_content if isinstance(block, dict) and block.get("type") in {"image", "audio", "resource"})
        return {"content": content, "isError": not bool(result.get("success", False))}

    async def _handle_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method == "initialize":
            await self.connection.send(
                make_result(
                    message.get("id"),
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "XiaoZhiWindowsAgentBridge", "version": "0.1.0"},
                    },
                )
            )
            self.initialized = True
        elif method == "tools/list":
            await self.connection.send(make_result(message.get("id"), {"tools": self.registry.list_tools()}))
        elif method == "tools/call":
            await self._handle_tools_call(message)
        elif method == "ping":
            if "id" in message:
                await self.connection.send(make_result(message["id"], {}))
        elif method and method.startswith("notifications/"):
            logger.debug("MCP notification: %s", method)
        elif "id" in message and "result" in message:
            logger.debug("Unmatched MCP response id=%s", message["id"])

    async def run(self) -> None:
        delay_index = 0
        while not self._stop.is_set():
            try:
                logger.info("Connecting to XiaoZhi MCP endpoint")
                await self.connection.connect()
                await self.accept_initialize()
                delay_index = 0
                logger.info("Connected; registered %d local tools", len(self.registry))
                while not self._stop.is_set():
                    message = validate_jsonrpc(await self.connection.receive())
                    await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.initialized = False
                logger.warning("MCP connection stopped: %s", exc)
                await self.connection.close()
                if self._stop.is_set():
                    break
                delay = self.reconnect_delays[min(delay_index, len(self.reconnect_delays) - 1)]
                delay_index += 1
                logger.info("Reconnecting in %.1f seconds", delay)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
