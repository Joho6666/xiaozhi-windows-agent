"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class PermissionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile: Literal["safe", "power", "unrestricted", "full", "open"] = "safe"
    low: Literal["auto", "confirm", "deny"] = "auto"
    medium: Literal["auto", "confirm", "deny"] = "confirm"
    high: Literal["auto", "confirm", "deny"] = "deny"
    blocked: Literal["auto", "confirm", "deny"] = "deny"


class DirectoryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed_roots: list[str] = Field(default_factory=lambda: ["Desktop", "Documents", "Downloads", "."])
    max_entries: int = Field(default=100, ge=1, le=1000)


class CommandRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    executable: str
    args: list[str] = Field(default_factory=list)

    @field_validator("executable")
    @classmethod
    def executable_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char in value for char in "|&><;`\n\r"):
            raise ValueError("command executable must be a safe, non-empty token")
        return value


class CommandConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_output_chars: int = Field(default=4000, ge=100, le=100_000)
    allowed: list[CommandRule] = Field(default_factory=list)


class FileConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed_extensions: set[str] = Field(default_factory=lambda: {".txt", ".md", ".json", ".yaml", ".yml", ".py", ".js", ".ts", ".cpp", ".c", ".h", ".java", ".csv"})
    max_file_bytes: int = Field(default=1_000_000, ge=1_024, le=50_000_000)
    max_return_chars: int = Field(default=12_000, ge=500, le=100_000)
    max_results: int = Field(default=100, ge=1, le=1_000)


class ReconnectConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    delays_seconds: list[float] = Field(default_factory=lambda: [1, 2, 4, 8, 15, 30])

    @field_validator("delays_seconds")
    @classmethod
    def delays_are_valid(cls, value: list[float]) -> list[float]:
        if not value or any(delay <= 0 for delay in value):
            raise ValueError("reconnect delays must contain positive values")
        return value


class BrowserConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    headless: bool = False
    search_engine: Literal["bing", "google"] = "bing"
    page_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    max_results: int = Field(default=5, ge=1, le=20)
    max_text_chars: int = Field(default=5000, ge=500, le=50_000)
    allowed_domains: list[str] = Field(default_factory=list)


class WorkspaceEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled_tools: list[str] = Field(default_factory=lambda: ["open_application", "list_directory", "run_command"])
    permissions: PermissionConfig = Field(default_factory=PermissionConfig)
    confirm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    directories: DirectoryConfig = Field(default_factory=DirectoryConfig)
    commands: CommandConfig = Field(default_factory=CommandConfig)
    files: FileConfig = Field(default_factory=FileConfig)
    reconnect: ReconnectConfig = Field(default_factory=ReconnectConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    workspaces: dict[str, WorkspaceEntry] = Field(default_factory=dict)
    enabled_skills: list[str] = Field(default_factory=list)
    protocol_mode: Literal["plain_jsonrpc", "xiaozhi_envelope"] = "plain_jsonrpc"
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class Settings(BaseModel):
    endpoint: str
    log_level: str = "INFO"
    project_dir: Path
    config: AppConfig


def _resolve_path(value: str, project_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def load_settings(project_dir: Path | None = None) -> Settings:
    """Load .env and config.yaml without ever logging the endpoint."""
    project_dir = (project_dir or Path.cwd()).resolve()
    load_dotenv(project_dir / ".env", override=False)

    endpoint = os.getenv("XIAOZHI_MCP_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError("XIAOZHI_MCP_ENDPOINT is missing; copy .env.example to .env and configure it")
    if not endpoint.startswith(("ws://", "wss://")):
        raise ValueError("XIAOZHI_MCP_ENDPOINT must start with ws:// or wss://")

    config_path = project_dir / "config.yaml"
    raw: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("config.yaml must contain a YAML mapping")
        raw = loaded

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid config.yaml: {exc}") from exc

    config.directories.allowed_roots = [
        str(_resolve_path(root, project_dir)) if root == "." else root
        for root in config.directories.allowed_roots
    ]
    return Settings(
        endpoint=endpoint,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        project_dir=project_dir,
        config=config,
    )
