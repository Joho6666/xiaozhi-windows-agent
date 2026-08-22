import pytest
from pathlib import Path
from security.permissions import PermissionManager
from agent.registry import RiskLevel
from tools.terminal import SafeCommandRunner
from tools.file_tools import FileSystemTools
from agent.workspaces import WorkspaceManager


@pytest.mark.asyncio
async def test_unrestricted_profile_auto_approves_all_risk_levels():
    perm = PermissionManager({"profile": "unrestricted"})
    assert await perm.check(RiskLevel.LOW, "low action") == "allow"
    assert await perm.check(RiskLevel.MEDIUM, "med action") == "allow"
    assert await perm.check(RiskLevel.HIGH, "high action (screen capture, write file)") == "allow"


@pytest.mark.asyncio
async def test_run_shell_command_executes_powershell():
    runner = SafeCommandRunner([], timeout_seconds=10)
    result = await runner.run_shell({"command": "echo 'hello from shell'"})
    assert result["success"] is True
    assert "hello from shell" in result["stdout"]


def test_delete_file_removes_file(tmp_path):
    f = tmp_path / "test_del.txt"
    f.write_text("content", encoding="utf-8")
    tools = FileSystemTools(WorkspaceManager({"test": {"path": str(tmp_path)}}, Path.cwd()))
    res = tools.delete_file("test", "test_del.txt")
    assert res["success"] is True
    assert not f.exists()