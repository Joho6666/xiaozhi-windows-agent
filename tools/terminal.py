"""Command execution supporting allowlisted runs and unrestricted PowerShell/shell execution."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
from typing import Any

from agent.config import CommandRule
from agent.workspaces import WorkspaceManager


FORBIDDEN_PATTERN = re.compile(r"[|&><;`\r\n]|\$\(", re.IGNORECASE)


class SafeCommandRunner:
    def __init__(
        self,
        rules: list[CommandRule],
        timeout_seconds: float = 30.0,
        max_output_chars: int = 8000,
        workspaces: WorkspaceManager | None = None,
        allow_arbitrary: bool = False,
    ) -> None:
        self.rules = rules
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self.workspaces = workspaces
        self.allow_arbitrary = allow_arbitrary

    @staticmethod
    def _normalize(value: str) -> str:
        return os.path.basename(value).lower()

    def build_argv(self, arguments: dict[str, Any]) -> list[str]:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")

        if FORBIDDEN_PATTERN.search(command):
            if self.allow_arbitrary:
                return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
            raise PermissionError("shell operators and nested shells are forbidden")

        argv = shlex.split(command, posix=False)
        if not argv:
            raise ValueError("command is empty")
        normalized_argv = [self._normalize(argv[0]), *argv[1:]]

        for rule in self.rules:
            if self._normalize(rule.executable) == normalized_argv[0] and rule.args == normalized_argv[1:]:
                if normalized_argv[0] == "dir":
                    return ["cmd.exe", "/d", "/c", "dir"]
                return [rule.executable, *rule.args]

        if self.allow_arbitrary:
            if normalized_argv[0] == "dir":
                return ["cmd.exe", "/d", "/c", "dir"]
            return argv

        raise PermissionError("command or arguments are not allowlisted")

    async def _run_argv(self, argv: list[str], cwd: Any = None) -> dict[str, Any]:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                cwd=cwd,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
            stdout = (completed.stdout or "")[: self.max_output_chars]
            stderr = (completed.stderr or "")[: self.max_output_chars]
            return {
                "success": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "truncated": len(completed.stdout or "") > self.max_output_chars or len(completed.stderr or "") > self.max_output_chars,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Command timed out", "error_code": "TIMEOUT"}
        except OSError as exc:
            return {"success": False, "message": f"Command failed to start: {exc}", "error_code": "COMMAND_START_FAILED"}

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            argv = self.build_argv(arguments)
        except (PermissionError, ValueError) as exc:
            return {"success": False, "message": str(exc)}
        return await self._run_argv(argv)

    async def run_safe(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.workspaces is None:
            return {"success": False, "error_code": "WORKSPACE_REQUIRED", "message": "A named workspace is required"}
        workspace = arguments.get("workspace")
        if not isinstance(workspace, str) or not workspace.strip():
            return {"success": False, "error_code": "WORKSPACE_REQUIRED", "message": "A named workspace is required"}
        try:
            cwd = self.workspaces.get_path(workspace)
        except KeyError:
            return {"success": False, "error_code": "WORKSPACE_NOT_FOUND", "message": f"Workspace not found: {workspace}"}
        if not cwd.exists() or not cwd.is_dir():
            return {"success": False, "error_code": "WORKSPACE_NOT_FOUND", "message": "Workspace directory does not exist"}
        try:
            argv = self.build_argv(arguments)
        except (PermissionError, ValueError) as exc:
            return {"success": False, "message": str(exc)}
        result = await self._run_argv(argv, cwd=cwd)
        result["workspace"] = workspace
        return result

    async def run_shell(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return {"success": False, "tool": "run_shell_command", "message": "command must be a non-empty string"}

        cwd_arg = arguments.get("cwd") or arguments.get("workspace")
        resolved_cwd = None
        if cwd_arg and self.workspaces and cwd_arg in self.workspaces.entries:
            resolved_cwd = str(self.workspaces.get_path(cwd_arg))
        elif cwd_arg:
            p = os.path.abspath(os.path.expanduser(str(cwd_arg)))
            if os.path.exists(p) and os.path.isdir(p):
                resolved_cwd = p

        timeout = float(arguments.get("timeout_seconds") or self.timeout_seconds)

        try:
            shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command] if os.name == "nt" else ["/bin/bash", "-c", command]
            completed = await asyncio.to_thread(
                subprocess.run,
                shell_cmd,
                cwd=resolved_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout = (completed.stdout or "")[: self.max_output_chars]
            stderr = (completed.stderr or "")[: self.max_output_chars]
            return {
                "success": completed.returncode == 0,
                "tool": "run_shell_command",
                "returncode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "cwd": resolved_cwd or os.getcwd(),
                "message": "Command completed successfully" if completed.returncode == 0 else f"Command exited with return code {completed.returncode}",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "tool": "run_shell_command", "error_code": "TIMEOUT", "message": "Command execution timed out"}
        except Exception as exc:
            return {"success": False, "tool": "run_shell_command", "error_code": "COMMAND_FAILED", "message": str(exc)}


RUN_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "Command string to execute"}},
    "required": ["command"],
    "additionalProperties": False,
}

RUN_SAFE_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "workspace": {"type": "string", "description": "Named workspace or directory"},
        "command": {"type": "string", "description": "Command string to execute"},
    },
    "required": ["workspace", "command"],
    "additionalProperties": False,
}

RUN_SHELL_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "PowerShell / Shell command to execute"},
        "cwd": {"type": "string", "description": "Optional working directory or named workspace"},
        "timeout_seconds": {"type": "number", "description": "Optional timeout in seconds"},
    },
    "required": ["command"],
    "additionalProperties": False,
}