"""Risk-based permission gate for local tool execution."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from agent.registry import RiskLevel


class PermissionDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class PermissionManager:
    def __init__(
        self,
        policies: dict[str, str] | Any,
        confirm_timeout_seconds: float = 30.0,
        input_func: Callable[[str], str] = input,
    ) -> None:
        profile = getattr(policies, "profile", policies.get("profile", "safe") if isinstance(policies, dict) else "safe")
        self.policies = {
            "LOW": getattr(policies, "low", policies.get("low", "auto") if isinstance(policies, dict) else "auto"),
            "MEDIUM": getattr(policies, "medium", policies.get("medium", "confirm") if isinstance(policies, dict) else "confirm"),
            "HIGH": getattr(policies, "high", policies.get("high", "deny") if isinstance(policies, dict) else "deny"),
            "BLOCKED": "deny",
        }
        if profile == "power":
            self.policies["MEDIUM"] = "auto"
            self.policies["HIGH"] = "confirm"
        elif profile in {"unrestricted", "full", "open"}:
            self.policies["LOW"] = "auto"
            self.policies["MEDIUM"] = "auto"
            self.policies["HIGH"] = "auto"
            self.policies["BLOCKED"] = "auto"
        self.confirm_timeout_seconds = confirm_timeout_seconds
        self.input_func = input_func

    async def check(self, risk_level: RiskLevel, request_description: str) -> PermissionDecision:
        policy = self.policies.get(risk_level.value, "deny")
        if (risk_level is RiskLevel.BLOCKED and policy != "auto") or policy == "deny":
            return PermissionDecision.DENY
        if policy == "auto":
            return PermissionDecision.ALLOW
        if policy != "confirm":
            return PermissionDecision.DENY
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(self.input_func, f"\nAgent requests: {request_description}\nAllow? [y/N] "),
                timeout=self.confirm_timeout_seconds,
            )
        except (asyncio.TimeoutError, EOFError, KeyboardInterrupt):
            return PermissionDecision.DENY
        return PermissionDecision.ALLOW if answer.strip().lower() in {"y", "yes"} else PermissionDecision.DENY
