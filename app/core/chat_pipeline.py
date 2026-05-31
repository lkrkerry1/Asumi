from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent import AgentEvent, AgentProgress, AgentResult, AgentRuntime, PendingToolAction
from app.debug_log import debug_log, summarize_messages
from app.storage.visual_observation import (
    VisualObservationJob,
    VisualObservationStore,
    summarize_visual_observation,
)


ProgressCallback = Callable[[AgentProgress], None]


class ChatPipeline:
    """封装对话运行管线，让 Qt Worker 只保留线程和信号职责。"""

    def __init__(
        self,
        agent_runtime: AgentRuntime,
        visual_observation_store: VisualObservationStore | None = None,
    ) -> None:
        self.agent_runtime = agent_runtime
        self.visual_observation_store = visual_observation_store

    def run_user_message(
        self,
        messages: list[dict[str, Any]],
        *,
        visual_observation_jobs: list[VisualObservationJob] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AgentResult:
        self._record_visual_observations("ChatWorker", visual_observation_jobs or [])
        debug_log(
            "ChatWorker",
            "开始处理用户消息",
            {
                "message_count": len(messages),
                "messages": summarize_messages(messages),
            },
        )
        return self.agent_runtime.handle_user_message(
            messages,
            progress_callback=progress_callback,
        )

    def run_confirmed_action(
        self,
        action: PendingToolAction,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> AgentResult:
        debug_log("ChatWorker", "开始处理已确认动作", action.to_dict())
        return self.agent_runtime.handle_confirmed_action(
            action,
            progress_callback=progress_callback,
        )

    def run_cancelled_action(self, action: PendingToolAction) -> AgentResult:
        debug_log("ChatWorker", "开始处理已取消动作", action.to_dict())
        return self.agent_runtime.handle_cancelled_action(action)

    def run_event(
        self,
        event: AgentEvent,
        *,
        visual_observation_jobs: list[VisualObservationJob] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AgentResult:
        self._record_visual_observations("EventWorker", visual_observation_jobs or [])
        debug_log(
            "EventWorker",
            "开始处理主动事件",
            {
                "type": event.type,
                "payload": event.payload,
            },
        )
        return self.agent_runtime.handle_event(
            event,
            progress_callback=progress_callback,
        )

    def _record_visual_observations(
        self,
        log_scope: str,
        visual_observation_jobs: list[VisualObservationJob],
    ) -> None:
        if self.visual_observation_store is None or not visual_observation_jobs:
            return
        for job in visual_observation_jobs:
            record = summarize_visual_observation(self.agent_runtime.api_client, job)
            self.visual_observation_store.append(record)
            debug_log(
                log_scope,
                "视觉观察记录已保存",
                {
                    "visual_id": record.id,
                    "source": record.source,
                    "summary": record.summary,
                    "visible_text_count": len(record.visible_texts),
                    "sensitive_redacted": record.sensitive_redacted,
                },
            )
