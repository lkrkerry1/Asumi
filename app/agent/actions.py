from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

from app.chat_reply import ChatReply


@dataclass(frozen=True)
class AgentAction:
    """Agent 决策出的外部动作。"""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryUpdate:
    """候选长期记忆更新，用于 UI 或调用方决定是否提示用户。"""

    id: str
    category: str
    content: str
    reason: str = ""


@dataclass(frozen=True)
class AgentEvent:
    """运行时主动事件，例如提醒到期。"""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PendingToolAction:
    """等待用户确认后才执行的工具动作。"""

    id: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    created_at: str

    @classmethod
    def create(
        cls,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str = "",
    ) -> "PendingToolAction":
        return cls(
            id=uuid.uuid4().hex[:8],
            tool_name=tool_name,
            arguments=dict(arguments),
            reason=reason,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingToolAction":
        action_id = data.get("id")
        tool_name = data.get("tool_name")
        arguments = data.get("arguments", {})
        reason = data.get("reason", "")
        created_at = data.get("created_at")
        if not isinstance(action_id, str) or not action_id.strip():
            raise ValueError("待确认动作缺少 id。")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("待确认动作缺少工具名。")
        if not isinstance(arguments, dict):
            raise ValueError("待确认动作参数必须是 JSON object。")
        if not isinstance(reason, str):
            reason = ""
        if not isinstance(created_at, str) or not created_at.strip():
            created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        return cls(
            id=action_id.strip(),
            tool_name=tool_name.strip(),
            arguments=dict(arguments),
            reason=reason.strip(),
            created_at=created_at.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class AgentResult:
    """Agent Runtime 的统一输出，供 UI 根据回复、动作和记忆更新分别处理。"""

    reply: ChatReply
    actions: list[AgentAction] = field(default_factory=list)
    memory_updates: list[MemoryUpdate] = field(default_factory=list)
