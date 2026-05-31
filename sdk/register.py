from __future__ import annotations

from dataclasses import dataclass, field

from sdk.types import ToolsTabContribution


@dataclass
class PluginCapabilityRegistry:
    """收集插件贡献的能力。"""

    tools_tabs: list[ToolsTabContribution] = field(default_factory=list)

    def register_tools_tab(self, contribution: ToolsTabContribution) -> None:
        self.tools_tabs.append(contribution)

