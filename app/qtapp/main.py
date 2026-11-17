"""Точка входа Qt-интерфейса RedZ Voice Studio.

Запуск:
    python app/qtapp/main.py

Или из собранного EXE — флаг --ui-qt (по умолчанию новый Qt-интерфейс).

Tkinter здесь не используется. Старый интерфейс (Tk) остаётся доступен
через --ui-old в app/voice_studio.py.
"""

from __future__ import annotations

import os
import sys

# --- путь к app/ (чтобы импортировать studio_paths и прочие модули) ---
_HERE = os.path.dirname(os.path.abspath(__file__))   # app/qtapp
_APP_DIR = os.path.dirname(_HERE)                    # app
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

import studio_paths as sp

from app_state import AppState
from live_engine import LiveEngine
from voice_controller import VoiceController
from models import (PromptModel, TakeModel, SampleModel, HistoryModel)
import branding

QML_DIR = os.path.join(_HERE, "qml")


def _qml_import_paths() -> list[str]:
    """Каталог с модулем RedZ (qmldir + компоненты)."""
    return [os.path.join(QML_DIR)]


def main() -> int:
    # высокое DPI (Qt 6 делает это сам, но на всякий случай)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QGuiApplication(sys.argv)
    app.setApplicationName(branding.BRAND_NAME)
    app.setOrganizationName(branding.ORG_NAME)
    app.setApplicationDisplayName(branding.BRAND_NAME)

    # иконка окна
    ico = os.path.join(_APP_DIR, "studio.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))

    engine = QQmlApplicationEngine()

    # --- контроллеры (один на приложение) ---
    state = AppState()
    live = LiveEngine()
    voices = VoiceController()

    # связываем
    live.attach(state)
    live.recorder = state.recorder
    state._live_engine = live

    prompt_model = PromptModel()
    take_model = TakeModel()
    sample_model = SampleModel()
    history_model = HistoryModel()

    # --- история переводов заполняется в любом режиме UI ---
    live.textReady.connect(
        lambda ru, es, tone="": history_model.add("out", ru, es))
    # для входящих: перевод на русский + оригинал собеседника
    live.peerTextReady.connect(
        lambda lang, ru, original: history_model.add("in", ru, original))

    # громкость синтеза из пользовательских настроек
    live.setVolume(state.voiceVolume)

    # --- контекст QML ---
    ctx = engine.rootContext()
    # название продукта — из одного модуля (app/branding.py)
    ctx.setContextProperty("brandName", branding.BRAND_NAME)
    ctx.setContextProperty("brandShort", branding.BRAND_SHORT)
    ctx.setContextProperty("brandSub", branding.BRAND_SUB)
    ctx.setContextProperty("brandTagline", branding.BRAND_TAGLINE)
    ctx.setContextProperty("appState", state)
    ctx.setContextProperty("liveEngine", live)
    ctx.setContextProperty("voiceController", voices)
    ctx.setContextProperty("promptModel", prompt_model)
    ctx.setContextProperty("takeModel", take_model)
    ctx.setContextProperty("sampleModel", sample_model)
    ctx.setContextProperty("historyModel", history_model)

    # стартовые данные
    state.refreshDevices()
    state.refreshPhrases()

    # настройка «Автозагрузка моделей»: поднять движок сразу после старта
    if state.autoStartEngine and state.engineInstalled() == "да":
        QTimer.singleShot(1500, state.startEngine)

    engine.addImportPath(os.path.join(QML_DIR))
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "main.qml")))

    if not engine.rootObjects():
        sys.stderr.write("Не удалось загрузить QML\n")
        return 1

    # окно — maximize (QML уже задаёт размер)
    for obj in engine.rootObjects():
        if isinstance(obj, QQuickWindow):
            obj.show()
            obj.requestActivate()
            break

    # аккуратное завершение
    code = app.exec()

    try:
        state.shutdown()
        live.shutdown()
    except Exception:
        pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())