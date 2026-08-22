"""Fixed-command project detection and test execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.workspaces import WorkspaceManager


class ProjectTools:
    def __init__(self, workspaces: WorkspaceManager, command_runner: Callable[[str, str], dict[str, Any]] | None = None) -> None:
        self.workspaces = workspaces
        self.command_runner = command_runner

    def _root(self, workspace: str) -> Path:
        try:
            return self.workspaces.get_path(workspace)
        except KeyError:
            raise

    def detect_project_type(self, workspace: str) -> dict[str, Any]:
        try:
            root = self._root(workspace)
        except KeyError:
            return {"success": False, "tool": "detect_project_type", "error_code": "WORKSPACE_NOT_FOUND", "message": f"Workspace not found: {workspace}"}
        markers = {
            "python": ("pyproject.toml", "pytest.ini", "setup.py", "requirements.txt"),
            "node": ("package.json",),
            "platformio": ("platformio.ini",),
            "esp_idf": ("CMakeLists.txt", "sdkconfig"),
        }
        types = [name for name, files in markers.items() if any((root / file).exists() for file in files)]
        return {"success": True, "tool": "detect_project_type", "message": "Project type detected", "project_types": types}

    def _test_command(self, root: Path) -> str | None:
        if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "tests").is_dir():
            return "python -m pytest -q"
        if (root / "package.json").exists():
            return "npm test"
        if (root / "platformio.ini").exists():
            return "pio test"
        return None

    def run_tests(self, workspace: str) -> dict[str, Any]:
        try:
            root = self._root(workspace)
        except KeyError:
            return {"success": False, "tool": "run_project_tests", "error_code": "WORKSPACE_NOT_FOUND", "message": f"Workspace not found: {workspace}"}
        command = self._test_command(root)
        if command is None:
            return {"success": False, "tool": "run_project_tests", "error_code": "TEST_COMMAND_NOT_DETECTED", "message": "No supported test manifest was found"}
        if self.command_runner is None:
            return {"success": False, "tool": "run_project_tests", "error_code": "COMMAND_RUNNER_UNAVAILABLE", "message": "Safe command runner is unavailable"}
        result = self.command_runner(command, workspace)
        result.setdefault("tool", "run_project_tests")
        result.setdefault("command", command)
        return result

