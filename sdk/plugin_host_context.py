from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginHostContext:
    """插件初始化时可读取的 Sakura 宿主上下文。"""

    base_dir: Path

