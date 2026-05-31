from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from app.agent.mcp.config import MCPConfig


WINDOWS_MCP_ENABLED_KEY = "WINDOWS_MCP_ENABLED"


@dataclass(frozen=True)
class MCPRuntimeSettings:
    """MCP 运行时开关；由 data/config/system_config.yaml 提供。"""

    windows_enabled: bool = False


def apply_mcp_runtime_settings(
    config: MCPConfig,
    settings: MCPRuntimeSettings,
) -> MCPConfig:
    """按运行时开关覆盖需要重启加载的 MCP server。"""

    servers = [
        replace(server, enabled=settings.windows_enabled)
        if server.name == "windows"
        else server
        for server in config.servers
    ]
    return replace(config, servers=servers)
