from tools.system_tools import detect_dev_tools, get_system_info


def test_detect_dev_tools_reports_installed_and_missing(monkeypatch):
    def fake_which(name):
        return "C:/tools/" + name if name in {"git", "codex"} else None

    monkeypatch.setattr("tools.system_tools.shutil.which", fake_which)
    monkeypatch.setattr("tools.system_tools._version", lambda path: "1.2.3")
    result = detect_dev_tools()
    assert result["success"] is True
    assert result["tools"]["git"]["installed"] is True
    assert result["tools"]["codex"]["version"] == "1.2.3"
    assert result["tools"]["node"]["installed"] is False


def test_system_info_has_non_secret_basics():
    result = get_system_info()
    assert result["success"] is True
    assert result["system"]
    assert result["python_version"]
    assert "password" not in result
    assert "token" not in result
