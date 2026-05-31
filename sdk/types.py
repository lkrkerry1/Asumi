from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolsTabContribution:
    """插件贡献到设置窗口“工具”页的设置区。"""

    tab_id: str
    title: str
    build: Callable[[Any], Any]
    order: float = 100.0

