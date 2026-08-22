"""Local, declarative Skill discovery with no network or permission escalation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SkillManager:
    def __init__(self, skills_dir: Path, enabled: list[str] | None = None) -> None:
        self.skills_dir = skills_dir
        self._enabled = set(enabled or [])
        self._skills: dict[str, dict[str, Any]] = {}
        self.discover()

    def discover(self) -> list[dict[str, Any]]:
        self._skills = {}
        if not self.skills_dir.exists():
            return []
        for directory in sorted(self.skills_dir.iterdir()):
            if not directory.is_dir():
                continue
            manifest_path = directory / "skill.yaml"
            if not manifest_path.is_file():
                continue
            try:
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
                continue
            name = raw["name"].strip()
            tools = raw.get("tools", [])
            workspaces = raw.get("workspaces", [])
            if not isinstance(tools, list) or not isinstance(workspaces, list):
                continue
            self._skills[name] = {
                "name": name,
                "description": str(raw.get("description", "")),
                "tools": [str(item) for item in tools],
                "workspaces": [str(item) for item in workspaces],
                "path": str(directory),
                "documentation": str(directory / "SKILL.md") if (directory / "SKILL.md").is_file() else None,
                "enabled": name in self._enabled,
            }
        return self.list_skills()

    def list_skills(self) -> list[dict[str, Any]]:
        return [dict(skill) for skill in self._skills.values()]

    def get_skill(self, name: str) -> dict[str, Any]:
        if name not in self._skills:
            raise KeyError(name)
        return dict(self._skills[name])

    def enable_skill(self, name: str) -> dict[str, Any]:
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(name)
        self._enabled.add(name)
        skill["enabled"] = True
        return dict(skill)

    def disable_skill(self, name: str) -> dict[str, Any]:
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(name)
        self._enabled.discard(name)
        skill["enabled"] = False
        return dict(skill)

