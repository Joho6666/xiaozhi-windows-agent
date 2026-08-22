"""CLI entry point for XiaoZhi Windows Agent Bridge."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from agent.bridge import MCPBridge
from agent.config import load_settings
from agent.connection import MCPConnection
from agent.registry import RiskLevel, Tool, ToolRegistry
from security.permissions import PermissionManager
from tools.filesystem import DirectoryLister, LIST_DIRECTORY_SCHEMA
from tools.file_tools import FileSystemTools
from tools.git_tools import GitTools
from tools.process_tools import ProcessTools
from tools.system_tools import detect_dev_tools, get_system_info
from tools.codex_tools import CodexTaskRunner, codex_path
from tools.terminal import RUN_COMMAND_SCHEMA, RUN_SAFE_COMMAND_SCHEMA, RUN_SHELL_COMMAND_SCHEMA, SafeCommandRunner
from tools.windows_apps import OPEN_APPLICATION_SCHEMA, open_application
from tools.browser_automation import BROWSER_CLICK_SCHEMA, BROWSER_OPEN_SCHEMA, BROWSER_READ_SCHEMA, BROWSER_SEARCH_SCHEMA, BrowserAutomation
from tools.windows_gui import WindowsGUIAutomation
from tools.project_tools import ProjectTools
from tools.screen_capture import ScreenCapture
from agent.workspaces import WorkspaceManager
from agent.tasks import TaskManager
from agent.skills import SkillManager
from agent.workflows import WorkflowManager
from security.audit import AuditLogger


logger = logging.getLogger(__name__)


def configure_logging(level: str, project_dir: Path) -> None:
    log_dir = project_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(log_dir / "agent.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(stream)
    root.addHandler(file_handler)


async def _browser_search_tool(browser: BrowserAutomation, arguments: dict) -> dict:
    return await browser.search(arguments.get("query", ""), arguments.get("max_results"))


async def _browser_open_tool(browser: BrowserAutomation, arguments: dict) -> dict:
    return await browser.open_url(arguments.get("url", ""))


async def _browser_click_tool(browser: BrowserAutomation, arguments: dict) -> dict:
    return await browser.click(arguments.get("target", ""))


def _workspace_schema() -> dict:
    return {
        "type": "object",
        "properties": {"workspace": {"type": "string", "description": "Named workspace from config.yaml"}},
        "required": ["workspace"],
        "additionalProperties": False,
    }


def _task_schema() -> dict:
    return {
        "type": "object",
        "properties": {"task_id": {"type": "string", "minLength": 1}},
        "required": ["task_id"],
        "additionalProperties": False,
    }


def _get_workspace(manager: WorkspaceManager, name: str) -> dict:
    try:
        path = manager.get_path(name)
    except KeyError:
        return {"success": False, "tool": "get_workspace", "error_code": "WORKSPACE_NOT_FOUND", "message": f"Workspace not found: {name}"}
    return {"success": True, "tool": "get_workspace", "message": "Workspace found", "workspace": name, "path": str(path), "exists": path.exists()}


async def _cancel_task(manager: TaskManager, task_id: str) -> dict:
    result = await manager.cancel_task(task_id)
    result.setdefault("tool", "cancel_task")
    return result


def _skill_result(tool: str, skills: list[dict]) -> dict:
    return {"success": True, "tool": tool, "message": f"{len(skills)} skill(s) available", "skills": skills}


def _toggle_skill(manager: SkillManager, operation: str, name: str) -> dict:
    try:
        skill = getattr(manager, operation)(name)
    except KeyError:
        return {"success": False, "tool": operation, "error_code": "SKILL_NOT_FOUND", "message": f"Skill not found: {name}"}
    action = "enabled" if operation == "enable_skill" else "disabled"
    return {"success": True, "tool": operation, "message": f"Skill {action}", "skill": skill}


def build_registry(settings, browser: BrowserAutomation | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    app_tool = Tool("open_application", "Open an allowlisted Windows application.", OPEN_APPLICATION_SCHEMA, open_application, RiskLevel.LOW, category="application")
    directory_lister = DirectoryLister(settings.config.directories.allowed_roots, settings.config.directories.max_entries)
    workspace_manager = WorkspaceManager(getattr(settings.config, "workspaces", {}), getattr(settings, "project_dir", Path.cwd()))
    command_runner = SafeCommandRunner(settings.config.commands.allowed, settings.config.commands.timeout_seconds, settings.config.commands.max_output_chars, workspace_manager)
    project_tools = ProjectTools(workspace_manager, command_runner=lambda command, workspace: asyncio.run(command_runner.run_safe({"command": command, "workspace": workspace})))
    file_config = getattr(settings.config, "files", None)
    file_tools = FileSystemTools(
        workspace_manager,
        allowed_extensions=getattr(file_config, "allowed_extensions", None),
        max_file_bytes=getattr(file_config, "max_file_bytes", 1_000_000),
        max_return_chars=getattr(file_config, "max_return_chars", 12_000),
        max_results=getattr(file_config, "max_results", 100),
        directory_lister=directory_lister,
    )
    git_tools = GitTools(workspace_manager)
    process_tools = ProcessTools()
    gui_tools = WindowsGUIAutomation()
    screen_capture = ScreenCapture()
    codex_runner = CodexTaskRunner(workspace_manager) if codex_path() else None
    task_manager = TaskManager()
    skill_manager = SkillManager(Path(getattr(settings, "project_dir", Path.cwd())) / "skills", getattr(settings.config, "enabled_skills", []))

    def arg(args, name, default=None):
        return args.get(name, default)

    tools = {
        "open_application": app_tool,
        "list_directory": Tool("list_directory", "List entries in an allowlisted directory.", LIST_DIRECTORY_SCHEMA, lambda args: directory_lister.list_directory(arg(args, "path", "")), RiskLevel.LOW, category="filesystem"),
        "run_command": Tool("run_command", "Run one exact command from the safe command allowlist.", RUN_COMMAND_SCHEMA, command_runner.run, RiskLevel.MEDIUM, category="terminal", timeout=settings.config.commands.timeout_seconds + 5),
        "run_safe_command": Tool("run_safe_command", "Run one exact command from the safe command allowlist inside a named workspace.", RUN_SAFE_COMMAND_SCHEMA, command_runner.run_safe, RiskLevel.MEDIUM, category="terminal", timeout=settings.config.commands.timeout_seconds + 5),
        "run_shell_command": Tool("run_shell_command", "Execute any PowerShell or CMD shell command on the system.", RUN_SHELL_COMMAND_SCHEMA, command_runner.run_shell, RiskLevel.MEDIUM, category="terminal", timeout=120),
        "delete_file": Tool("delete_file", "Delete a file or folder from the filesystem.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}, lambda args: file_tools.delete_file(arg(args, "workspace"), arg(args, "path", "")), RiskLevel.HIGH, category="filesystem"),
        "detect_project_type": Tool("detect_project_type", "Detect a supported project type from workspace marker files.", _workspace_schema(), lambda args: project_tools.detect_project_type(arg(args, "workspace", "")), RiskLevel.LOW, category="coding"),
        "run_project_tests": Tool("run_project_tests", "Detect and run a fixed test command for a named workspace.", _workspace_schema(), lambda args: project_tools.run_tests(arg(args, "workspace", "")), RiskLevel.MEDIUM, category="coding", timeout=120),
        "list_workspaces": Tool("list_workspaces", "List named project workspaces available to the agent.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: {"success": True, "tool": "list_workspaces", "message": "Workspaces listed", "workspaces": workspace_manager.list_workspaces()}, RiskLevel.LOW, category="filesystem"),
        "get_workspace": Tool("get_workspace", "Get the path and existence of a named workspace.", {"type": "object", "properties": {"workspace": {"type": "string"}}, "required": ["workspace"], "additionalProperties": False}, lambda args: _get_workspace(workspace_manager, arg(args, "workspace", "")), RiskLevel.LOW, category="filesystem"),
        "list_workspace_files": Tool("list_workspace_files", "List files in a named workspace.", {"type": "object", "properties": {"workspace": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["workspace"], "additionalProperties": False}, lambda args: file_tools.find_files(arg(args, "workspace", ""), arg(args, "pattern", "*")), RiskLevel.LOW, category="filesystem"),
        "find_files": Tool("find_files", "Find files in an allowed directory or named workspace by filename pattern.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string", "description": "Desktop, Documents, Downloads, or an allowed relative path"}, "pattern": {"type": "string"}}, "required": ["pattern"], "additionalProperties": False}, lambda args: file_tools.find_files(arg(args, "workspace", None), arg(args, "pattern", "*"), path=arg(args, "path", None)), RiskLevel.LOW, category="filesystem"),
        "read_text_file": Tool("read_text_file", "Read a bounded text file from a workspace or allowed directory path.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}, lambda args: file_tools.read_text_file(arg(args, "workspace", None), arg(args, "path", "")), RiskLevel.LOW, category="filesystem"),
        "search_text": Tool("search_text", "Search text in allowed source files within a workspace or allowed directory.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}, "query": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["query"], "additionalProperties": False}, lambda args: file_tools.search_text(arg(args, "workspace", None), arg(args, "query", ""), arg(args, "pattern", "*"), path=arg(args, "path", None)), RiskLevel.LOW, category="filesystem"),
        "get_file_info": Tool("get_file_info", "Get metadata for a workspace file.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}}, "required": ["workspace", "path"], "additionalProperties": False}, lambda args: file_tools.get_file_info(arg(args, "workspace", ""), arg(args, "path", "")), RiskLevel.LOW, category="filesystem"),
        "open_file": Tool("open_file", "Open an allowed workspace file with its registered Windows application.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}}, "required": ["workspace", "path"], "additionalProperties": False}, lambda args: file_tools.open_file(arg(args, "workspace", ""), arg(args, "path", "")), RiskLevel.MEDIUM, category="filesystem"),
        "write_text_file": Tool("write_text_file", "Write a bounded text file inside a named workspace after confirmation.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}, "text": {"type": "string"}}, "required": ["workspace", "path", "text"], "additionalProperties": False}, lambda args: file_tools.write_text_file(arg(args, "workspace", ""), arg(args, "path", ""), arg(args, "text", "")), RiskLevel.HIGH, category="filesystem"),
        "get_recent_files": Tool("get_recent_files", "List recently modified files in an allowed directory or named workspace.", {"type": "object", "properties": {"workspace": {"type": "string"}, "path": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False}, lambda args: file_tools.get_recent_files(arg(args, "workspace", None), arg(args, "limit", 10), path=arg(args, "path", None)), RiskLevel.LOW, category="filesystem"),
        "git_status": Tool("git_status", "Show Git working tree status for a workspace.", _workspace_schema(), lambda args: git_tools.git_status(arg(args, "workspace", "")), RiskLevel.LOW, category="coding"),
        "git_diff": Tool("git_diff", "Show unstaged Git diff for a workspace.", _workspace_schema(), lambda args: git_tools.git_diff(arg(args, "workspace", "")), RiskLevel.LOW, category="coding"),
        "git_log": Tool("git_log", "Show recent Git commits for a workspace.", _workspace_schema(), lambda args: git_tools.git_log(arg(args, "workspace", "")), RiskLevel.LOW, category="coding"),
        "git_branch": Tool("git_branch", "Show the current Git branch for a workspace.", _workspace_schema(), lambda args: git_tools.git_branch(arg(args, "workspace", "")), RiskLevel.LOW, category="coding"),
        "get_system_info": Tool("get_system_info", "Get non-secret Windows and Python system information.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: get_system_info(), RiskLevel.LOW, category="system"),
        "detect_dev_tools": Tool("detect_dev_tools", "Detect installed development tools and versions.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: detect_dev_tools(), RiskLevel.LOW, category="system"),
        "list_running_apps": Tool("list_running_apps", "List running allowlisted applications.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: process_tools.list_running_apps(), RiskLevel.LOW, category="application"),
        "close_application": Tool("close_application", "Close a named allowlisted application.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, lambda args: process_tools.close_application(arg(args, "name", "")), RiskLevel.MEDIUM, category="application"),
        "focus_application": Tool("focus_application", "Focus a named allowlisted application window.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, lambda args: process_tools.focus_application(arg(args, "name", "")), RiskLevel.MEDIUM, category="application"),
        "desktop_list_windows": Tool("desktop_list_windows", "List visible Windows desktop windows without exposing their contents.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: gui_tools.list_windows(), RiskLevel.LOW, category="application"),
        "desktop_click": Tool("desktop_click", "Click a named control in an allowlisted application window.", {"type": "object", "properties": {"application": {"type": "string"}, "control": {"type": "string"}}, "required": ["application", "control"], "additionalProperties": False}, lambda args: gui_tools.click(arg(args, "application", ""), arg(args, "control", "")), RiskLevel.MEDIUM, category="application"),
        "desktop_type": Tool("desktop_type", "Enter non-secret text into a named control in an allowlisted application.", {"type": "object", "properties": {"application": {"type": "string"}, "control": {"type": "string"}, "text": {"type": "string"}}, "required": ["application", "control", "text"], "additionalProperties": False}, lambda args: gui_tools.type_text(arg(args, "application", ""), arg(args, "control", ""), arg(args, "text", "")), RiskLevel.MEDIUM, category="application"),
        "desktop_hotkey": Tool("desktop_hotkey", "Send a safe allowlisted shortcut to an allowlisted application.", {"type": "object", "properties": {"application": {"type": "string"}, "keys": {"type": "string"}}, "required": ["application", "keys"], "additionalProperties": False}, lambda args: gui_tools.hotkey(arg(args, "application", ""), arg(args, "keys", "")), RiskLevel.MEDIUM, category="application"),
        "screen_capture": Tool("screen_capture", "Capture the current Windows screen as an in-memory image for visual analysis.", {"type": "object", "properties": {}, "additionalProperties": False}, screen_capture.capture, RiskLevel.HIGH, category="system"),
        "get_task_status": Tool("get_task_status", "Get the status and result of a background task.", _task_schema(), lambda args: task_manager.get_status(arg(args, "task_id", "")), RiskLevel.LOW, category="workflow"),
        "get_task_result": Tool("get_task_result", "Get the current result of a background task.", _task_schema(), lambda args: task_manager.get_status(arg(args, "task_id", "")), RiskLevel.LOW, category="workflow"),
        "cancel_task": Tool("cancel_task", "Cancel a queued or running background task.", _task_schema(), lambda args: _cancel_task(task_manager, arg(args, "task_id", "")), RiskLevel.MEDIUM, category="workflow"),
        "discover_skills": Tool("discover_skills", "Discover local declarative skills in the project skills directory.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: _skill_result("discover_skills", skill_manager.discover()), RiskLevel.LOW, category="workflow"),
        "list_skills": Tool("list_skills", "List locally installed skills and enabled state.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: _skill_result("list_skills", skill_manager.list_skills()), RiskLevel.LOW, category="workflow"),
        "enable_skill": Tool("enable_skill", "Enable a local skill without changing its declared tools.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, lambda args: _toggle_skill(skill_manager, "enable_skill", arg(args, "name", "")), RiskLevel.LOW, category="workflow"),
        "disable_skill": Tool("disable_skill", "Disable a local skill.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, lambda args: _toggle_skill(skill_manager, "disable_skill", arg(args, "name", "")), RiskLevel.LOW, category="workflow"),
    }
    workflow_manager = WorkflowManager(Path(getattr(settings, "project_dir", Path.cwd())) / "workflows", registry)
    tools.update(
        {
            "list_workflows": Tool("list_workflows", "List local YAML workflows.", {"type": "object", "properties": {}, "additionalProperties": False}, lambda _args: {"success": True, "tool": "list_workflows", "message": "Workflows listed", "workflows": workflow_manager.list_workflows()}, RiskLevel.LOW, category="workflow"),
            "run_workflow": Tool("run_workflow", "Run a named local workflow made only of registered tools.", {"type": "object", "properties": {"name": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["name"], "additionalProperties": False}, lambda args: workflow_manager.run(arg(args, "name", ""), arg(args, "arguments", {})), RiskLevel.MEDIUM, category="workflow", timeout=120),
        }
    )
    if codex_runner is not None:
        async def queue_codex(arguments: dict) -> dict:
            mode = str(arguments.get("mode", "analyze")).lower()
            return task_manager.create_task("codex_task", lambda: codex_runner.run(arguments), timeout=codex_runner.timeout_seconds, metadata={"workspace": arguments.get("workspace"), "mode": mode})

        tools["codex_task"] = Tool("codex_task", "Queue a Codex task (analyze or modify) inside a workspace.", {"type": "object", "properties": {"workspace": {"type": "string"}, "task": {"type": "string"}, "mode": {"type": "string", "enum": ["analyze", "modify"]}}, "required": ["workspace", "task"], "additionalProperties": False}, queue_codex, RiskLevel.LOW, category="coding", timeout=10)
    if settings.config.browser.enabled and browser is not None:
        tools.update(
            {
                "browser_search": Tool("browser_search", "Search the public web in a visible browser and return result links.", BROWSER_SEARCH_SCHEMA, lambda args: _browser_search_tool(browser, args), RiskLevel.LOW, category="browser"),
                "browser_open": Tool("browser_open", "Open a public web page in the browser and return a text preview.", BROWSER_OPEN_SCHEMA, lambda args: _browser_open_tool(browser, args), RiskLevel.LOW, category="browser"),
                "browser_read_page": Tool("browser_read_page", "Read text from the currently open browser page.", BROWSER_READ_SCHEMA, lambda _args: browser.read_page(), RiskLevel.LOW, category="browser"),
                "browser_click": Tool("browser_click", "Click a visible link or button on the current browser page after confirmation.", BROWSER_CLICK_SCHEMA, lambda args: _browser_click_tool(browser, args), RiskLevel.MEDIUM, category="browser"),
            }
        )
    for name in settings.config.enabled_tools:
        if name not in tools and name == "codex_task":
            continue
        if name not in tools and name.startswith("browser_") and browser is None:
            logger.warning("Skipping browser tool %s because browser runtime is disabled", name)
            continue
        if name not in tools:
            raise ValueError(f"unknown enabled tool in config.yaml: {name}")
        registry.register(tools[name])
    registry.task_manager = task_manager
    registry.skill_manager = skill_manager
    registry.workflow_manager = workflow_manager
    return registry


async def async_main() -> None:
    project_dir = Path(__file__).resolve().parent
    settings = load_settings(project_dir)
    configure_logging(settings.log_level, project_dir)
    browser = BrowserAutomation(settings.config.browser, project_dir) if settings.config.browser.enabled else None
    registry = build_registry(settings, browser)
    print("===================================")
    print(" XiaoZhi Windows Agent v0.1")
    print("===================================")
    print("XiaoZhi MCP     CONNECTING")
    print(f"Tools           {len(registry)}")
    print("Security        ENABLED")
    print(f"Permission      {settings.config.permissions.profile.upper()}")
    print("\nRegistered Tools:")
    for tool in registry.list_tools():
        print(f"✓ {tool['name']}")
    permissions = PermissionManager(settings.config.permissions, settings.config.confirm_timeout_seconds)
    connection = MCPConnection(settings.endpoint, settings.config.protocol_mode, settings.config.request_timeout_seconds)
    shutdown_callbacks = [registry.task_manager.shutdown]
    if browser:
        shutdown_callbacks.insert(0, browser.close)
    bridge = MCPBridge(connection, registry, permissions, settings.config.reconnect.delays_seconds, shutdown_callbacks, AuditLogger(project_dir / "logs" / "audit.jsonl"))
    try:
        await bridge.run()
    finally:
        await bridge.stop()


def main() -> int:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
