import pytest
from pathlib import Path
from agent.tasks import TaskManager
from agent.workspaces import WorkspaceManager
from tools.agent_dispatcher import AgentDispatcher


@pytest.mark.asyncio
async def test_agent_dispatcher_dispatches_codex_task(monkeypatch, tmp_path):
    calls = []

    class FakeCompleted:
        returncode = 0
        stdout = "Codex completed successfully\n"
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeCompleted()

    monkeypatch.setattr("tools.agent_dispatcher.shutil.which", lambda name: f"C:/bin/{name}.cmd")
    monkeypatch.setattr("tools.agent_dispatcher.subprocess.run", fake_run)

    workspaces = WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd())
    task_manager = TaskManager()
    dispatcher = AgentDispatcher(workspaces, task_manager)

    res = dispatcher.dispatch({
        "agent_type": "codex",
        "task": "Add Wi-Fi reconnect handler",
        "workspace": "esp32",
        "mode": "modify",
    })

    assert res["success"] is True
    assert res["status"] == "running"
    assert "task_id" in res
    assert "Codex" in res["spoken_summary"]

    status = dispatcher.get_status({"task_id": res["task_id"]})
    assert status["success"] is True

    agents = dispatcher.list_agents()
    assert agents["success"] is True
    assert "codex" in agents["installed_agents"]