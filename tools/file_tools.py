"""File discovery, reading, writing, and search supporting all workspace and system paths."""

from __future__ import annotations

import fnmatch
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.workspaces import WorkspaceManager
from tools.filesystem import DirectoryLister


class FileSystemTools:
    def __init__(
        self,
        workspaces: WorkspaceManager,
        allowed_extensions: set[str] | None = None,
        max_file_bytes: int = 50_000_000,
        max_return_chars: int = 20_000,
        max_results: int = 200,
        directory_lister: DirectoryLister | None = None,
        file_opener: Callable[[Path], Any] | None = None,
    ) -> None:
        self.workspaces = workspaces
        self.directory_lister = directory_lister
        self.file_opener = file_opener or (os.startfile if hasattr(os, "startfile") else None)
        self.allowed_extensions = allowed_extensions or {".txt", ".md", ".json", ".yaml", ".yml", ".py", ".js", ".ts", ".cpp", ".c", ".h", ".java", ".csv"}
        self.max_file_bytes = max_file_bytes
        self.max_return_chars = max_return_chars
        self.max_results = max_results

    def _result(self, tool: str, success: bool, message: str, **data: Any) -> dict[str, Any]:
        return {"success": success, "tool": tool, "message": message, **data}

    def _find_root(self, workspace: str | None, path: str | None) -> Path:
        if workspace:
            return self.workspaces.get_path(workspace)
        if self.directory_lister:
            return self.directory_lister.resolve_allowed_path(path or ".")
        p = Path(os.path.expanduser(path or "."))
        return p.resolve()

    def _resolve_file(self, workspace: str | None, path: str) -> Path:
        if workspace:
            return self.workspaces.resolve_child(workspace, path)
        if self.directory_lister:
            try:
                return self.directory_lister.resolve_allowed_path(path)
            except Exception:
                pass
        p = Path(os.path.expanduser(path))
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()

    def find_files(self, workspace: str | None = None, pattern: str = "*", max_results: int | None = None, path: str | None = None) -> dict[str, Any]:
        if not pattern or len(pattern) > 100 or any(part in pattern for part in ("/", "\\", "..")):
            raise PermissionError("pattern must be a filename pattern without path traversal")
        root = self._find_root(workspace, path)
        if not root.exists():
            return self._result("find_files", False, "Workspace directory does not exist", error_code="WORKSPACE_NOT_FOUND")
        found: list[dict[str, Any]] = []
        limit = min(max_results or self.max_results, self.max_results)
        try:
            for item in root.rglob("*"):
                if len(found) >= limit:
                    break
                if not item.is_file() or not fnmatch.fnmatch(item.name.lower(), pattern.lower()):
                    continue
                try:
                    relative = item.relative_to(root)
                    found.append({"name": item.name, "path": str(relative), "size": item.stat().st_size})
                except Exception:
                    found.append({"name": item.name, "path": str(item), "size": item.stat().st_size})
        except Exception as exc:
            return self._result("find_files", False, f"Error searching files: {exc}")
        return self._result("find_files", True, f"Found {len(found)} file(s)", files=found, truncated=len(found) >= limit)

    def read_text_file(self, workspace: str | None = None, path: str = "") -> dict[str, Any]:
        if not path:
            return self._result("read_text_file", False, "path is required", error_code="INVALID_PATH")
        target = self._resolve_file(workspace, path)
        if self.allowed_extensions and target.suffix.lower() not in self.allowed_extensions:
            return self._result("read_text_file", False, "File type is not allowed", error_code="UNSUPPORTED_FILE_TYPE")
        if not target.exists() or not target.is_file():
            return self._result("read_text_file", False, "File not found", error_code="FILE_NOT_FOUND")
        try:
            size = target.stat().st_size
            if size > self.max_file_bytes:
                return self._result("read_text_file", False, "File is too large", error_code="FILE_TOO_LARGE", size=size)
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = target.read_text(encoding="gbk", errors="replace")
            return self._result(
                "read_text_file",
                True,
                "File read successfully",
                path=str(path),
                size=size,
                lines=text.count("\n") + (1 if text else 0),
                text=text[: self.max_return_chars],
                truncated=len(text) > self.max_return_chars,
            )
        except Exception as exc:
            return self._result("read_text_file", False, f"Error reading file: {exc}", error_code="READ_ERROR")

    def search_text(self, workspace: str | None = None, query: str = "", pattern: str = "*", path: str | None = None) -> dict[str, Any]:
        if not query or len(query) > 500:
            return self._result("search_text", False, "query must be a non-empty string under 500 characters", error_code="INVALID_QUERY")
        root = self._find_root(workspace, path)
        matches: list[dict[str, Any]] = []
        try:
            for item in root.rglob("*"):
                if len(matches) >= self.max_results or not item.is_file() or not fnmatch.fnmatch(item.name.lower(), pattern.lower()):
                    continue
                if self.allowed_extensions and item.suffix.lower() not in self.allowed_extensions:
                    continue
                try:
                    try:
                        lines = item.read_text(encoding="utf-8").splitlines()
                    except UnicodeDecodeError:
                        lines = item.read_text(encoding="gbk", errors="replace").splitlines()
                    for line_number, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            matches.append({"file": str(item.relative_to(root)), "line": line_number, "text": line.strip()[:500]})
                            if len(matches) >= self.max_results:
                                break
                except (OSError, UnicodeError):
                    continue
        except Exception as exc:
            return self._result("search_text", False, f"Error searching text: {exc}")
        return self._result("search_text", True, f"Found {len(matches)} match(es)", matches=matches, truncated=len(matches) >= self.max_results)

    def get_file_info(self, workspace: str | None = None, path: str = "") -> dict[str, Any]:
        target = self._resolve_file(workspace, path)
        if not target.exists():
            return self._result("get_file_info", False, "File not found", error_code="FILE_NOT_FOUND")
        stat = target.stat()
        return self._result(
            "get_file_info",
            True,
            "File information retrieved",
            path=str(path),
            name=target.name,
            size=stat.st_size,
            is_directory=target.is_dir(),
            modified_at=stat.st_mtime,
        )

    def write_text_file(self, workspace: str | None = None, path: str = "", text: str = "") -> dict[str, Any]:
        if not isinstance(text, str):
            return self._result("write_text_file", False, "Text must be a string", error_code="INVALID_TEXT")
        target = self._resolve_file(workspace, path)
        if self.allowed_extensions and target.suffix.lower() not in self.allowed_extensions:
            return self._result("write_text_file", False, "File type is not allowed", error_code="UNSUPPORTED_FILE_TYPE")
        try:
            if not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")
            return self._result("write_text_file", True, "File written successfully", path=str(path), size=target.stat().st_size)
        except Exception as exc:
            return self._result("write_text_file", False, f"Error writing file: {exc}", error_code="WRITE_ERROR")

    def delete_file(self, workspace: str | None = None, path: str = "") -> dict[str, Any]:
        if not path:
            return self._result("delete_file", False, "path is required", error_code="INVALID_PATH")
        target = self._resolve_file(workspace, path)
        if not target.exists():
            return self._result("delete_file", False, f"File or directory not found: {target}", error_code="NOT_FOUND")
        try:
            if target.is_dir():
                shutil.rmtree(target)
                return self._result("delete_file", True, f"Directory deleted: {target}", path=str(target))
            else:
                target.unlink()
                return self._result("delete_file", True, f"File deleted: {target}", path=str(target))
        except Exception as exc:
            return self._result("delete_file", False, f"Error deleting: {exc}", error_code="DELETE_ERROR")

    def open_file(self, workspace: str | None = None, path: str = "") -> dict[str, Any]:
        target = self._resolve_file(workspace, path)
        if self.allowed_extensions and target.suffix.lower() not in self.allowed_extensions:
            return self._result("open_file", False, "File type is not allowed", error_code="UNSUPPORTED_FILE_TYPE")
        if not target.exists() or not target.is_file():
            return self._result("open_file", False, "File not found", error_code="FILE_NOT_FOUND")
        if self.file_opener is None:
            return self._result("open_file", False, "Windows file opener is unavailable", error_code="OPEN_FILE_UNAVAILABLE")
        try:
            self.file_opener(target)
        except Exception as exc:
            return self._result("open_file", False, "Unable to open file", error_code="OPEN_FILE_FAILED", detail=str(exc))
        return self._result("open_file", True, "File opened successfully", path=str(target))

    def get_recent_files(self, workspace: str | None = None, limit: int = 10, path: str | None = None) -> dict[str, Any]:
        root = self._find_root(workspace, path)
        try:
            files = [item for item in root.rglob("*") if item.is_file()]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return self._result(
                "get_recent_files",
                True,
                f"Found {min(limit, len(files))} recent file(s)",
                files=[{"path": str(p.relative_to(root)), "modified_at": p.stat().st_mtime, "size": p.stat().st_size} for p in files[: max(1, min(limit, 50))]],
            )
        except Exception as exc:
            return self._result("get_recent_files", False, f"Error getting recent files: {exc}")