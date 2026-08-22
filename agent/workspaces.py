"""Named, path-confined project workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WorkspaceManager:
    def __init__(self, definitions: dict[str, Any], project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self._workspaces: dict[str, Path] = {}
        for name, definition in definitions.items():
            if isinstance(definition, dict):
                raw_path = definition.get("path")
            else:
                raw_path = getattr(definition, "path", str(definition))
            path = Path(str(raw_path)).expanduser()
            if not path.is_absolute():
                path = self.project_dir / path
            self._workspaces[name] = path.resolve()

    def get_path(self, name: str) -> Path:
        if name not in self._workspaces:
            raise KeyError(name)
        return self._workspaces[name]

    def list_workspaces(self) -> list[dict[str, str]]:
        return [{"name": name, "path": str(path), "exists": str(path.exists()).lower()} for name, path in self._workspaces.items()]

    def resolve_child(self, workspace: str, relative_path: str = ".") -> Path:
        root = self.get_path(workspace)
        requested = Path(relative_path)
        if requested.is_absolute():
            raise PermissionError("absolute paths are not allowed inside a workspace")
        raw_candidate = root / requested
        current = raw_candidate
        while current != root and root in current.parents:
            if current.is_symlink():
                raise PermissionError("symbolic links are not allowed")
            current = current.parent
        candidate = raw_candidate.resolve()
        if candidate != root and root not in candidate.parents:
            raise PermissionError("path escapes the workspace")
        return candidate
