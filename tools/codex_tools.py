"""Codex CLI wrapper supporting both read-only analysis and workspace modification."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

from agent.workspaces import WorkspaceManager


def codex_path() -> str | None:
    return shutil.which("codex")


class CodexTaskRunner:
    def __init__(self, workspaces: WorkspaceManager, timeout_seconds: float = 180.0, max_output_chars: int = 16_000) -> None:
        self.workspaces = workspaces
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace = arguments.get("workspace")
        task = arguments.get("task")
        mode = str(arguments.get("mode", "analyze")).lower()
        if not isinstance(task, str) or not task.strip() or len(task) > 4000:
            return {"success": False, "tool": "codex_task", "error_code": "INVALID_TASK", "message": "task must be a non-empty string under 4000 characters"}
        executable = codex_path()
        if not executable:
            return {"success": False, "tool": "codex_task", "error_code": "CODEX_NOT_INSTALLED", "message": "Codex CLI was not found"}
        try:
            root = self.workspaces.get_path(workspace) if workspace else self.workspaces.get_path("agent")
        except KeyError:
            return {"success": False, "tool": "codex_task", "error_code": "WORKSPACE_NOT_FOUND", "message": f"Workspace not found: {workspace}"}

        if mode == "modify":
            prompt = "Perform the following task on the workspace and apply needed changes. Task: " + task.strip()
            argv = [executable, "exec", "--color", "never", "--json", "--skip-git-repo-check", "--cd", str(root), prompt]
        else:
            prompt = "Analyze the workspace in read-only mode. Do not modify files, do not delete files, and do not run destructive commands. Task: " + task.strip()
            argv = [executable, "exec", "--color", "never", "--json", "--ignore-user-config", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(root), prompt]

        start = time.perf_counter()
        try:
            result = subprocess.run(argv, cwd=root, shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            return {"success": False, "tool": "codex_task", "error_code": "TIMEOUT", "message": "Codex task timed out"}
        except OSError as exc:
            return {"success": False, "tool": "codex_task", "error_code": "CODEX_START_FAILED", "message": f"Codex could not start: {exc}"}
        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        text = output or error
        return {
            "success": result.returncode == 0,
            "tool": "codex_task",
            "message": "Codex task completed" if result.returncode == 0 else "Codex task failed",
            "spoken_summary": text[:1200],
            "full_result": text[: self.max_output_chars],
            "return_code": result.returncode,
            "duration_ms": int((time.perf_counter() - start) * 1000),
        }
