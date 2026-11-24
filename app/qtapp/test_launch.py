"""Тест запуска Qt-интерфейса: проверяет, что QML загружается и приложение не падает.

Запускает приложение на 3 секунды, затем завершает. Возвращает 0 при успехе.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))   # app/qtapp
_QTAPP = _HERE
_APP = os.path.dirname(_QTAPP)                       # app
_ROOT = os.path.dirname(_APP)                        # корень проекта
_QML = os.path.join(_QTAPP, "qml")
for p in (_APP, _QTAPP, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from app_state import AppState
from live_engine import LiveEngine
from voice_controller import VoiceController
import branding
from models import PromptModel, TakeModel, SampleModel, HistoryModel


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
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
        sys.stderr.write("QML не загрузился (корневые объекты отсутствуют)\n")
        return 1

    win = None
    for obj in engine.rootObjects():
        if isinstance(obj, QQuickWindow):
            win = obj
            break
    if win is None:
        sys.stderr.write("нет окна\n")
        return 1

    win.show()

    def finish() -> None:
        print(">>> окно создано и показано, QML OK")
        # скриншот через grabWindow
        try:
            os.makedirs(os.path.join(_ROOT, "shots"), exist_ok=True)
            img = win.grabWindow()
            if img is not None and not img.isNull():
                out = os.path.join(_ROOT, "shots", "qt_live.png")
                img.save(out)
                print(f">>> saved {out} ({img.width()}x{img.height()})")
        except Exception as exc:
            sys.stderr.write(f"скриншот: {exc}\n")
        try:
            state.shutdown()
            live.shutdown()
        except Exception:
            pass
        app.quit()

    QTimer.singleShot(1500, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())