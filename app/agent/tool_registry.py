from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent.actions import PendingToolAction
from app.debug_log import debug_log


ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class Tool:
    """内部工具定义。"""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None
    requires_confirmation: bool = False
    confirmation_risk: str = "normal"
    group: str = "default"
    risk: str = "low"
    capability: str | None = None


@dataclass(frozen=True)
class ToolExecutionResult:
    """工具执行结果，统一交回模型做最终表述。"""

    tool_name: str
    success: bool
    content: Any
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "tool_name": self.tool_name,
            "success": self.success,
            "content": self.content,
        }
        if self.error:
            data["error"] = self.error
        return data


class ToolRegistry:
    """管理 Agent 可用工具，后续 MCP Provider 会挂到这一层。"""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self.free_access_enabled = True
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        debug_log(
            "ToolRegistry",
            "注册工具",
            {
                "name": tool.name,
                "group": tool.group,
                "risk": tool.risk,
                "requires_confirmation": tool.requires_confirmation,
            },
        )

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def describe_tools(
        self,
        allowed_capabilities: set[str] | None = None,
        active_groups: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """返回可暴露给模型的工具描述；可按能力开关和工具组隐藏工具。"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "requires_confirmation": tool.requires_confirmation,
                "group": tool.group,
                "risk": tool.risk,
            }
            for tool in self.all()
            if self._tool_is_visible(
                tool,
                allowed_capabilities=allowed_capabilities,
                active_groups=active_groups,
            )
        ]

    def describe_openai_tools(
        self,
        allowed_capabilities: set[str] | None = None,
        active_groups: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """返回 OpenAI Chat Completions 原生 function tools 定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": _normalize_parameters_schema(tool.parameters),
                },
            }
            for tool in self.all()
            if self._tool_is_visible(
                tool,
                allowed_capabilities=allowed_capabilities,
                active_groups=active_groups,
            )
        ]

    def search_tools(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        keyword = str(arguments.get("keyword") or "").strip().lower()
        results: list[dict[str, Any]] = []
        for tool in self.all():
            if tool.name in {"search_tools", "list_tool_groups"}:
                continue
            if keyword and not _tool_matches_keyword(tool, keyword):
                continue
            results.append(
                {
                    "name": tool.name,
                    "group": tool.group,
                    "description": tool.description,
                    "risk": tool.risk,
                    "requires_confirmation": tool.requires_confirmation,
                }
            )
        return results

    def list_tool_groups(self, _arguments: dict[str, Any]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for tool in self.all():
            counts[tool.group] = counts.get(tool.group, 0) + 1
        return [
            {"group": group, "tool_count": count}
            for group, count in sorted(counts.items())
        ]

    def groups(self) -> set[str]:
        return {tool.group for tool in self.all()}

    def _tool_is_visible(
        self,
        tool: Tool,
        *,
        allowed_capabilities: set[str] | None,
        active_groups: set[str] | None,
    ) -> bool:
        capability_visible = (
            allowed_capabilities is None
            or tool.capability is None
            or tool.capability in allowed_capabilities
        )
        if not capability_visible:
            return False
        if active_groups is None:
            return True
        if tool.capability is not None and allowed_capabilities and tool.capability in allowed_capabilities:
            return True
        return tool.group in active_groups

    def set_free_access_enabled(self, enabled: bool) -> None:
        """开启后普通确认工具直接执行，文件删除类高风险工具仍保留确认。"""
        self.free_access_enabled = enabled

    def prepare_or_execute(
        self,
        name: str,
        arguments: dict[str, Any],
        reason: str = "",
        tool_call_id: str = "",
    ) -> ToolExecutionResult | PendingToolAction:
        tool = self.get(name)
        debug_log(
            "ToolRegistry",
            "准备工具执行",
            {
                "name": name,
                "known": tool is not None,
                "requires_confirmation": tool.requires_confirmation if tool is not None else False,
                "free_access_enabled": self.free_access_enabled,
                "arguments": arguments,
                "reason": reason,
            },
        )
        if tool is None or not tool.requires_confirmation:
            return self.execute(name, arguments)
        if self.free_access_enabled and _can_execute_with_free_access(tool):
            debug_log("ToolRegistry", "自由访问模式直接执行确认工具", {"name": name})
            return self.execute(name, arguments)
        if not isinstance(arguments, dict):
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error="工具参数必须是 JSON object。",
            )
            debug_log("ToolRegistry", "工具参数无效", result.to_dict())
            return result
        action = PendingToolAction.create(
            tool_name=name,
            arguments=arguments,
            reason=reason,
            tool_call_id=tool_call_id,
        )
        debug_log("ToolRegistry", "工具等待用户确认", action.to_dict())
        return action

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        started_at = time.perf_counter()
        tool = self.get(name)
        if tool is None:
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error=f"未知工具：{name}",
            )
            debug_log("ToolRegistry", "工具执行失败", _result_with_elapsed(result, started_at))
            return result
        if tool.handler is None:
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error=f"工具未配置处理器：{name}",
            )
            debug_log("ToolRegistry", "工具执行失败", _result_with_elapsed(result, started_at))
            return result
        if not isinstance(arguments, dict):
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error="工具参数必须是 JSON object。",
            )
            debug_log("ToolRegistry", "工具执行失败", _result_with_elapsed(result, started_at))
            return result

        try:
            debug_log(
                "ToolRegistry",
                "开始执行工具",
                {
                    "name": name,
                    "group": tool.group,
                    "risk": tool.risk,
                    "arguments": arguments,
                },
            )
            content = tool.handler(arguments)
        except Exception as exc:
            result = ToolExecutionResult(
                tool_name=name,
                success=False,
                content="",
                error=str(exc),
            )
            debug_log("ToolRegistry", "工具执行异常", _result_with_elapsed(result, started_at))
            return result
        result = ToolExecutionResult(
            tool_name=name,
            success=True,
            content=content,
        )
        debug_log("ToolRegistry", "工具执行成功", _result_with_elapsed(result, started_at))
        return result


def _can_execute_with_free_access(tool: Tool) -> bool:
    """识别完整访问权限下可直接执行的确认工具。"""
    if _requires_confirmation_despite_free_access(tool):
        return False
    if _is_browser_free_access_tool(tool.name):
        return True
    return True


def _is_browser_free_access_tool(name: str) -> bool:
    """浏览器原生 Playwright 操作在完整访问权限下可直接执行。"""
    return name in {
        "playwright_navigate",
        "playwright_get_text",
        "playwright_search_web",
        "playwright_screenshot",
        "playwright_click",
        "playwright_fill",
        "playwright_evaluate",
    }


def _tool_matches_keyword(tool: Tool, keyword: str) -> bool:
    haystack = "\n".join(
        [
            tool.name,
            tool.group,
            tool.description,
        ]
    ).lower()
    return keyword in haystack


def _normalize_parameters_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    if not parameters:
        return {"type": "object", "properties": {}, "required": []}
    if parameters.get("type") == "object":
        schema = dict(parameters)
        schema.setdefault("properties", {})
        schema.setdefault("required", [])
        normalized = _sanitize_openai_schema(schema)
        return normalized if isinstance(normalized, dict) else {"type": "object", "properties": {}, "required": []}
    return {
        "type": "object",
        "properties": _sanitize_schema_properties(dict(parameters)),
        "required": [],
    }


def _sanitize_openai_schema(schema: Any) -> Any:
    """把内部 JSON Schema 收窄成兼容常见 OpenAI-compatible 端点的 function schema。"""
    if isinstance(schema, list):
        return [_sanitize_openai_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    sanitized: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            sanitized[key] = _sanitize_schema_properties(value)
            continue
        if key == "required" and isinstance(value, list):
            sanitized[key] = [
                item
                for item in value
                if isinstance(item, str)
            ]
            continue
        if key == "type":
            normalized_type = _sanitize_schema_type(value)
            if normalized_type is None:
                continue
            sanitized[key] = normalized_type
            if isinstance(value, list) and "null" in value:
                sanitized["nullable"] = True
            continue
        sanitized[key] = _sanitize_openai_schema(value)

    if "properties" in sanitized and isinstance(sanitized["properties"], dict):
        required = sanitized.get("required")
        if isinstance(required, list):
            sanitized["required"] = [
                item
                for item in required
                if item in sanitized["properties"]
            ]
    if "type" not in sanitized:
        if "properties" in sanitized:
            sanitized["type"] = "object"
        elif "items" in sanitized:
            sanitized["type"] = "array"
        elif "enum" in sanitized:
            sanitized["type"] = "string"
    return sanitized


def _sanitize_schema_properties(properties: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for name, property_schema in properties.items():
        if _is_null_only_schema(property_schema):
            continue
        sanitized_property = _sanitize_openai_schema(property_schema)
        if isinstance(sanitized_property, dict):
            sanitized[str(name)] = sanitized_property
    return sanitized


def _sanitize_schema_type(value: Any) -> str | None:
    if isinstance(value, str):
        return None if value == "null" else value
    if isinstance(value, list):
        non_null_types = [
            item
            for item in value
            if isinstance(item, str) and item != "null"
        ]
        if not non_null_types:
            return None
        return non_null_types[0]
    return None


def _is_null_only_schema(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    schema_type = schema.get("type")
    return schema_type == "null" or schema_type == ["null"]


def _requires_confirmation_despite_free_access(tool: Tool) -> bool:
    """识别完整访问权限也不能直接执行的高风险工具。"""
    if tool.risk == "high":
        return True
    if tool.confirmation_risk in {"delete_file", "file_delete", "destructive_file"}:
        return True
    normalized = tool.name.lower()
    return any(
        marker in normalized
        for marker in (
            "delete_file",
            "remove_file",
            "unlink_file",
            "delete_path",
            "remove_path",
            "delete_local_file",
            "remove_local_file",
        )
    )


def _result_with_elapsed(result: ToolExecutionResult, started_at: float) -> dict[str, Any]:
    data = result.to_dict()
    data["elapsed_ms"] = int((time.perf_counter() - started_at) * 1000)
    return data
