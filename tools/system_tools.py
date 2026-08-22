"""Non-secret local environment and system information tools."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEV_TOOLS = {
    "git": ("git", "--version"),
    "python": ("python", "--version"),
    "node": ("node", "--version"),
    "npm": ("npm", "--version"),
    "pnpm": ("pnpm", "--version"),
    "codex": ("codex", "--version"),
    "claude": ("claude", "--version"),
    "platformio": ("pio", "--version"),
    "esp_idf": ("idf.py", "--version"),
    "cmake": ("cmake", "--version"),
    "ninja": ("ninja", "--version"),
    "java": ("java", "-version"),
    "adb": ("adb", "version"),
}


def _version(path: str) -> str:
    try:
        executable = Path(path).stem.lower()
        flag = "version" if executable == "adb" else "-version" if executable == "java" else "--version"
        result = subprocess.run([path, flag], shell=False, capture_output=True, text=True, timeout=5, check=False)
        output = (result.stdout or result.stderr or "").strip().splitlines()
        return output[0][:200] if output else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def detect_dev_tools() -> dict[str, Any]:
    detected: dict[str, Any] = {}
    for name, (command, _flag) in DEV_TOOLS.items():
        path = shutil.which(command)
        detected[name] = {"installed": bool(path), "path": path, "version": _version(path) if path else None}
    return {"success": True, "tool": "detect_dev_tools", "message": "Development tools detected", "tools": detected}


def get_system_info() -> dict[str, Any]:
    result: dict[str, Any] = {
        "success": True,
        "tool": "get_system_info",
        "message": "System information retrieved",
        "system": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
    }
    try:
        import psutil

        result["cpu_percent"] = psutil.cpu_percent(interval=None)
        result["memory_percent"] = psutil.virtual_memory().percent
        disk = psutil.disk_usage("C:\\") if platform.system() == "Windows" else psutil.disk_usage("/")
        result["disk_percent"] = disk.percent
    except ImportError:
        result["message"] = "Basic system information retrieved; install psutil for usage metrics"
    return result
