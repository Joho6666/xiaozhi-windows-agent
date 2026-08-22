"""Small asyncio task manager for long-running local tools."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TaskHandler = Callable[[], Any]


@dataclass
class _TaskRecord:
    task_id: str
    name: str
    handler: TaskHandler = field(repr=False)
    timeout: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.QUEUED
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    asyncio_task: asyncio.Task[Any] | None = field(default=None, repr=False)


class TaskManager:
    """Run local work outside the MCP receive loop and expose stable status."""

    def __init__(self) -> None:
        self._tasks: dict[str, _TaskRecord] = {}

    def create_task(
        self,
        name: str,
        handler: TaskHandler,
        *,
        timeout: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:12]
        record = _TaskRecord(task_id, name, handler, timeout, metadata or {})
        self._tasks[task_id] = record
        record.asyncio_task = asyncio.create_task(self._run(record), name=f"xiaozhi-{name}-{task_id}")
        return self._public(record)

    async def _invoke(self, record: _TaskRecord) -> Any:
        if inspect.iscoroutinefunction(record.handler):
            value = await record.handler()
        else:
            value = await asyncio.to_thread(record.handler)
        if inspect.isawaitable(value):
            value = await value
        return value

    async def _run(self, record: _TaskRecord) -> None:
        record.status = TaskStatus.RUNNING
        record.started_at = time.time()
        try:
            value = self._invoke(record)
            result = await asyncio.wait_for(value, timeout=record.timeout) if record.timeout else await value
            record.result = result if isinstance(result, dict) else {"success": True, "data": result}
            record.status = TaskStatus.COMPLETED if record.result.get("success", True) else TaskStatus.FAILED
        except asyncio.CancelledError:
            record.status = TaskStatus.CANCELLED
            raise
        except asyncio.TimeoutError:
            record.status = TaskStatus.FAILED
            record.error = "Task timed out"
            record.result = {"success": False, "error_code": "TIMEOUT", "message": record.error}
        except Exception as exc:  # noqa: BLE001 - task errors must not kill the bridge
            record.status = TaskStatus.FAILED
            record.error = str(exc)
            record.result = {"success": False, "error_code": "TASK_FAILED", "message": "Task failed"}
        finally:
            record.completed_at = time.time()

    def _public(self, record: _TaskRecord) -> dict[str, Any]:
        response: dict[str, Any] = {
            "success": record.status is not TaskStatus.FAILED,
            "task_id": record.task_id,
            "name": record.name,
            "status": record.status.value,
            "created_at": record.created_at,
        }
        if record.started_at is not None:
            response["started_at"] = record.started_at
        if record.completed_at is not None:
            response["completed_at"] = record.completed_at
        if record.metadata:
            response["metadata"] = record.metadata
        if record.result is not None:
            response["result"] = record.result
        if record.error is not None:
            response["error"] = record.error
        return response

    def get_status(self, task_id: str) -> dict[str, Any]:
        record = self._tasks.get(task_id)
        if record is None:
            return {"success": False, "error_code": "TASK_NOT_FOUND", "message": "Task was not found"}
        return self._public(record)

    async def wait_for(self, task_id: str, timeout: float | None = None) -> dict[str, Any]:
        record = self._tasks.get(task_id)
        if record is None:
            return {"success": False, "error_code": "TASK_NOT_FOUND", "message": "Task was not found"}
        if record.asyncio_task is not None and not record.asyncio_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(record.asyncio_task), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        return self._public(record)

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        record = self._tasks.get(task_id)
        if record is None:
            return {"success": False, "error_code": "TASK_NOT_FOUND", "message": "Task was not found"}
        if record.asyncio_task is not None and not record.asyncio_task.done():
            record.asyncio_task.cancel()
            with suppress(asyncio.CancelledError):
                await record.asyncio_task
        return self._public(record)

    def list_tasks(self) -> list[dict[str, Any]]:
        return [self._public(record) for record in self._tasks.values()]

    async def shutdown(self) -> None:
        pending = [record.asyncio_task for record in self._tasks.values() if record.asyncio_task and not record.asyncio_task.done()]
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError):
                await task
