"""Проверка клавиатурной навигации сайдбара: Tab → Down → Enter меняет раздел."""
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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

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
    ctx.setContextProperty("historyModel", HistoryModel())

    state.refreshDevices()
    state.refreshPhrases()

    engine.addImportPath(_QML)
    engine.load(QUrl.fromLocalFile(os.path.join(_QML, "main.qml")))
    if not engine.rootObjects():
        print("QML не загрузился")
        return 1

    win = next((o for o in engine.rootObjects() if isinstance(o, QQuickWindow)), None)
    if win is None:
        print("нет окна")
        return 1
    win.show()
    win.requestActivate()

    results = {}

    def run() -> None:
        results["start"] = win.property("section")
        QTest.keyClick(win, Qt.Key_Tab)
        QTest.qWait(150)
        QTest.keyClick(win, Qt.Key_Down)
        QTest.qWait(150)
        QTest.keyClick(win, Qt.Key_Down)
        QTest.qWait(150)
        QTest.keyClick(win, Qt.Key_Return)
        QTest.qWait(300)
        results["after_keys"] = win.property("section")
        QTest.keyClick(win, Qt.Key_Up)
        QTest.qWait(150)
        QTest.keyClick(win, Qt.Key_Space)
        QTest.qWait(300)
        results["after_space"] = win.property("section")
        print("section start       :", results["start"])
        print("после Tab,Down,Down,Enter:", results["after_keys"])
        print("после Up,Space      :", results["after_space"])
        ok = results["start"] == "home" and results["after_keys"] == "voices" \
            and results["after_space"] == "live"
        print("KEYBOARD NAV:", "PASS" if ok else "FAIL")
        try:
            state.shutdown()
            live.shutdown()
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(1200, run)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
