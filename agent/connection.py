"""Small WebSocket transport wrapper with reconnect-friendly behavior."""

from __future__ import annotations

import json
from typing import Any

import websockets

from .protocol import decode_message, encode_message


class MCPConnection:
    def __init__(self, endpoint: str, protocol_mode: str = "plain_jsonrpc", request_timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.protocol_mode = protocol_mode
        self.request_timeout = request_timeout
        self.websocket: Any = None
        self.session_id: str | None = None

    async def connect(self) -> None:
        self.websocket = await websockets.connect(self.endpoint, ping_interval=20, ping_timeout=20)

    async def close(self) -> None:
        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None

    async def send(self, message: dict[str, Any]) -> None:
        if self.websocket is None:
            raise ConnectionError("WebSocket is not connected")
        encoded = encode_message(message, self.protocol_mode, self.session_id)
        await self.websocket.send(json.dumps(encoded, ensure_ascii=False))

    async def receive(self) -> dict[str, Any]:
        if self.websocket is None:
            raise ConnectionError("WebSocket is not connected")
        raw = await self.websocket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        decoded, session_id = decode_message(json.loads(raw), self.protocol_mode)
        if session_id:
            self.session_id = session_id
        return decoded
