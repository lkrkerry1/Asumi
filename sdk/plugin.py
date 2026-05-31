from __future__ import annotations

from pathlib import Path

from sdk.plugin_host_context import PluginHostContext
from sdk.register import PluginCapabilityRegistry


class PluginBase:
    """Shinsekai 插件基类的最小兼容实现。"""

    @property
    def plugin_id(self) -> str:
        raise NotImplementedError

    @property
    def plugin_version(self) -> str:
        return "0.0.0"

    def initialize(
        self,
        register: PluginCapabilityRegistry,
        plugin_root: Path,
        host: PluginHostContext,
    ) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        return None

