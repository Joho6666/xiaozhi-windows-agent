from pathlib import Path

from agent.workspaces import WorkspaceManager
from tools.codex_tools import CodexTaskRunner


def test_codex_analyze_uses_read_only_workspace_command(monkeypatch, tmp_path):
    calls = []

    class Completed:
        returncode = 0
        stdout = '{"type":"message","message":"analysis complete"}\n'
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Completed()

    monkeypatch.setattr("tools.codex_tools.shutil.which", lambda name: "C:/tools/codex.exe" if name == "codex" else None)
    monkeypatch.setattr("tools.codex_tools.subprocess.run", fake_run)
    runner = CodexTaskRunner(WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd()))
    result = runner.run({"workspace": "esp32", "task": "analyze build errors", "mode": "analyze"})
    assert result["success"] is True
    argv, kwargs = calls[0]
    assert argv[:2] == ["C:/tools/codex.exe", "exec"]
    assert "--sandbox" in argv and "read-only" in argv
    assert "--ephemeral" in argv
    assert "--ask-for-approval" not in argv
    assert "--ignore-user-config" in argv
    assert "--json" in argv
    assert kwargs["shell"] is False
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


def test_codex_modify_supports_workspace_modification(monkeypatch, tmp_path):
    calls = []

    class Completed:
        returncode = 0
        stdout = '{"type":"message","message":"modification complete"}\n'
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Completed()

    monkeypatch.setattr("tools.codex_tools.shutil.which", lambda name: "C:/tools/codex.exe" if name == "codex" else None)
    monkeypatch.setattr("tools.codex_tools.subprocess.run", fake_run)
    runner = CodexTaskRunner(WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd()))
    result = runner.run({"workspace": "esp32", "task": "change code", "mode": "modify"})
    assert result["success"] is True
    argv, kwargs = calls[0]
    assert argv[:2] == ["C:/tools/codex.exe", "exec"]
    assert "--sandbox" not in argv