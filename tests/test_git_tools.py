import subprocess
from pathlib import Path

from agent.workspaces import WorkspaceManager
from tools.git_tools import GitTools


def test_git_status_and_log_use_workspace(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "hello.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial"], check=True)
    (tmp_path / "hello.txt").write_text("changed", encoding="utf-8")
    manager = WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd())
    tools = GitTools(manager)
    status = tools.git_status("project")
    log = tools.git_log("project")
    assert status["success"] is True
    assert "hello.txt" in status["stdout"]
    assert log["success"] is True


def test_git_tool_rejects_unknown_workspace(tmp_path):
    tools = GitTools(WorkspaceManager({}, Path.cwd()))
    result = tools.git_status("missing")
    assert result["success"] is False
    assert result["error_code"] == "WORKSPACE_NOT_FOUND"


def test_git_tool_rejects_workspace_directory_that_does_not_exist(tmp_path):
    manager = WorkspaceManager({"missing": {"path": str(tmp_path / "missing")}}, Path.cwd())
    result = GitTools(manager).git_status("missing")
    assert result["success"] is False
    assert result["error_code"] == "WORKSPACE_NOT_FOUND"
