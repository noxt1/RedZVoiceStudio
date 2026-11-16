"""RedZ Voice Studio — Qt-приложение (PySide6 + QML).

Этот пакет — новый интерфейс. Старый (Tkinter) остаётся в app/ui/ и
запускается флагом --ui-old. Аудиодвижок и логика НЕ дублируются:
используются app/live_client.py, app/studio_core.py, app/mic_bridge.py,
app/studio_paths.py и остальные существующие модули.
"""

__all__ = ["__version__"]
__version__ = "1.0.0"