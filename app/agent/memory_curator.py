from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.memory import MemoryStore
from app.llm.api_client import ChatMessage, OpenAICompatibleClient
from app.storage.chat_history import ChatHistoryEntry


DEFAULT_AUTO_MEMORY_TRIGGER_TURNS = 8
DEFAULT_AUTO_MEMORY_BACKFILL_LIMIT = 200


@dataclass(frozen=True)
class MemoryCurationSettings:
    enabled: bool = True
    trigger_turns: int = DEFAULT_AUTO_MEMORY_TRIGGER_TURNS
    backfill_limit: int = DEFAULT_AUTO_MEMORY_BACKFILL_LIMIT


@dataclass(frozen=True)
class MemoryCurationResult:
    created: int = 0
    updated: int = 0
    archived: int = 0
    ignored: int = 0
    processed_entries: int = 0

    def summary(self) -> str:
        return (
            f"整理完成：新增 {self.created} 条，更新 {self.updated} 条，"
            f"归档 {self.archived} 条，忽略 {self.ignored} 条。"
        )


class MemoryCurationState:
    """记录自动整理进度，避免重复处理历史。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def snapshot(self) -> dict[str, Any]:
        if not self.path.exists():
            return _normalize_state({})
        try:
            raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _normalize_state({})
        return _normalize_state(raw_data)

    def pending_turns(self) -> int:
        return int(self.snapshot()["pending_turns"])

    def increment_pending_turns(self) -> int:
        state = self.snapshot()
        state["pending_turns"] = int(state["pending_turns"]) + 1
        self._save(state)
        return int(state["pending_turns"])

    def mark_processed(
        self,
        processed_history_count: int,
        *,
        consumed_turns: int = 0,
        backfill_completed: bool | None = None,
    ) -> None:
        state = self.snapshot()
        state["processed_history_count"] = max(0, processed_history_count)
        state["pending_turns"] = max(0, int(state["pending_turns"]) - max(0, consumed_turns))
        if backfill_completed is not None:
            state["backfill_completed"] = bool(backfill_completed)
        self._save(state)

    def mark_history_cleared(self) -> None:
        state = self.snapshot()
        state["processed_history_count"] = 0
        state["pending_turns"] = 0
        state["backfill_completed"] = True
        self._save(state)

    def unprocessed_entries(self, entries: list[ChatHistoryEntry]) -> list[ChatHistoryEntry]:
        state = self.snapshot()
        processed = int(state["processed_history_count"])
        if processed < 0 or processed > len(entries):
            processed = 0
        return entries[processed:]

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(_normalize_state(state), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


class MemoryCurator:
    """调用模型把聊天历史整理为长期记忆操作。"""

    def __init__(
        self,
        api_client: OpenAICompatibleClient,
        memory_store: MemoryStore,
    ) -> None:
        self.api_client = api_client
        self.memory_store = memory_store

    def curate_entries(self, entries: list[ChatHistoryEntry]) -> MemoryCurationResult:
        history = _entries_for_model(entries)
        if not history:
            return MemoryCurationResult(processed_entries=len(entries))

        content = self.api_client.complete_raw(
            _build_memory_curation_prompt(self.memory_store.snapshot()["memories"]),
            [{"role": "user", "content": json.dumps({"history": history}, ensure_ascii=False)}],
            temperature=0.2,
        )
        operations = _parse_operations(content)
        counts = self.memory_store.apply_curation_operations(operations)
        return MemoryCurationResult(
            created=counts["created"],
            updated=counts["updated"],
            archived=counts["archived"],
            ignored=counts["ignored"],
            processed_entries=len(entries),
        )


def _build_memory_curation_prompt(memories: list[dict[str, Any]]) -> str:
    existing_memories = json.dumps(memories, ensure_ascii=False, indent=2)
    return f"""
你是 Sakura 的长期记忆整理器。你只负责从聊天历史中提炼长期有用的信息，并输出 JSON。
不要输出 Markdown，不要解释，不要生成角色回复。

现有长期记忆：
{existing_memories}

可用分类：
- preference：用户稳定偏好，例如语言、称呼、回复风格、工具习惯。
- project：项目状态、技术栈、长期任务目标。
- habit：反复出现的行为习惯或工作方式。
- fact：稳定事实。
- relationship：用户与 Sakura 的关系、称呼、互动边界、长期相处上下文。

整理规则：
- 只记录未来多轮对话仍有帮助的信息。
- 不记录一次性闲聊、临时情绪、玩笑、未确认猜测、普通问答过程。
- 如果新信息与已有记忆重复，用 update；如果只是再次出现同一事实，也可以 update 提升重要度或置信度。
- 如果发现已有记忆过时或冲突，用 archive。
- 严禁记录密码、API Key、token、银行卡、身份证件号、支付信息等敏感凭据。
- importance 和 confidence 必须是 0 到 1 之间的小数。

只返回如下 JSON：
{{
  "operations": [
    {{
      "action": "create",
      "category": "preference",
      "content": "要保存的长期记忆",
      "importance": 0.8,
      "confidence": 0.9
    }},
    {{
      "action": "update",
      "id": "已有记忆 id",
      "content": "更新后的内容",
      "importance": 0.8,
      "confidence": 0.9
    }},
    {{
      "action": "archive",
      "id": "已有记忆 id"
    }},
    {{
      "action": "ignore"
    }}
  ]
}}
""".strip()


def _entries_for_model(entries: list[ChatHistoryEntry]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for entry in entries:
        if entry.role not in {"user", "assistant"}:
            continue
        content = entry.content.strip()
        if not content:
            continue
        result.append(
            {
                "created_at": entry.created_at,
                "role": entry.role,
                "content": content,
                "translation": entry.translation.strip(),
            }
        )
    return result


def _parse_operations(content: str) -> list[dict[str, Any]]:
    data = json.loads(_strip_code_fence(content.strip()))
    if not isinstance(data, dict):
        raise ValueError("记忆整理结果必须是 JSON object。")
    operations = data.get("operations", [])
    if not isinstance(operations, list):
        raise ValueError("记忆整理结果缺少 operations 列表。")
    return [operation for operation in operations if isinstance(operation, dict)]


def _strip_code_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def _normalize_state(raw_data: Any) -> dict[str, Any]:
    data = raw_data if isinstance(raw_data, dict) else {}
    return {
        "processed_history_count": max(0, _int_value(data.get("processed_history_count"), default=0)),
        "pending_turns": max(0, _int_value(data.get("pending_turns"), default=0)),
        "backfill_completed": bool(data.get("backfill_completed", False)),
    }


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
