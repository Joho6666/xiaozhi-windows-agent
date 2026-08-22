"""Read-only Git tools constrained to named workspaces."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from agent.workspaces import WorkspaceManager


class GitTools:
    def __init__(self, workspaces: WorkspaceManager, timeout_seconds: float = 20.0, max_output_chars: int = 12_000) -> None:
        self.workspaces = workspaces
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def _run(self, tool: str, workspace: str, args: list[str]) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            cwd = self.workspaces.get_path(workspace)
        except KeyError:
            return {"success": False, "tool": tool, "error_code": "WORKSPACE_NOT_FOUND", "message": f"Workspace not found: {workspace}"}
        if not cwd.exists() or not cwd.is_dir():
            return {"success": False, "tool": tool, "error_code": "WORKSPACE_NOT_FOUND", "message": "Workspace directory does not exist"}
        try:
            result = subprocess.run(["git", *args], cwd=cwd, shell=False, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
        except FileNotFoundError:
            return {"success": False, "tool": tool, "error_code": "GIT_NOT_INSTALLED", "message": "Git executable was not found"}
        except subprocess.TimeoutExpired:
            return {"success": False, "tool": tool, "error_code": "TIMEOUT", "message": "Git command timed out"}
        stdout = (result.stdout or "")[: self.max_output_chars]
        stderr = (result.stderr or "")[: self.max_output_chars]
        if result.returncode != 0:
            code = "NOT_GIT_REPOSITORY" if "not a git repository" in stderr.lower() else "GIT_COMMAND_FAILED"
            return {"success": False, "tool": tool, "error_code": code, "message": stderr.strip() or "Git command failed", "return_code": result.returncode, "stdout": stdout, "stderr": stderr, "duration_ms": int((time.perf_counter() - start) * 1000)}
        return {"success": True, "tool": tool, "message": f"{tool} completed", "stdout": stdout, "stderr": stderr, "return_code": result.returncode, "duration_ms": int((time.perf_counter() - start) * 1000)}

    def git_status(self, workspace: str) -> dict[str, Any]:
        return self._run("git_status", workspace, ["status", "--short", "--branch"])

    def git_diff(self, workspace: str) -> dict[str, Any]:
        return self._run("git_diff", workspace, ["diff", "--no-ext-diff", "--", "."])

    def git_log(self, workspace: str) -> dict[str, Any]:
        return self._run("git_log", workspace, ["log", "-10", "--oneline", "--decorate"])

    def git_branch(self, workspace: str) -> dict[str, Any]:
        return self._run("git_branch", workspace, ["branch", "--show-current"])
