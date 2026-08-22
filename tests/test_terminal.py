import asyncio
from pathlib import Path

from agent.config import CommandRule
from agent.workspaces import WorkspaceManager
from tools.terminal import SafeCommandRunner


def test_command_allowlist_is_exact():
    runner = SafeCommandRunner([CommandRule(executable="whoami", args=[])])
    assert runner.build_argv({"command": "whoami"}) == ["whoami"]
    for command in ("del file.txt", "whoami | findstr x", "whoami extra", "powershell -c whoami"):
        try:
            runner.build_argv({"command": command})
        except (PermissionError, ValueError):
            pass
        else:
            raise AssertionError(f"unsafe command accepted: {command}")


def test_dir_builtin_is_fixed_to_a_constant_command():
    runner = SafeCommandRunner([CommandRule(executable="dir", args=[])])
    assert runner.build_argv({"command": "dir"}) == ["cmd.exe", "/d", "/c", "dir"]


def test_command_runner_uses_subprocess_without_shell(monkeypatch):
    calls = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("tools.terminal.subprocess.run", fake_run)
    runner = SafeCommandRunner([CommandRule(executable="whoami", args=[])])
    result = asyncio.run(runner.run({"command": "whoami"}))
    assert result["success"] is True
    assert calls["kwargs"]["shell"] is False


def test_safe_command_requires_and_uses_named_workspace(monkeypatch, tmp_path):
    calls = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(*args, **kwargs):
        calls["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("tools.terminal.subprocess.run", fake_run)
    manager = WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd())
    runner = SafeCommandRunner([CommandRule(executable="whoami", args=[])], workspaces=manager)
    denied = asyncio.run(runner.run_safe({"command": "whoami"}))
    allowed = asyncio.run(runner.run_safe({"command": "whoami", "workspace": "project"}))
    assert denied["success"] is False
    assert allowed["success"] is True
    assert calls["kwargs"]["cwd"] == tmp_path.resolve()
