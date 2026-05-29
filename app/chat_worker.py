from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from app.agent import AgentResult, AgentRuntime, PendingToolAction


class ChatWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        agent_runtime: AgentRuntime,
        messages: list[dict[str, str]] | None = None,
        confirmed_action: PendingToolAction | None = None,
        cancelled_action: PendingToolAction | None = None,
    ) -> None:
        super().__init__()
        self.agent_runtime = agent_runtime
        self.messages = messages or []
        self.confirmed_action = confirmed_action
        self.cancelled_action = cancelled_action

    @Slot()
    def run(self) -> None:
        try:
            if self.confirmed_action is not None:
                result: AgentResult = self.agent_runtime.handle_confirmed_action(self.confirmed_action)
            elif self.cancelled_action is not None:
                result = self.agent_runtime.handle_cancelled_action(self.cancelled_action)
            else:
                result = self.agent_runtime.handle_user_message(self.messages)
        except Exception as exc:  # UI 边界统一转成可读错误。
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
