from tools.windows_apps import _resolve_executable, launch_application, normalize_app_name
from pathlib import Path


def test_chinese_aliases():
    assert normalize_app_name("记事本") == "notepad"
    assert normalize_app_name("VS Code") == "vscode"
    assert normalize_app_name("2G浏览器") == "edge"
    assert normalize_app_name("微软 Edge 浏览器") == "edge"
    assert normalize_app_name("电脑视") == "edge"
    assert normalize_app_name("Chrome") == "chrome"


def test_application_allowlist_and_mock_launcher():
    calls = []

    def launcher(argv, **kwargs):
        calls.append(argv)

    result = launch_application("记事本", launcher=launcher)
    assert result["success"] is True
    assert calls and Path(calls[0][0]).name.lower() in {"notepad.exe", "notepad"}


def test_browser_defaults_to_edge_and_chrome_is_explicit(monkeypatch):
    monkeypatch.setattr("tools.windows_apps._find_executable", lambda candidates: candidates[0])
    assert normalize_app_name("浏览器") == "edge"
    assert normalize_app_name("Edge") == "edge"
    assert normalize_app_name("Chrome") == "chrome"
    assert Path(_resolve_executable("edge")).name.lower() == "msedge.exe"
    assert Path(_resolve_executable("chrome")).name.lower() == "chrome.exe"


def test_application_rejects_arbitrary_executable():
    result = launch_application("C:\\Windows\\System32\\calc.exe", launcher=lambda *_args, **_kwargs: None)
    assert result["success"] is False
    assert "allowed" in result["message"]


def test_codeblocks_is_allowlisted_with_common_aliases(monkeypatch):
    monkeypatch.setattr("tools.windows_apps._find_executable", lambda _candidates: "C:/Program Files/CodeBlocks/codeblocks.exe")
    assert normalize_app_name("Code::Blocks") == "codeblocks"
    assert launch_application("CodeBlocks", launcher=lambda *_args, **_kwargs: None)["success"] is True


def test_vscode_resolves_command_shim_to_gui_executable(monkeypatch, tmp_path):
    shim = tmp_path / "bin" / "code.cmd"
    real = tmp_path / "Code.exe"
    shim.parent.mkdir()
    shim.write_text("@echo off", encoding="utf-8")
    real.write_bytes(b"")
    monkeypatch.setattr("tools.windows_apps._find_executable", lambda _candidates: str(shim))
    assert _resolve_executable("vscode") == str(real)
