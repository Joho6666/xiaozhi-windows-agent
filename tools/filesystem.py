"""Directory listing supporting all local paths and shortcuts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SENSITIVE_PARTS = {
    "system32",
    "sam",
    "security",
    "credentials",
    "credential manager",
    ".ssh",
    "browser login data",
    "cookies",
}


def _is_sensitive(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    return bool(lowered & SENSITIVE_PARTS)


class DirectoryLister:
    def __init__(self, allowed_roots: list[str] | None = None, max_entries: int = 200, allow_arbitrary: bool = True) -> None:
        self.max_entries = max_entries
        self.allow_arbitrary = allow_arbitrary
        self._roots: dict[str, Path] = {}
        roots = allowed_roots or ["Desktop", "Documents", "Downloads", "."]
        for root in roots:
            alias, configured_path = (root.split("=", 1) if "=" in root else (root, None))
            alias = alias.strip()
            path = Path(configured_path).expanduser() if configured_path else Path(root).expanduser()
            if configured_path is None and root in {"Desktop", "Documents", "Downloads"}:
                path = Path.home() / root
            try:
                resolved = path.resolve()
                self._roots[alias.lower()] = resolved
                if resolved == Path.cwd().resolve() or (len(roots) == 1 and "." not in self._roots):
                    self._roots.setdefault(".", resolved)
            except Exception:
                pass

    def resolve_allowed_path(self, user_path: str) -> Path:
        if not isinstance(user_path, str) or not user_path.strip():
            raise ValueError("path must be a non-empty string")
        requested = user_path.strip()
        key = requested.lower().rstrip("\\/")
        if key in self._roots:
            path = self._roots[key]
        else:
            normalized = requested.replace("\\", "/")
            parts = normalized.split("/")
            alias_root = self._roots.get(parts[0].lower()) if parts else None
            if alias_root is not None:
                path = (alias_root / "/".join(parts[1:])).resolve()
            else:
                p = Path(os.path.expanduser(requested))
                if not p.is_absolute():
                    base = self._roots.get(".", Path.cwd().resolve())
                    p = base / p
                path = p.resolve()

        if _is_sensitive(path):
            raise PermissionError("sensitive system directory is not allowed")
        return path

    def list_directory(self, user_path: str) -> dict[str, Any]:
        try:
            path = self.resolve_allowed_path(user_path)
            if not path.exists() or not path.is_dir():
                return {"success": False, "message": f"Directory not found: {path}"}
            entries: list[dict[str, Any]] = []
            for entry in sorted(path.iterdir(), key=lambda item: item.name.lower())[: self.max_entries]:
                try:
                    if _is_sensitive(entry):
                        continue
                    is_dir = entry.is_dir()
                    item: dict[str, Any] = {
                        "name": entry.name,
                        "type": "directory" if is_dir else "file",
                    }
                    if not is_dir:
                        item["size"] = entry.stat().st_size
                    entries.append(item)
                except OSError:
                    continue
            return {"success": True, "path": str(path), "entries": entries, "truncated": len(entries) >= self.max_entries}
        except (PermissionError, ValueError) as exc:
            return {"success": False, "message": str(exc)}
        except Exception as exc:
            return {"success": False, "message": str(exc)}


LIST_DIRECTORY_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "Path to list (e.g. Desktop, Downloads, C:/, D:/Projects, or relative path)"}},
    "required": ["path"],
    "additionalProperties": False,
}