from __future__ import annotations

from app.agent import AgentEvent, AgentResult, PendingToolAction
from app.core.chat_pipeline import ChatPipeline
from app.llm.chat_reply import parse_chat_reply


class RuntimeStub:
    api_client = object()

    def __init__(self) -> None:
        self.calls: list[str] = []

    def handle_user_message(self, messages, progress_callback=None):  # type: ignore[no-untyped-def]
        self.calls.append(f"user:{len(messages)}")
        if progress_callback is not None:
            progress_callback
        return AgentResult(parse_chat_reply("はい"), [])

    def handle_confirmed_action(self, action, progress_callback=None):  # type: ignore[no-untyped-def]
        self.calls.append(f"confirmed:{action.tool_name}")
        return AgentResult(parse_chat_reply("確認したよ"), [])

    def handle_cancelled_action(self, action):  # type: ignore[no-untyped-def]
        self.calls.append(f"cancelled:{action.tool_name}")
        return AgentResult(parse_chat_reply("やめたよ"), [])

    def handle_event(self, event, progress_callback=None):  # type: ignore[no-untyped-def]
        self.calls.append(f"event:{event.type}")
        return AgentResult(parse_chat_reply("見たよ"), [])


def test_chat_pipeline_delegates_chat_actions() -> None:
    runtime = RuntimeStub()
    pipeline = ChatPipeline(runtime)  # type: ignore[arg-type]
    action = PendingToolAction.create("demo_tool", {}, "测试")

    pipeline.run_user_message([{"role": "user", "content": "你好"}])
    pipeline.run_confirmed_action(action)
    pipeline.run_cancelled_action(action)
    pipeline.run_event(AgentEvent(type="timer", payload={}))

    assert runtime.calls == [
        "user:1",
        "confirmed:demo_tool",
        "cancelled:demo_tool",
        "event:timer",
    ]
