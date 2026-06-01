from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from app.core.app_context import AppContext
from app.core.bootstrap import build_deferred_services, build_initial_app_context
from app.config.character_loader import CharacterConfigError
from app.ui.pet_window import PetWindow


BASE_DIR = Path(__file__).resolve().parent


class DeferredStartupWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, base_dir: Path, context: AppContext) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.context = context

    @Slot()
    def run(self) -> None:
        try:
            services = build_deferred_services(self.base_dir, self.context)
            self._move_service_objects_to_ui_thread(services)
            self.finished.emit(services)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _move_service_objects_to_ui_thread(self, services: object) -> None:
        application = QApplication.instance()
        if application is None:
            return
        tts_provider = getattr(services, "tts_provider", None)
        if isinstance(tts_provider, QObject):
            tts_provider.moveToThread(application.thread())


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Sakura Desktop Pet")
    app.setQuitOnLastWindowClosed(False)

    try:
        context = build_initial_app_context(BASE_DIR)
    except CharacterConfigError as exc:
        print(f"[Character] 配置无效：{exc}")
        return 1

    pet_window = PetWindow(context)
    pet_window.show()
    QTimer.singleShot(0, lambda: _start_deferred_startup(BASE_DIR, pet_window))

    return app.exec()


def _start_deferred_startup(base_dir: Path, pet_window: PetWindow) -> None:
    thread = QThread(pet_window)
    worker = DeferredStartupWorker(base_dir, pet_window.context)
    worker.moveToThread(thread)
    pet_window.deferred_startup_thread = thread
    pet_window.deferred_startup_worker = worker
    thread.started.connect(worker.run)
    worker.finished.connect(pet_window.apply_deferred_services)
    worker.failed.connect(pet_window.handle_deferred_startup_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda: setattr(pet_window, "deferred_startup_thread", None))
    thread.finished.connect(lambda: setattr(pet_window, "deferred_startup_worker", None))
    thread.start()

if __name__ == "__main__":
    raise SystemExit(main())
