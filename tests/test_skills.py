from pathlib import Path

import pytest

from agent.skills import SkillManager


def test_skill_manager_discovers_and_toggles_local_skills(tmp_path: Path):
    skill_dir = tmp_path / "embedded"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(
        "name: embedded\ndescription: Embedded helper\ntools: [read_text_file, git_status]\nworkspaces: [esp32]\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("# Embedded\n", encoding="utf-8")
    manager = SkillManager(tmp_path)

    discovered = manager.list_skills()
    assert discovered[0]["name"] == "embedded"
    assert discovered[0]["enabled"] is False
    assert manager.enable_skill("embedded")["enabled"] is True
    assert manager.get_skill("embedded")["tools"] == ["read_text_file", "git_status"]
    assert manager.disable_skill("embedded")["enabled"] is False


def test_skill_manager_rejects_missing_or_invalid_skill(tmp_path: Path):
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "skill.yaml").write_text("description: no name\n", encoding="utf-8")
    manager = SkillManager(tmp_path)
    assert manager.list_skills() == []
    with pytest.raises(KeyError):
        manager.enable_skill("missing")
