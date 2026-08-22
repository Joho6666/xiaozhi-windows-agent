import asyncio

from agent.registry import RiskLevel
from security.permissions import PermissionDecision, PermissionManager


def test_low_is_automatic():
    manager = PermissionManager({"low": "auto", "medium": "confirm", "high": "deny"})
    assert asyncio.run(manager.check(RiskLevel.LOW, "open_application")) is PermissionDecision.ALLOW


def test_medium_confirmation_and_high_block():
    yes = PermissionManager({"low": "auto", "medium": "confirm", "high": "deny"}, input_func=lambda _: "y")
    no = PermissionManager({"low": "auto", "medium": "confirm", "high": "deny"}, input_func=lambda _: "n")
    assert asyncio.run(yes.check(RiskLevel.MEDIUM, "run_command")) is PermissionDecision.ALLOW
    assert asyncio.run(no.check(RiskLevel.MEDIUM, "run_command")) is PermissionDecision.DENY
    assert asyncio.run(yes.check(RiskLevel.HIGH, "write_file")) is PermissionDecision.DENY
    assert asyncio.run(yes.check(RiskLevel.BLOCKED, "format")) is PermissionDecision.DENY


def test_power_profile_allows_medium_but_still_confirms_high():
    manager = PermissionManager({"profile": "power", "low": "auto", "medium": "confirm", "high": "deny"}, input_func=lambda _: "y")
    assert asyncio.run(manager.check(RiskLevel.MEDIUM, "browser_click")) is PermissionDecision.ALLOW
    assert asyncio.run(manager.check(RiskLevel.HIGH, "modify_files")) is PermissionDecision.ALLOW
    assert asyncio.run(PermissionManager({"profile": "power"}).check(RiskLevel.BLOCKED, "read_cookie")) is PermissionDecision.DENY
