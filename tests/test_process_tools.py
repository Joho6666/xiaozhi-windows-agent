from tools.process_tools import ProcessTools


def test_list_running_apps_uses_process_provider():
    class FakeProcess:
        info = {"pid": 42, "name": "notepad.exe", "exe": "C:/Windows/notepad.exe"}

    tools = ProcessTools(process_iter=lambda **_kwargs: [FakeProcess()])
    result = tools.list_running_apps()
    assert result["success"] is True
    assert result["processes"][0]["name"] == "notepad.exe"


def test_close_application_rejects_non_allowlisted_names():
    tools = ProcessTools(process_iter=lambda **_kwargs: [])
    result = tools.close_application("unknown.exe")
    assert result["success"] is False
    assert result["error_code"] == "APPLICATION_NOT_ALLOWED"


def test_focus_application_only_targets_allowlisted_process(monkeypatch):
    class FakeProcess:
        info = {"pid": 101, "name": "msedge.exe", "exe": "C:/Edge/msedge.exe"}

    focused = []
    monkeypatch.setattr("tools.process_tools._focus_pid", lambda pid: focused.append(pid) or True)
    tools = ProcessTools(process_iter=lambda **_kwargs: [FakeProcess()])
    result = tools.focus_application("浏览器")
    assert result["success"] is True
    assert focused == [101]
