from tools.filesystem import DirectoryLister


def test_directory_lister_allows_project_relative_paths(tmp_path):
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    lister = DirectoryLister([str(tmp_path)], max_entries=10)
    result = lister.list_directory(".")
    assert result["success"] is True
    assert result["entries"][0]["name"] == "hello.txt"


def test_directory_lister_rejects_absolute_escape(tmp_path):
    lister = DirectoryLister([str(tmp_path)], max_entries=10)
    result = lister.list_directory("C:\\Windows\\System32")
    assert result["success"] is False


def test_directory_lister_resolves_file_below_named_root(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "notes.md").write_text("hello", encoding="utf-8")
    lister = DirectoryLister([f"Desktop={desktop}"], max_entries=10)
    assert lister.resolve_allowed_path("Desktop/notes.md") == (desktop / "notes.md").resolve()
