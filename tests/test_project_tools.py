from pathlib import Path

from agent.workspaces import WorkspaceManager
from tools.project_tools import ProjectTools


def test_detect_project_type_and_choose_fixed_test_command(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    runner = ProjectTools(WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd()), command_runner=lambda command, workspace: {"success": True, "command": command, "workspace": workspace})
    detected = runner.detect_project_type("project")
    result = runner.run_tests("project")
    assert detected["project_types"] == ["python"]
    assert result["success"] is True
    assert result["command"] == "python -m pytest -q"


def test_run_tests_rejects_workspace_without_known_test_manifest(tmp_path: Path):
    runner = ProjectTools(WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd()))
    result = runner.run_tests("project")
    assert result["success"] is False
    assert result["error_code"] == "TEST_COMMAND_NOT_DETECTED"
