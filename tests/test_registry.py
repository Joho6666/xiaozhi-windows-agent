from agent.registry import RiskLevel, Tool, ToolRegistry


def test_registry_register_list_and_schema():
    registry = ToolRegistry()
    tool = Tool("demo", "demo tool", {"type": "object"}, lambda _: {"success": True}, RiskLevel.LOW)
    registry.register(tool)
    assert registry.get_tool("demo") is tool
    assert registry.list_tools() == [{"name": "demo", "description": "demo tool", "inputSchema": {"type": "object"}}]


def test_registry_rejects_duplicates():
    registry = ToolRegistry()
    tool = Tool("demo", "demo", {}, lambda _: {}, RiskLevel.LOW)
    registry.register(tool)
    try:
        registry.register(tool)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate tool was accepted")


def test_registry_supports_category_timeout_and_unregister():
    registry = ToolRegistry()
    tool = Tool("demo", "demo", {}, lambda _: {"success": True}, RiskLevel.LOW, category="system", timeout=2.0)
    registry.register_tool(tool)
    assert registry.get_tool("demo").category == "system"
    assert registry.get_tool("demo").timeout == 2.0
    assert registry.unregister_tool("demo") is True
    assert registry.get_tool("demo") is None


def test_registry_execute_adds_uniform_result_metadata():
    import asyncio

    registry = ToolRegistry()
    registry.register(Tool("demo", "demo", {}, lambda _: {"success": True, "message": "done"}, RiskLevel.LOW))
    result = asyncio.run(registry.execute("demo", {}))
    assert result["tool"] == "demo"
    assert result["success"] is True
    assert result["message"] == "done"
    assert isinstance(result["duration_ms"], int)
