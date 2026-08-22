"""Process listing, graceful closing, and window focusing for all Windows applications."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from tools.windows_apps import normalize_app_name


def _focus_pid(pid: int) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    focused = False

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def callback(hwnd, _lparam):
        nonlocal focused
        process_id = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == pid and user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            focused = bool(user32.SetForegroundWindow(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return focused


PROCESS_ALLOWLIST = {
    "notepad": {"notepad.exe"},
    "calculator": {"calculatorapp.exe", "calc.exe"},
    "explorer": {"explorer.exe"},
    "cmd": {"cmd.exe"},
    "powershell": {"powershell.exe", "pwsh.exe"},
    "vscode": {"code.exe"},
    "codeblocks": {"codeblocks.exe"},
    "edge": {"msedge.exe"},
    "chrome": {"chrome.exe"},
    "firefox": {"firefox.exe"},
}


class ProcessTools:
    def __init__(self, process_iter: Callable[..., Any] | None = None, process_factory: Callable[[int], Any] | None = None) -> None:
        if process_iter is None:
            import psutil

            process_iter = psutil.process_iter
            process_factory = psutil.Process
        self.process_iter = process_iter
        self.process_factory = process_factory

    def list_running_apps(self) -> dict[str, Any]:
        processes: list[dict[str, Any]] = []
        seen = set()
        for process in self.process_iter(attrs=["pid", "name", "exe"]):
            try:
                info = getattr(process, "info", {})
                name = info.get("name")
                pid = info.get("pid")
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                processes.append({"pid": pid, "name": name, "exe": info.get("exe")})
            except Exception:
                continue
        return {"success": True, "tool": "list_running_apps", "message": f"Found {len(processes)} running processes", "processes": processes[:100]}

    def close_application(self, name: str) -> dict[str, Any]:
        canonical = normalize_app_name(name)
        allowed_names = PROCESS_ALLOWLIST.get(canonical)
        if not allowed_names and not name.lower().endswith(".exe"):
            return {"success": False, "tool": "close_application", "error_code": "APPLICATION_NOT_ALLOWED", "message": "Application is not allowlisted for closing"}
        target_names = allowed_names if allowed_names else {name.lower()}
        closed = 0
        for process in self.process_iter(attrs=["pid", "name", "exe"]):
            try:
                info = getattr(process, "info", {})
                if (info.get("name") or "").lower() in target_names:
                    if self.process_factory:
                        self.process_factory(info["pid"]).terminate()
                        closed += 1
            except Exception:
                continue
        if not allowed_names and closed == 0:
            return {"success": False, "tool": "close_application", "error_code": "APPLICATION_NOT_ALLOWED", "message": "Application is not allowlisted for closing"}
        return {"success": True, "tool": "close_application", "message": f"Closed {closed} process(es)", "closed": closed}

    def focus_application(self, name: str) -> dict[str, Any]:
        canonical = normalize_app_name(name)
        allowed_names = PROCESS_ALLOWLIST.get(canonical)
        if not allowed_names:
            allowed_names = {name.lower(), f"{name.lower()}.exe"}
        focused = 0
        for process in self.process_iter(attrs=["pid", "name", "exe"]):
            try:
                info = getattr(process, "info", {})
                p_name = (info.get("name") or "").lower()
                if p_name in allowed_names and _focus_pid(info["pid"]):
                    focused += 1
                    break
            except Exception:
                continue
        if focused == 0:
            return {"success": False, "tool": "focus_application", "error_code": "WINDOW_NOT_FOUND", "message": "No visible window was found for the application"}
        return {"success": True, "tool": "focus_application", "message": f"Focused {canonical}", "focused": focused}