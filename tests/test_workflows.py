from pathlib import Path

import pytest

from agent.registry import RiskLevel, Tool, ToolRegistry
from agent.workflows import WorkflowManager


@pytest.mark.asyncio
async def test_workflow_runs_registered_steps_and_stops_on_failure(tmp_path: Path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "inspect.yaml").write_text(
        "name: inspect\ndescription: Inspect\nsteps:\n  - tool: first\n  - tool: second\n",
        encoding="utf-8",
    )
    registry = ToolRegistry()
    registry.register(Tool("first", "first", {"type": "object"}, lambda _: {"success": True}, RiskLevel.LOW))
    registry.register(Tool("second", "second", {"type": "object"}, lambda _: {"success": False, "message": "stopped"}, RiskLevel.LOW))
    manager = WorkflowManager(workflows, registry)

    result = await manager.run("inspect", {})
    assert result["success"] is False
    assert result["failed_step"] == 2
    assert len(result["steps"]) == 2


def test_workflow_loader_ignores_unknown_files(tmp_path: Path):
    (tmp_path / "not-yaml.txt").write_text("x", encoding="utf-8")
    manager = WorkflowManager(tmp_path, ToolRegistry())
    assert manager.list_workflows() == []
