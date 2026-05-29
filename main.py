from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.api_client import ApiSettings, OpenAICompatibleClient
from app.character_loader import CharacterConfigError, CharacterRegistry
from app.pet_window import PetWindow
from app.tts import create_tts_provider


BASE_DIR = Path(__file__).resolve().parent


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Sakura Desktop Pet")
    app.setQuitOnLastWindowClosed(False)

    settings = ApiSettings.load(BASE_DIR / ".env")
    api_client = OpenAICompatibleClient(settings)
    try:
        character_registry = CharacterRegistry(BASE_DIR)
        character_profile = character_registry.current(BASE_DIR / ".env")
    except CharacterConfigError as exc:
        print(f"[Character] 配置无效：{exc}")
        return 1
    tts_provider = create_tts_provider(BASE_DIR, character_profile)

    pet_window = PetWindow(
        base_dir=BASE_DIR,
        character_registry=character_registry,
        character_profile=character_profile,
        api_client=api_client,
        tts_provider=tts_provider,
    )
    pet_window.show()

    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
