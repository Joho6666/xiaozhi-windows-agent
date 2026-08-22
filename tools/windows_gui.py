"""Constrained and flexible Windows UI Automation adapter backed by pywinauto UIA."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

from tools.windows_apps import normalize_app_name


GUI_ALLOWLIST = {"notepad", "calculator", "explorer", "vscode", "codeblocks", "edge", "chrome", "firefox"}
SAFE_HOTKEYS = {
    "ctrl+l",
    "ctrl+t",
    "ctrl+w",
    "ctrl+f",
    "ctrl+a",
    "ctrl+c",
    "ctrl+v",
    "ctrl+s",
    "escape",
    "return",
    "alt+left",
    "alt+right",
    "f5",
}
DESTRUCTIVE_CONTROL_TOKENS = ("delete", "remove", "format", "shutdown", "restart", "关机", "删除", "格式化", "卸载")


class WindowsGUIAutomation:
    def __init__(self, desktop_factory: Callable[..., Any] | None = None, max_text_length: int = 10_000) -> None:
        self.desktop_factory = desktop_factory
        self.max_text_length = max_text_length

    def _desktop(self):
        factory = self.desktop_factory
        if factory is None:
            try:
                from pywinauto import Desktop
            except ImportError as exc:
                raise RuntimeError("pywinauto is not installed; run python -m pip install -r requirements.txt") from exc
            factory = Desktop
        return factory(backend="uia")

    @staticmethod
    def _app(name: str) -> str | None:
        canonical = normalize_app_name(name)
        return canonical if canonical in GUI_ALLOWLIST else None

    def _find_window(self, name: str) -> Any:
        app = self._app(name)
        if app is None:
            raise PermissionError("Application is not allowlisted for GUI automation")
        desktop = self._desktop()
        try:
            windows = desktop.windows(visible_only=True)
        except TypeError:
            windows = desktop.windows()
        patterns = {
            "vscode": re.compile(r"(Visual Studio Code|VS Code|Code)", re.I),
            "codeblocks": re.compile(r"Code::?Blocks", re.I),
            "edge": re.compile(r"Microsoft Edge", re.I),
            "chrome": re.compile(r"Google Chrome", re.I),
            "notepad": re.compile(r"Notepad|记事本", re.I),
            "calculator": re.compile(r"Calculator|计算器", re.I),
            "explorer": re.compile(r"File Explorer|文件资源管理器|Explorer", re.I),
            "firefox": re.compile(r"Mozilla Firefox|Firefox", re.I),
        }
        for window in windows:
            if patterns.get(app, re.compile(re.escape(app), re.I)).search(str(window.window_text() or "")):
                return window
        raise LookupError("No visible application window was found")

    @staticmethod
    def _application_for_title(title: str) -> str | None:
        patterns = {
            "vscode": re.compile(r"(Visual Studio Code|VS Code|Code)", re.I),
            "codeblocks": re.compile(r"Code::?Blocks", re.I),
            "edge": re.compile(r"Microsoft Edge", re.I),
            "chrome": re.compile(r"Google Chrome", re.I),
            "notepad": re.compile(r"Notepad|记事本", re.I),
            "calculator": re.compile(r"Calculator|计算器", re.I),
            "explorer": re.compile(r"File Explorer|文件资源管理器|Explorer", re.I),
            "firefox": re.compile(r"Mozilla Firefox|Firefox", re.I),
        }
        return next((name for name, pattern in patterns.items() if pattern.search(title)), None)

    @staticmethod
    def _control(window: Any, title: str) -> Any:
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("control must be a short non-empty title")
        controls = window.descendants(title=title.strip())
        if not controls:
            raise LookupError("Control was not found")
        return controls[0]

    def list_windows(self) -> dict[str, Any]:
        try:
            windows = self._desktop().windows(visible_only=True)
            result = []
            for window in windows:
                title = str(window.window_text() or "").strip()
                if not title:
                    continue
                app = self._application_for_title(title)
                pid = getattr(getattr(window, "element_info", None), "process_id", None)
                if app:
                    result.append({"application": app, "pid": pid})
                else:
                    result.append({"application": title[:50], "pid": pid})
            return {"success": True, "tool": "desktop_list_windows", "message": f"Found {len(result)} visible windows", "windows": result[:30]}
        except (ImportError, OSError, RuntimeError) as exc:
            return {"success": False, "tool": "desktop_list_windows", "error_code": "GUI_UNAVAILABLE", "message": str(exc)}

    def click(self, application: str, control: str) -> dict[str, Any]:
        if isinstance(control, str) and any(token in control.lower() for token in DESTRUCTIVE_CONTROL_TOKENS):
            return {"success": False, "tool": "desktop_click", "error_code": "DESTRUCTIVE_CONTROL_BLOCKED", "message": "Destructive controls cannot be clicked"}
        try:
            win = self._find_window(application)
            if hasattr(win, "set_focus"):
                try:
                    win.set_focus()
                except Exception:
                    pass
            target = self._control(win, control)
            target.click_input()
            return {"success": True, "tool": "desktop_click", "message": "Control clicked", "application": normalize_app_name(application), "control": control}
        except PermissionError as exc:
            return {"success": False, "tool": "desktop_click", "error_code": "APPLICATION_NOT_ALLOWED", "message": str(exc)}
        except LookupError as exc:
            return {"success": False, "tool": "desktop_click", "error_code": "CONTROL_NOT_FOUND", "message": str(exc)}
        except (ImportError, OSError, RuntimeError) as exc:
            return {"success": False, "tool": "desktop_click", "error_code": "GUI_UNAVAILABLE", "message": str(exc)}
        except Exception as exc:
            return {"success": False, "tool": "desktop_click", "error_code": "CLICK_FAILED", "message": str(exc)}

    def type_text(self, application: str, control: str, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text or len(text) > self.max_text_length:
            return {"success": False, "tool": "desktop_type", "error_code": "TEXT_TOO_LONG", "message": "Text is empty or exceeds the configured limit"}
        try:
            win = self._find_window(application)
            if hasattr(win, "set_focus"):
                try:
                    win.set_focus()
                except Exception:
                    pass
            target = self._control(win, control)
            if hasattr(target, "is_password") and (target.is_password() if callable(target.is_password) else bool(target.is_password)):
                return {"success": False, "tool": "desktop_type", "error_code": "SENSITIVE_CONTROL_BLOCKED", "message": "Password controls cannot be used"}
            target.set_edit_text(text)
            return {"success": True, "tool": "desktop_type", "message": "Text entered", "application": normalize_app_name(application), "control": control, "characters": len(text)}
        except PermissionError as exc:
            return {"success": False, "tool": "desktop_type", "error_code": "APPLICATION_NOT_ALLOWED", "message": str(exc)}
        except LookupError as exc:
            return {"success": False, "tool": "desktop_type", "error_code": "CONTROL_NOT_FOUND", "message": str(exc)}
        except (ImportError, OSError, RuntimeError) as exc:
            return {"success": False, "tool": "desktop_type", "error_code": "GUI_UNAVAILABLE", "message": str(exc)}
        except Exception as exc:
            return {"success": False, "tool": "desktop_type", "error_code": "TYPE_FAILED", "message": str(exc)}

    def hotkey(self, application: str, keys: str) -> dict[str, Any]:
        normalized = "+".join(part.strip().lower() for part in keys.split("+")) if isinstance(keys, str) else ""
        if normalized not in SAFE_HOTKEYS:
            return {"success": False, "tool": "desktop_hotkey", "error_code": "KEY_NOT_ALLOWED", "message": "Shortcut is not allowlisted"}
        try:
            window = self._find_window(application)
            if hasattr(window, "set_focus"):
                try:
                    window.set_focus()
                except Exception:
                    pass
            if hasattr(window, "type_keys"):
                window.type_keys("{" + "}{".join(normalized.split("+")) + "}")
            return {"success": True, "tool": "desktop_hotkey", "message": "Shortcut sent", "application": normalize_app_name(application), "keys": normalized}
        except PermissionError as exc:
            return {"success": False, "tool": "desktop_hotkey", "error_code": "APPLICATION_NOT_ALLOWED", "message": str(exc)}
        except LookupError as exc:
            return {"success": False, "tool": "desktop_hotkey", "error_code": "WINDOW_NOT_FOUND", "message": str(exc)}
        except (ImportError, OSError, RuntimeError) as exc:
            return {"success": False, "tool": "desktop_hotkey", "error_code": "GUI_UNAVAILABLE", "message": str(exc)}
        except Exception as exc:
            return {"success": False, "tool": "desktop_hotkey", "error_code": "HOTKEY_FAILED", "message": str(exc)}