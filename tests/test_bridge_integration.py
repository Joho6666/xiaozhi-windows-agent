import asyncio
import json

import pytest
import websockets

from agent.bridge import MCPBridge
from agent.connection import MCPConnection
from agent.protocol import make_result
from agent.registry import RiskLevel, Tool, ToolRegistry
from security.permissions import PermissionManager


@pytest.mark.asyncio
async def test_initialize_tools_call_and_ping_over_websocket():
    received_methods = []

    async def endpoint_handler(websocket):
        await websocket.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
        init_response = json.loads(await websocket.recv())
        received_methods.append("initialize")
        assert init_response["id"] == 1

        notification = json.loads(await websocket.recv())
        received_methods.append(notification["method"])
        await websocket.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        tools_response = json.loads(await websocket.recv())
        received_methods.append("tools/list")
        assert tools_response["id"] == 2

        await websocket.send(json.dumps({"jsonrpc": "2.0", "id": 90, "method": "ping", "params": {}}))
        await websocket.send(json.dumps({"jsonrpc": "2.0", "id": 91, "method": "tools/call", "params": {"name": "demo", "arguments": {}}}))
        ping_response = json.loads(await websocket.recv())
        call_response = json.loads(await websocket.recv())
        assert ping_response["id"] == 90
        assert call_response["id"] == 91
        assert json.loads(call_response["result"]["content"][0]["text"])["success"] is True

    async with websockets.serve(endpoint_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        connection = MCPConnection(f"ws://127.0.0.1:{port}")
        registry = ToolRegistry()
        registry.register(Tool("demo", "demo", {"type": "object"}, lambda _: {"success": True, "message": "ok"}, RiskLevel.LOW))
        bridge = MCPBridge(connection, registry, PermissionManager({"low": "auto", "medium": "deny", "high": "deny"}), [0.01])
        await connection.connect()
        await bridge.accept_initialize()
        tools_request = await connection.receive()
        await bridge._handle_message(tools_request)
        ping = await connection.receive()
        await bridge._handle_message(ping)
        call = await connection.receive()
        await bridge._handle_message(call)
        await connection.close()

    assert received_methods == ["initialize", "notifications/initialized", "tools/list"]


@pytest.mark.asyncio
async def test_bridge_reconnects_after_endpoint_disconnect():
    connection_count = 0
    connected_twice = asyncio.Event()

    async def endpoint_handler(websocket):
        nonlocal connection_count
        connection_count += 1
        current_connection = connection_count
        await websocket.send(json.dumps({"jsonrpc": "2.0", "id": current_connection, "method": "initialize", "params": {}}))
        init_response = json.loads(await websocket.recv())
        if current_connection == 1:
            await websocket.close()
            return
        assert init_response["id"] == current_connection
        notification = json.loads(await websocket.recv())
        assert notification["method"] == "notifications/initialized"
        await websocket.send(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}))
        tools_response = json.loads(await websocket.recv())
        assert tools_response["id"] == 3
        connected_twice.set()
        await websocket.close()

    async with websockets.serve(endpoint_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        connection = MCPConnection(f"ws://127.0.0.1:{port}")
        registry = ToolRegistry()
        permissions = PermissionManager({"low": "auto", "medium": "deny", "high": "deny"})
        bridge = MCPBridge(connection, registry, permissions, [0.01])
        task = asyncio.create_task(bridge.run())
        await asyncio.wait_for(connected_twice.wait(), timeout=2)
        await bridge.stop()
        await asyncio.wait_for(task, timeout=2)

    assert connection_count >= 2


@pytest.mark.asyncio
async def test_bridge_preserves_mcp_image_content_blocks():
    class FakeConnection:
        request_timeout = 1

        def __init__(self):
            self.sent = []

        async def send(self, message):
            self.sent.append(message)

    connection = FakeConnection()
    registry = ToolRegistry()
    registry.register(Tool("screen_capture", "screen", {}, lambda _: {"success": True, "tool": "screen_capture", "message": "captured", "content": [{"type": "image", "data": "abc", "mimeType": "image/jpeg"}]}, RiskLevel.HIGH))
    bridge = MCPBridge(connection, registry, PermissionManager({"low": "auto", "medium": "auto", "high": "auto"}), [1])
    await bridge._handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "screen_capture", "arguments": {}}})
    content = connection.sent[0]["result"]["content"]
    assert any(block["type"] == "image" for block in content)
    assert any(block["type"] == "text" for block in content)
