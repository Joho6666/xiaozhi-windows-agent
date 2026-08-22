from pathlib import Path

import pytest

from agent.workspaces import WorkspaceManager
from tools.file_tools import FileSystemTools
from tools.filesystem import DirectoryLister


def make_tools(tmp_path):
    (tmp_path / "report.pdf").write_bytes(b"pdf")
    (tmp_path / "notes.md").write_text("STM32CubeMX\nsecond line", encoding="utf-8")
    (tmp_path / "data.bin").write_bytes(b"binary")
    manager = WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd())
    return FileSystemTools(manager, allowed_extensions={".txt", ".md", ".json", ".yaml", ".yml", ".py", ".js", ".ts", ".cpp", ".c", ".h", ".java", ".csv"})


def test_find_files_returns_matching_workspace_files(tmp_path):
    tools = make_tools(tmp_path)
    result = tools.find_files("project", "*.pdf")
    assert result["success"] is True
    assert result["files"][0]["name"] == "report.pdf"


def test_read_text_file_and_search_text_are_bounded(tmp_path):
    tools = make_tools(tmp_path)
    read = tools.read_text_file("project", "notes.md")
    search = tools.search_text("project", "STM32CubeMX")
    assert read["success"] is True and "second line" in read["text"]
    assert search["success"] is True and search["matches"][0]["file"] == "notes.md"


def test_read_text_file_rejects_unsupported_extension_and_escape(tmp_path):
    tools = make_tools(tmp_path)
    unsupported = tools.read_text_file("project", "data.bin")
    assert unsupported["success"] is False
    with pytest.raises(PermissionError):
        tools.find_files("project", "..\\outside")


def test_find_files_can_search_an_allowlisted_directory_alias(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "manual.pdf").write_bytes(b"pdf")
    tools = FileSystemTools(
        WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd()),
        directory_lister=DirectoryLister([str(desktop)]),
    )
    result = tools.find_files(None, "*.pdf", path=".")
    assert result["success"] is True
    assert result["files"][0]["name"] == "manual.pdf"


def test_get_recent_files_can_search_an_allowlisted_directory_alias(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "latest.txt").write_text("latest", encoding="utf-8")
    tools = FileSystemTools(
        WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd()),
        directory_lister=DirectoryLister([str(downloads)]),
    )
    result = tools.get_recent_files(None, 1, path=".")
    assert result["success"] is True
    assert result["files"][0]["path"] == "latest.txt"


def test_read_and_search_can_use_allowed_directory_file_path(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "notes.md").write_text("ESP32 build failed", encoding="utf-8")
    lister = DirectoryLister([f"Desktop={desktop}"], max_entries=10)
    tools = FileSystemTools(
        WorkspaceManager({}, Path.cwd()),
        directory_lister=lister,
    )
    read = tools.read_text_file(None, "Desktop/notes.md")
    search = tools.search_text(None, "ESP32", path="Desktop")
    assert read["success"] is True
    assert search["success"] is True
    assert search["matches"][0]["file"] == "notes.md"


def test_write_text_file_is_workspace_confined_and_open_file_uses_safe_path(tmp_path):
    (tmp_path / "notes.md").write_text("old", encoding="utf-8")
    opened = []
    tools = FileSystemTools(
        WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd()),
        file_opener=lambda path: opened.append(path),
    )
    written = tools.write_text_file("project", "notes.md", "new")
    opened_result = tools.open_file("project", "notes.md")
    assert written["success"] is True
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "new"
    assert opened_result["success"] is True
    assert opened == [(tmp_path / "notes.md").resolve()]


def test_write_text_file_rejects_unsupported_file_and_absolute_path(tmp_path):
    tools = FileSystemTools(WorkspaceManager({"project": {"path": str(tmp_path)}}, Path.cwd()))
    assert tools.write_text_file("project", "program.exe", "bad")["error_code"] == "UNSUPPORTED_FILE_TYPE"
    with pytest.raises(PermissionError):
        tools.write_text_file("project", "C:\\Windows\\x.txt", "bad")
