"""Multi-Agent Orchestrator and Dispatcher for XiaoZhi.
Enables XiaoZhi (Voice Commander) to dispatch, monitor, and coordinate local CLI agents
(Codex CLI as primary, Claude Code, OpenCode, and local developer runtimes).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from agent.tasks import TaskManager
from agent.workspaces import WorkspaceManager


class AgentDispatcher:
    def __init__(
        self,
        workspaces: WorkspaceManager,
        task_manager: TaskManager,
        default_timeout: float = 300.0,
    ) -> None:
        self.workspaces = workspaces
        self.task_manager = task_manager
        self.default_timeout = default_timeout
        self._last_dispatched_task_id: str | None = None

    def _resolve_cwd(self, workspace: str | None) -> Path:
        if workspace and self.workspaces:
            try:
                return self.workspaces.get_path(workspace)
            except KeyError:
                pass
        if workspace:
            p = Path(os.path.expanduser(workspace)).resolve()
            if p.exists() and p.is_dir():
                return p
        return Path.cwd().resolve()

    def _detect_installed_agents(self) -> dict[str, str]:
        agents = {
            "codex": shutil.which("codex") or shutil.which("codex.cmd") or shutil.which("codex.exe"),
            "claude": shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe"),
            "opencode": shutil.which("opencode") or shutil.which("opencode.cmd") or shutil.which("opencode.exe"),
        }
        return {k: v for k, v in agents.items() if v}

    def _execute_codex(self, root: Path, task: str, mode: str, timeout: float) -> dict[str, Any]:
        executable = shutil.which("codex") or shutil.which("codex.cmd") or shutil.which("codex.exe")
        if not executable:
            return {"success": False, "agent": "codex", "error_code": "NOT_INSTALLED", "message": "Codex CLI is not installed on this machine"}

        if mode == "modify":
            prompt = f"Perform the following coding task on the project and apply necessary changes directly: {task.strip()}"
            argv = [executable, "exec", "--color", "never", "--json", "--skip-git-repo-check", "--cd", str(root), prompt]
        else:
            prompt = f"Analyze the workspace in read-only mode. Do not modify files. Task: {task.strip()}"
            argv = [executable, "exec", "--color", "never", "--json", "--ignore-user-config", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(root), prompt]

        start_time = time.perf_counter()
        try:
            res = subprocess.run(
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            duration = int((time.perf_counter() - start_time) * 1000)
            output = (res.stdout or "").strip() or (res.stderr or "").strip()

            diff_summary = ""
            try:
                git_diff = subprocess.run(
                    ["git", "diff", "--stat"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    check=False,
                )
                if git_diff.stdout and git_diff.stdout.strip():
                    diff_summary = f"\n文件改动统计:\n{git_diff.stdout.strip()}"
            except Exception:
                pass

            success = res.returncode == 0
            if success:
                spoken = f"Codex 已完成任务：{task[:60]}。耗时 {duration//1000} 秒。"
                if diff_summary:
                    spoken += " 已更新工程代码。"
            else:
                spoken = f"Codex 执行任务未完全成功，退出代码 {res.returncode}。"

            return {
                "success": success,
                "agent": "codex",
                "mode": mode,
                "task": task,
                "duration_ms": duration,
                "spoken_summary": spoken,
                "full_result": output[:16000] + diff_summary,
                "return_code": res.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "agent": "codex", "error_code": "TIMEOUT", "message": f"Codex task timed out after {timeout} seconds"}
        except Exception as exc:
            return {"success": False, "agent": "codex", "error_code": "EXEC_FAILED", "message": str(exc)}

    def _execute_claude(self, root: Path, task: str, timeout: float) -> dict[str, Any]:
        executable = shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")
        if not executable:
            return {"success": False, "agent": "claude", "error_code": "NOT_INSTALLED", "message": "Claude Code CLI is not installed"}

        argv = [executable, "-p", task.strip()]
        start_time = time.perf_counter()
        try:
            res = subprocess.run(
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            duration = int((time.perf_counter() - start_time) * 1000)
            output = (res.stdout or "").strip() or (res.stderr or "").strip()
            success = res.returncode == 0
            return {
                "success": success,
                "agent": "claude",
                "task": task,
                "duration_ms": duration,
                "spoken_summary": f"Claude Code 已完成任务：{task[:60]}。" if success else "Claude Code 执行未完成。",
                "full_result": output[:16000],
                "return_code": res.returncode,
            }
        except Exception as exc:
            return {"success": False, "agent": "claude", "error_code": "EXEC_FAILED", "message": str(exc)}

    def _execute_opencode(self, root: Path, task: str, timeout: float) -> dict[str, Any]:
        executable = shutil.which("opencode") or shutil.which("opencode.cmd") or shutil.which("opencode.exe")
        if not executable:
            return {"success": False, "agent": "opencode", "error_code": "NOT_INSTALLED", "message": "OpenCode CLI is not installed"}

        argv = [executable, task.strip()]
        start_time = time.perf_counter()
        try:
            res = subprocess.run(
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            duration = int((time.perf_counter() - start_time) * 1000)
            output = (res.stdout or "").strip() or (res.stderr or "").strip()
            success = res.returncode == 0
            return {
                "success": success,
                "agent": "opencode",
                "task": task,
                "duration_ms": duration,
                "spoken_summary": f"OpenCode 已完成任务：{task[:60]}。" if success else "OpenCode 执行未完成。",
                "full_result": output[:16000],
                "return_code": res.returncode,
            }
        except Exception as exc:
            return {"success": False, "agent": "opencode", "error_code": "EXEC_FAILED", "message": str(exc)}

    def dispatch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        agent_type = str(arguments.get("agent_type") or arguments.get("agent") or "codex").strip().lower()
        task = arguments.get("task")
        workspace = arguments.get("workspace")
        mode = str(arguments.get("mode") or "modify").strip().lower()
        timeout = float(arguments.get("timeout_seconds") or self.default_timeout)

        if not isinstance(task, str) or not task.strip():
            return {"success": False, "tool": "dispatch_agent", "message": "task must be a non-empty string"}

        root = self._resolve_cwd(workspace)

        def runner():
            if agent_type == "codex":
                return self._execute_codex(root, task, mode, timeout)
            elif agent_type == "claude":
                return self._execute_claude(root, task, timeout)
            elif agent_type == "opencode":
                return self._execute_opencode(root, task, timeout)
            else:
                return self._execute_codex(root, task, mode, timeout)

        record = self.task_manager.create_task(
            name=f"agent-{agent_type}",
            handler=runner,
            timeout=timeout + 10,
            metadata={"agent": agent_type, "workspace": str(root), "task": task[:100], "mode": mode},
        )
        task_id = record["task_id"]
        self._last_dispatched_task_id = task_id

        agent_names = {"codex": "Codex", "claude": "Claude Code", "opencode": "OpenCode"}
        display_name = agent_names.get(agent_type, agent_type.upper())

        return {
            "success": True,
            "tool": "dispatch_agent",
            "task_id": task_id,
            "agent": agent_type,
            "status": "running",
            "workspace": str(root),
            "spoken_summary": f"已将任务安排给本地 {display_name} 处理，正在后台执行中。你可以稍后问我任务进度。",
            "message": f"Dispatched task to {display_name} in background (Task ID: {task_id})",
        }

    def get_status(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        task_id = arguments.get("task_id") or self._last_dispatched_task_id
        if not task_id:
            return {"success": False, "tool": "get_agent_status", "message": "No active agent task found. Please dispatch a task first."}

        status_info = self.task_manager.get_status(task_id)
        if not status_info.get("success", False) and status_info.get("error_code") == "TASK_NOT_FOUND":
            return status_info

        status = status_info.get("status")
        meta = status_info.get("metadata", {})
        agent_name = meta.get("agent", "Agent").capitalize()

        if status == "running":
            elapsed = int(time.time() - status_info.get("created_at", time.time()))
            spoken = f"本地 {agent_name} 正在后台执行任务（已运行 {elapsed} 秒）。"
        elif status == "completed":
            result = status_info.get("result", {})
            spoken = result.get("spoken_summary") or f"本地 {agent_name} 已经顺利完成任务！"
        elif status == "failed":
            spoken = f"本地 {agent_name} 执行任务遇到问题或超时。"
        elif status == "cancelled":
            spoken = f"本地 {agent_name} 的任务已被取消。"
        else:
            spoken = f"本地 {agent_name} 当前状态为：{status}。"

        return {
            "success": True,
            "tool": "get_agent_status",
            "task_id": task_id,
            "status": status,
            "agent": meta.get("agent"),
            "spoken_summary": spoken,
            "details": status_info,
        }

    def list_agents(self, _args: dict[str, Any] | None = None) -> dict[str, Any]:
        installed = self._detect_installed_agents()
        tasks = self.task_manager.list_tasks()
        return {
            "success": True,
            "tool": "list_active_agents",
            "installed_agents": list(installed.keys()),
            "active_tasks": [t for t in tasks if t.get("status") == "running"],
            "recent_tasks": tasks[-5:],
            "message": f"Installed agents: {', '.join(installed.keys())}; {len(tasks)} tasks recorded.",
        }


DISPATCH_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "description": "The prompt or instruction for the local agent (e.g. 'Fix compile errors in esp32 project', 'Add Wi-Fi reconnect logic', 'Write unit tests')"},
        "agent_type": {"type": "string", "enum": ["codex", "claude", "opencode"], "description": "Target agent CLI: 'codex' (default, primary), 'claude', or 'opencode'"},
        "workspace": {"type": "string", "description": "Named workspace (e.g. 'esp32', 'agent') or directory path to work on"},
        "mode": {"type": "string", "enum": ["modify", "analyze"], "description": "'modify' to edit code and create files (default); 'analyze' for read-only analysis"},
        "timeout_seconds": {"type": "number", "description": "Maximum execution time in seconds (default 300)"},
    },
    "required": ["task"],
    "additionalProperties": False,
}

GET_AGENT_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "description": "Optional task ID. If omitted, checks the latest dispatched agent task."},
    },
    "additionalProperties": False,
}

LIST_AGENTS_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}