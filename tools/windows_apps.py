"""Application launcher supporting standard apps and Windows Start Menu/system discovery."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


APP_ALIASES = {
    "notepad": "notepad",
    "记事本": "notepad",
    "calculator": "calculator",
    "calc": "calculator",
    "计算器": "calculator",
    "explorer": "explorer",
    "文件管理器": "explorer",
    "cmd": "cmd",
    "命令提示符": "cmd",
    "powershell": "powershell",
    "powershell终端": "powershell",
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "codeblocks": "codeblocks",
    "code::blocks": "codeblocks",
    "code blocks": "codeblocks",
    "codeblocks ide": "codeblocks",
    "browser": "edge",
    "默认浏览器": "edge",
    "浏览器": "edge",
    "2g浏览器": "edge",
    "电脑视": "edge",
    "edge": "edge",
    "edge浏览器": "edge",
    "微软edge": "edge",
    "微软 edge": "edge",
    "微软 edge 浏览器": "edge",
    "谷歌": "chrome",
    "谷歌浏览器": "chrome",
    "google chrome": "chrome",
    "chrome": "chrome",
    "chrome浏览器": "chrome",
    "火狐": "firefox",
    "火狐浏览器": "firefox",
    "firefox": "firefox",
}

APP_CANDIDATES = {
    "notepad": ["notepad.exe", "notepad"],
    "calculator": ["calc.exe", "calc"],
    "explorer": ["explorer.exe", "explorer"],
    "cmd": ["cmd.exe", "cmd"],
    "powershell": ["powershell.exe", "powershell", "pwsh.exe", "pwsh"],
    "vscode": ["code.exe", "code.cmd", "code"],
    "codeblocks": ["codeblocks.exe", "codeblocks"],
    "edge": ["msedge.exe", "msedge"],
    "chrome": ["chrome.exe", "chrome"],
    "firefox": ["firefox.exe", "firefox"],
}


def _windows_known_paths(app: str) -> list[Path]:
    """Return vendor-documented install locations."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    roots = [Path(value) for value in (local_app_data, program_files, program_files_x86) if value]
    paths: list[Path] = []
    if app == "vscode":
        paths.extend(root / "Microsoft VS Code" / "Code.exe" for root in roots)
    elif app in {"edge", "chrome", "firefox"}:
        for root in roots:
            if app == "edge":
                paths.append(root / "Microsoft" / "Edge" / "Application" / "msedge.exe")
            elif app == "chrome":
                paths.append(root / "Google" / "Chrome" / "Application" / "chrome.exe")
            else:
                paths.append(root / "Mozilla Firefox" / "firefox.exe")
    return paths


def normalize_app_name(name: str) -> str:
    key = " ".join(name.strip().lower().split())
    return APP_ALIASES.get(key, key)


def _find_executable(candidates: list[str]) -> str | None:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _resolve_executable(app: str) -> str | None:
    executable = _find_executable(APP_CANDIDATES.get(app, [app]))
    if executable:
        if executable.lower().endswith(".cmd"):
            real_executable = Path(executable).resolve().parent.parent / "Code.exe"
            if real_executable.is_file():
                return str(real_executable)
        return executable
    for path in _windows_known_paths(app):
        if path.is_file():
            return str(path)
    return None


def _find_start_menu_app(name: str) -> str | None:
    query = name.strip().lower()
    clean_query = query.replace(".exe", "").replace(".lnk", "")
    roots = [
        Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs",
        Path.home() / "AppData/Local/Programs",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.lnk"):
            stem = path.stem.lower()
            if stem == clean_query or clean_query in stem or stem in clean_query:
                return str(path)
    return None


def launch_application(name: str, launcher: Callable[..., Any] | None = None) -> dict[str, Any]:
    if not isinstance(name, str) or not name.strip():
        return {"success": False, "message": "name must be a non-empty string"}

    raw_name = name.strip()
    normalized = normalize_app_name(raw_name)

    if (":\\" in raw_name or "/" in raw_name or "\\\\" in raw_name) and normalized not in APP_CANDIDATES:
        return {"success": False, "message": "Application is not allowed"}

    # 1. Known candidate mapping
    if normalized in APP_CANDIDATES:
        executable = _resolve_executable(normalized)
        if executable:
            try:
                (launcher or subprocess.Popen)([executable], close_fds=True)
                return {"success": True, "message": f"{normalized} opened successfully"}
            except (OSError, subprocess.SubprocessError) as exc:
                return {"success": False, "message": f"Unable to open application: {exc}"}

    # 2. Direct executable on PATH
    which_path = shutil.which(raw_name) or shutil.which(f"{raw_name}.exe") or shutil.which(f"{raw_name}.cmd")
    if which_path:
        try:
            (launcher or subprocess.Popen)([which_path], close_fds=True)
            return {"success": True, "message": f"{raw_name} opened successfully ({which_path})"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"success": False, "message": f"Unable to open application: {exc}"}

    # 3. Start menu shortcut
    shortcut = _find_start_menu_app(raw_name)
    if shortcut:
        try:
            if launcher:
                launcher([shortcut])
            elif hasattr(os, "startfile"):
                os.startfile(shortcut)
            else:
                subprocess.Popen(["cmd.exe", "/c", "start", "", shortcut])
            return {"success": True, "message": f"{raw_name} opened successfully via shortcut: {Path(shortcut).name}"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"success": False, "message": f"Unable to open application: {exc}"}

    # 4. Fallback system launch
    try:
        if launcher:
            launcher([raw_name])
        elif hasattr(os, "startfile"):
            os.startfile(raw_name)
        else:
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{raw_name}'"])
        return {"success": True, "message": f"{raw_name} opened successfully"}
    except Exception as exc:
        return {"success": False, "message": f"Application '{raw_name}' not found or could not be launched: {exc}"}


def open_application(arguments: dict[str, Any]) -> dict[str, Any]:
    name = arguments.get("name")
    if not isinstance(name, str) or not name.strip():
        return {"success": False, "message": "name must be a non-empty string"}
    return launch_application(name)


OPEN_APPLICATION_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "description": "Application name, Chinese alias, executable name, or shortcut name"}},
    "required": ["name"],
    "additionalProperties": False,
}