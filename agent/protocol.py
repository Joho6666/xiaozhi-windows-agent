"""JSON-RPC and XiaoZhi envelope protocol helpers."""

from __future__ import annotations

from typing import Any


def make_request(request_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def make_notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    return message


def make_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def encode_message(message: dict[str, Any], mode: str = "plain_jsonrpc", session_id: str | None = None) -> dict[str, Any]:
    if mode == "plain_jsonrpc":
        return message
    if mode == "xiaozhi_envelope":
        return {"session_id": session_id or "", "type": "mcp", "payload": message}
    raise ValueError(f"unsupported protocol mode: {mode}")


def decode_message(message: dict[str, Any], mode: str = "plain_jsonrpc") -> tuple[dict[str, Any], str | None]:
    if mode == "plain_jsonrpc":
        return message, None
    if mode == "xiaozhi_envelope":
        if message.get("type") != "mcp" or not isinstance(message.get("payload"), dict):
            raise ValueError("invalid XiaoZhi MCP envelope")
        return message["payload"], message.get("session_id")
    raise ValueError(f"unsupported protocol mode: {mode}")


def validate_jsonrpc(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ValueError("message is not a JSON-RPC 2.0 object")
    if "method" not in message and "result" not in message and "error" not in message:
        raise ValueError("JSON-RPC message has no method, result, or error")
    return message
