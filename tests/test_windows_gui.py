import pytest

from tools.windows_gui import WindowsGUIAutomation


class FakeControl:
    def __init__(self, title="Search", control_type="Edit", password=False):
        self._title = title
        self._control_type = control_type
        self._password = password
        self.clicked = False
        self.typed = None

    def window_text(self):
        return self._title

    def friendly_class_name(self):
        return self._control_type

    def is_password(self):
        return self._password

    def click_input(self):
        self.clicked = True

    def set_edit_text(self, value):
        self.typed = value


class FakeWindow:
    def __init__(self, control):
        self.control = control
        self.element_info = type("Info", (), {"process_id": 11, "handle": 22})()

    def window_text(self):
        return "VS Code"

    def descendants(self, **kwargs):
        return [self.control] if kwargs.get("title") == self.control.window_text() else []


def test_gui_automation_clicks_and_types_in_allowlisted_app():
    control = FakeControl()
    window = FakeWindow(control)
    automation = WindowsGUIAutomation(desktop_factory=lambda **_kwargs: type("Desktop", (), {"windows": lambda _self: [window]})())

    clicked = automation.click("vscode", "Search")
    typed = automation.type_text("vscode", "Search", "hello world")
    assert clicked["success"] is True
    assert typed["success"] is True
    assert control.clicked is True
    assert control.typed == "hello world"


def test_gui_automation_rejects_password_and_shell_targets():
    password = FakeControl(password=True)
    window = FakeWindow(password)
    automation = WindowsGUIAutomation(desktop_factory=lambda **_kwargs: type("Desktop", (), {"windows": lambda _self: [window]})())
    result = automation.type_text("vscode", "Search", "secret")
    shell = automation.click("powershell", "Search")
    assert result["success"] is False
    assert result["error_code"] == "SENSITIVE_CONTROL_BLOCKED"
    assert shell["success"] is False
    assert shell["error_code"] == "APPLICATION_NOT_ALLOWED"


def test_gui_automation_rejects_unsafe_hotkey():
    automation = WindowsGUIAutomation(desktop_factory=lambda **_kwargs: None)
    result = automation.hotkey("vscode", "ctrl+alt+delete")
    assert result["success"] is False
    assert result["error_code"] == "KEY_NOT_ALLOWED"


def test_gui_automation_does_not_click_destructive_controls():
    control = FakeControl("Delete")
    window = FakeWindow(control)
    automation = WindowsGUIAutomation(desktop_factory=lambda **_kwargs: type("Desktop", (), {"windows": lambda _self: [window]})())
    result = automation.click("vscode", "Delete")
    assert result["success"] is False
    assert result["error_code"] == "DESTRUCTIVE_CONTROL_BLOCKED"
