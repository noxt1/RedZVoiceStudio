"""Скриншоты «Истории» с заполненными записями (проверка карточек).

Запускается на windows-платформе, чтобы шрифты рисовались как в приложении.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app")
_QTAPP = os.path.join(_APP, "qtapp")
_QML = os.path.join(_QTAPP, "qml")
for p in (_APP, _QTAPP, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from app_state import AppState
from live_engine import LiveEngine
from voice_controller import VoiceController
import branding
from models import PromptModel, TakeModel, SampleModel, HistoryModel


def main() -> int:
    app = QGuiApplication(sys.argv[:1])
    engine = QQmlApplicationEngine()

    state = AppState()
    live = LiveEngine()
    voices = VoiceController()
    live.attach(state)
    live.recorder = state.recorder
    state._live_engine = live

    history = HistoryModel()
    history.add("out", "Привет, как дела?", "Hola, ¿cómo estás?")
    history.add("in", "О нет, нет, нет.", "Oh no, no, no.")
    history.add("out", "Я уже хочу есть.", "Ya tengo hambre.")
    history.add("in", "Не двигайся!", "¡No se mueva!")

    ctx = engine.rootContext()
    ctx.setContextProperty("brandName", branding.BRAND_NAME)
    ctx.setContextProperty("brandShort", branding.BRAND_SHORT)
    ctx.setContextProperty("brandSub", branding.BRAND_SUB)
    ctx.setContextProperty("brandTagline", branding.BRAND_TAGLINE)
    ctx.setContextProperty("appState", state)
    ctx.setContextProperty("liveEngine", live)
    ctx.setContextProperty("voiceController", voices)
    ctx.setContextProperty("promptModel", PromptModel())
    ctx.setContextProperty("takeModel", TakeModel())
    ctx.setContextProperty("sampleModel", SampleModel())
    ctx.setContextProperty("historyModel", history)

    state.refreshDevices()
    state.refreshPhrases()

    engine.addImportPath(_QML)
    engine.load(QUrl.fromLocalFile(os.path.join(_QML, "main.qml")))
    win = next((o for o in engine.rootObjects() if isinstance(o, QQuickWindow)), None)
    if win is None:
        print("нет окна")
        return 1
    win.setProperty("section", "history")
    win.resize(1280, 840)
    win.show()

    def grab(name: str) -> None:
        img = win.grabWindow()
        out = os.path.join(_ROOT, "shots", name)
        img.save(out)
        print("saved", out, img.width(), img.height())

    def step1() -> None:
        grab("history_filled_1280x840.png")
        win.resize(1920, 1080)
        QTimer.singleShot(900, step2)

    def step2() -> None:
        grab("history_filled_1920x1080.png")
        try:
            state.shutdown()
            live.shutdown()
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(1200, step1)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
