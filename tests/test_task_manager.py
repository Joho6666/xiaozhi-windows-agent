import asyncio

import pytest

from agent.tasks import TaskManager, TaskStatus


@pytest.mark.asyncio
async def test_task_manager_runs_and_returns_result():
    manager = TaskManager()

    async def work():
        await asyncio.sleep(0)
        return {"success": True, "message": "finished"}

    created = manager.create_task("demo", work)
    assert created["status"] == TaskStatus.QUEUED.value
    completed = await manager.wait_for(created["task_id"], timeout=1)
    assert completed["status"] == TaskStatus.COMPLETED.value
    assert completed["result"]["message"] == "finished"


@pytest.mark.asyncio
async def test_task_manager_can_cancel_running_task():
    manager = TaskManager()
    started = asyncio.Event()

    async def work():
        started.set()
        await asyncio.sleep(10)

    created = manager.create_task("slow", work)
    await asyncio.wait_for(started.wait(), timeout=1)
    cancelled = await manager.cancel_task(created["task_id"])
    assert cancelled["status"] == TaskStatus.CANCELLED.value
    assert manager.get_status(created["task_id"])["status"] == TaskStatus.CANCELLED.value


def test_task_manager_rejects_unknown_task():
    manager = TaskManager()
    result = manager.get_status("missing")
    assert result["success"] is False
    assert result["error_code"] == "TASK_NOT_FOUND"
