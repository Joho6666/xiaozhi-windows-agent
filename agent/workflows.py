"""Local YAML workflows that orchestrate registered tools only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent.registry import ToolRegistry


class WorkflowManager:
    def __init__(self, workflows_dir: Path, registry: ToolRegistry) -> None:
        self.workflows_dir = workflows_dir
        self.registry = registry
        self._workflows: dict[str, dict[str, Any]] = {}
        self.discover()

    def discover(self) -> list[dict[str, Any]]:
        self._workflows = {}
        if not self.workflows_dir.exists():
            return []
        for path in sorted(self.workflows_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not isinstance(raw.get("steps"), list):
                continue
            steps = [step for step in raw["steps"] if isinstance(step, str) or isinstance(step, dict)]
            if len(steps) != len(raw["steps"]):
                continue
            self._workflows[raw["name"]] = {"name": raw["name"], "description": str(raw.get("description", "")), "steps": steps, "path": str(path)}
        return self.list_workflows()

    def list_workflows(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._workflows.values()]

    async def run(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        workflow = self._workflows.get(name)
        if workflow is None:
            return {"success": False, "tool": "run_workflow", "error_code": "WORKFLOW_NOT_FOUND", "message": f"Workflow not found: {name}"}
        results: list[dict[str, Any]] = []
        shared = arguments or {}
        for index, raw_step in enumerate(workflow["steps"], 1):
            if isinstance(raw_step, str):
                tool_name, step_args = raw_step, shared
            else:
                tool_name = raw_step.get("tool")
                step_args = dict(shared)
                step_args.update(raw_step.get("arguments", {}))
            if not isinstance(tool_name, str) or self.registry.get_tool(tool_name) is None:
                result = {"success": False, "error_code": "UNKNOWN_WORKFLOW_TOOL", "message": f"Tool is not registered: {tool_name}"}
            else:
                try:
                    result = await self.registry.execute(tool_name, step_args)
                except Exception as exc:  # noqa: BLE001 - workflow returns a business error
                    result = {"success": False, "error_code": "WORKFLOW_STEP_FAILED", "message": str(exc)}
            results.append({"step": index, "tool": tool_name, "result": result})
            if not result.get("success", False):
                return {"success": False, "tool": "run_workflow", "message": "Workflow stopped after a failed step", "failed_step": index, "steps": results}
        return {"success": True, "tool": "run_workflow", "message": "Workflow completed", "steps": results}

