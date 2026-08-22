from pathlib import Path

import pytest

from agent.workspaces import WorkspaceManager


def test_workspace_manager_resolves_named_workspace_and_child(tmp_path):
    manager = WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd())
    assert manager.list_workspaces()[0]["name"] == "esp32"
    child = manager.resolve_child("esp32", "src/main.cpp")
    assert child == (tmp_path / "src" / "main.cpp").resolve()


def test_workspace_manager_rejects_path_escape(tmp_path):
    manager = WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd())
    with pytest.raises(PermissionError):
        manager.resolve_child("esp32", "..\\secret.txt")


def test_workspace_manager_rejects_unknown_workspace(tmp_path):
    manager = WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd())
    with pytest.raises(KeyError):
        manager.get_path("missing")


def test_workspace_manager_rejects_symlinked_child(tmp_path):
    target = tmp_path / "real.txt"
    target.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")
    manager = WorkspaceManager({"esp32": {"path": str(tmp_path)}}, Path.cwd())
    with pytest.raises(PermissionError):
        manager.resolve_child("esp32", "link.txt")
