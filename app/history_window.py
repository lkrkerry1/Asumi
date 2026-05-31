from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QLabel,
    QDialog,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.chat_history import ChatHistoryEntry, ChatHistoryStore


@dataclass(frozen=True)
class HistoryEntryView:
    role_name: str
    align: str
    bubble_object_name: str
    meta_text: str
    content: str


class HistoryWindow(QDialog):
    def __init__(
        self,
        history_store: ChatHistoryStore,
        subtitle_language: str = "ja",
        on_save_and_clear: Callable[[], None] | None = None,
        parent=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self.history_store = history_store
        self.subtitle_language = subtitle_language
        self.on_save_and_clear = on_save_and_clear
        self._bubble_frames: list[QFrame] = []

        self.setWindowTitle("历史记录")
        self.resize(620, 680)

        self.title_label = QLabel("历史记录", self)
        self.title_label.setObjectName("historyTitle")

        self.count_label = QLabel("0 条记录", self)
        self.count_label.setObjectName("historyCount")

        self.history_view = QScrollArea(self)
        self.history_view.setObjectName("historyScroll")
        self.history_view.setWidgetResizable(True)
        self.history_view.setFrameShape(QFrame.Shape.NoFrame)

        self.history_content = QWidget(self.history_view)
        self.history_content.setObjectName("historyContent")
        self.history_layout = QVBoxLayout(self.history_content)
        self.history_layout.setContentsMargins(20, 14, 20, 14)
        self.history_layout.setSpacing(12)
        self.history_view.setWidget(self.history_content)

        self.refresh_button = QPushButton("刷新", self)
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.clicked.connect(self.refresh)

        self.clear_button = QPushButton("清空历史", self)
        self.clear_button.setObjectName("dangerButton")
        self.clear_button.clicked.connect(self.clear_history)

        self.save_and_clear_button = QPushButton("清除并保存至记忆", self)
        self.save_and_clear_button.setObjectName("primaryButton")
        self.save_and_clear_button.clicked.connect(self.save_and_clear_history)

        self.close_button = QPushButton("关闭", self)
        self.close_button.setObjectName("secondaryButton")
        self.close_button.clicked.connect(self.close)

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.count_label)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.save_and_clear_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.close_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(header_layout)
        layout.addWidget(self.history_view, 1)
        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            QDialog {
                background: #f4fbfd;
                color: #24343a;
                font-family: "Microsoft YaHei", "Yu Gothic UI", sans-serif;
                font-size: 16px;
            }
            QLabel#historyTitle {
                color: #1f3d46;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#historyCount {
                color: #668892;
                background: rgba(226, 246, 250, 0.72);
                border: 1px solid rgba(120, 176, 188, 0.36);
                border-radius: 12px;
                padding: 5px 10px;
                font-size: 13px;
            }
            QScrollArea#historyScroll {
                background: rgba(236, 250, 252, 0.92);
                border: 1px solid rgba(120, 176, 188, 0.50);
                border-radius: 14px;
            }
            QWidget#historyContent {
                background: transparent;
            }
            QFrame#assistantBubble {
                background: #f2fbfc;
                border: 1px solid #c9e8ee;
                border-radius: 14px;
            }
            QFrame#userBubble {
                background: #cdeff5;
                border: 1px solid #a7dbe4;
                border-radius: 14px;
            }
            QFrame#errorBubble {
                background: #ffe9e7;
                border: 1px solid #efc2bd;
                border-radius: 14px;
            }
            QFrame#systemBubble {
                background: #e7f3f5;
                border: 1px solid #cfe2e6;
                border-radius: 12px;
            }
            QLabel#entryMeta {
                color: #6a8f98;
                font-size: 13px;
            }
            QLabel#entryText {
                color: #24343a;
                font-size: 16px;
                line-height: 155%;
            }
            QLabel#errorText {
                color: #9f393a;
                font-size: 16px;
                line-height: 155%;
            }
            QLabel#systemText {
                color: #536b72;
                font-size: 15px;
                line-height: 155%;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(120, 176, 188, 0.50);
                border-radius: 8px;
                color: #315760;
                min-width: 72px;
                padding: 8px 12px;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(219, 244, 248, 0.95);
            }
            QPushButton#dangerButton {
                background: #fff3f2;
                border: 1px solid rgba(221, 122, 122, 0.52);
                color: #b4494a;
            }
            QPushButton#dangerButton:hover {
                background: #ffe5e3;
            }
            QPushButton#primaryButton {
                background: #5eb7c8;
                border: 1px solid rgba(65, 146, 161, 0.55);
                color: white;
            }
            QPushButton#primaryButton:hover {
                background: #4aa9bb;
            }
            QPushButton#secondaryButton:default {
                background: #5eb7c8;
            }
            """
        )
        self.refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if not hasattr(self, "history_view"):
            return
        self._update_bubble_widths()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._schedule_layout_update()

    def set_subtitle_language(self, subtitle_language: str) -> None:
        if subtitle_language == self.subtitle_language:
            return
        self.subtitle_language = subtitle_language
        self.refresh()

    def set_history_store(self, history_store: ChatHistoryStore, assistant_name: str) -> None:
        self.history_store = history_store
        self.history_store.assistant_name = assistant_name
        self.refresh()

    def refresh(self) -> None:
        entries = self.history_store.load()
        self.count_label.setText(f"{len(entries)} 条记录")
        self._clear_entries()

        if not entries:
            self._add_empty_state()
            return

        for entry in entries:
            self._add_entry(entry)
        self.history_layout.addStretch(1)
        self._schedule_layout_update()

    def clear_history(self) -> None:
        result = QMessageBox.question(
            self,
            "清空历史",
            "确定要清空全部历史记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.history_store.clear()
        self.refresh()

    def save_and_clear_history(self) -> None:
        if self.on_save_and_clear is None:
            QMessageBox.warning(self, "不可用", "当前没有可用的记忆整理器。")
            return
        entries = self.history_store.load()
        if not entries:
            self.refresh()
            return
        result = QMessageBox.question(
            self,
            "清除并保存至记忆",
            "会先让模型整理当前历史并写入长期记忆，成功后再清空历史。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.set_memory_save_busy(True)
        self.on_save_and_clear()

    def set_memory_save_busy(self, busy: bool) -> None:
        if not hasattr(self, "save_and_clear_button"):
            return
        self.save_and_clear_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.save_and_clear_button.setText("整理中..." if busy else "清除并保存至记忆")

    def _clear_entries(self) -> None:
        self._bubble_frames.clear()
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # deleteLater 会等事件循环空闲后才真正销毁；
                # 先隐藏并脱离父控件，避免刷新后旧内容短暂叠在空状态上。
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _add_empty_state(self) -> None:
        empty_label = QLabel("还没有历史记录\n等和桜聊过之后，这里会安静地收好对话。", self.history_content)
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setObjectName("systemText")
        empty_label.setWordWrap(True)
        self.history_layout.addStretch(1)
        self.history_layout.addWidget(empty_label)
        self.history_layout.addStretch(1)

    def _add_entry(self, entry: ChatHistoryEntry) -> None:
        view = _entry_view_model(entry, self.subtitle_language, self.history_store.assistant_name)

        row = QWidget(self.history_content)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        bubble = QFrame(row)
        bubble.setObjectName(view.bubble_object_name)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 12)
        bubble_layout.setSpacing(6)

        meta_label = QLabel(view.meta_text, bubble)
        meta_label.setObjectName("entryMeta")
        meta_label.setAlignment(_label_alignment(view.align))

        content_label = QLabel(view.content, bubble)
        content_label.setObjectName(_content_object_name(view.bubble_object_name))
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.PlainText)
        content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )

        bubble_layout.addWidget(meta_label)
        bubble_layout.addWidget(content_label)

        if view.align == "right":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        elif view.align == "center":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)

        self._bubble_frames.append(bubble)
        self.history_layout.addWidget(row)

    def _update_bubble_widths(self) -> None:
        width = self.history_view.viewport().width()
        if width < 320:
            width = self.history_view.width() - 2
        if width < 320:
            width = self.width() - 36
        if width <= 0:
            return

        available_width = max(1, width - 40)
        target_width = int(width * 0.82)
        max_width = min(max(260, target_width), available_width)
        for bubble in self._bubble_frames:
            bubble.setFixedWidth(max_width)
            bubble.updateGeometry()

    def _schedule_layout_update(self) -> None:
        QTimer.singleShot(0, self._sync_history_layout)
        QTimer.singleShot(80, self._sync_history_layout)

    def _sync_history_layout(self) -> None:
        self._update_bubble_widths()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.history_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def _entry_view_model(
    entry: ChatHistoryEntry,
    subtitle_language: str,
    assistant_name: str,
) -> HistoryEntryView:
    role_name, align, bubble_object_name = _role_style(entry.role, assistant_name)
    time_text = _format_time(entry.created_at)
    return HistoryEntryView(
        role_name=role_name,
        align=align,
        bubble_object_name=bubble_object_name,
        meta_text=f"{role_name} · {time_text}",
        content=entry.display_content(subtitle_language),
    )


def _role_style(role: str, assistant_name: str) -> tuple[str, str, str]:
    if role == "user":
        return ("你", "right", "userBubble")
    if role == "assistant":
        return (assistant_name, "left", "assistantBubble")
    if role == "error":
        return ("错误", "left", "errorBubble")
    return ("系统记录", "center", "systemBubble")


def _label_alignment(align: str) -> Qt.AlignmentFlag:
    if align == "right":
        return Qt.AlignmentFlag.AlignRight
    if align == "center":
        return Qt.AlignmentFlag.AlignCenter
    return Qt.AlignmentFlag.AlignLeft


def _content_object_name(bubble_object_name: str) -> str:
    if bubble_object_name == "errorBubble":
        return "errorText"
    if bubble_object_name == "systemBubble":
        return "systemText"
    return "entryText"


def _format_time(created_at: str) -> str:
    time_text = created_at.replace("T", " ").replace("Z", "")
    for separator in ("+", "."):
        time_text = time_text.split(separator, 1)[0]
    return time_text
