"""Скриншот Qt-интерфейса через QQuickWidget (QWidget render в память)."""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))   # tools
_ROOT = os.path.dirname(_HERE)                       # корень проекта
_APP = os.path.join(_ROOT, "app")                    # app
_QTAPP = os.path.join(_APP, "qtapp")                 # app/qtapp
_QML = os.path.join(_QTAPP, "qml")                   # app/qtapp/qml
for p in (_APP, _QTAPP, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtQml import QQmlEngine, QQmlContext
from PySide6.QtQuickWidgets import QQuickWidget

from app_state import AppState
from live_engine import LiveEngine
from voice_controller import VoiceController
from models import PromptModel, TakeModel, SampleModel, HistoryModel

W, H = 1280, 820


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, "shots", "qt_home.png")
    page = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    app = QApplication(sys.argv[:1])

    widget = QQuickWidget()
    wengine = widget.engine()
    wengine.addImportPath(_QML)
    wctx = wengine.rootContext()

    state = AppState()
    live = LiveEngine()
    voices = VoiceController()
    live.attach(state)
    live.recorder = state.recorder
    state._live_engine = live

    wctx.setContextProperty("appState", state)
    wctx.setContextProperty("liveEngine", live)
    wctx.setContextProperty("voiceController", voices)
    wctx.setContextProperty("promptModel", PromptModel())
    wctx.setContextProperty("takeModel", TakeModel())
    wctx.setContextProperty("sampleModel", SampleModel())
    wctx.setContextProperty("historyModel", HistoryModel())

    state.refreshDevices()
    state.refreshPhrases()

    widget.setSource(QUrl.fromLocalFile(os.path.join(_QML, "shot_main.qml")))
    if widget.status() == QQuickWidget.Error:
        for err in widget.errors():
            print("QML error:", err.toString())
        return 1
    widget.setResizeMode(QQuickWidget.SizeRootObjectToView)
    widget.resize(W, H)
    widget.show()

    # даём время на загрузку и отрисовку
    QTimer.singleShot(2500, lambda: save(widget, out, page, app))
    return app.exec()


def save(widget: QQuickWidget, out: str, page: int, app) -> None:
    try:
        if page:
            # устанавливаем currentPage через корневой объект
            root = widget.rootObject()
            if root is not None:
                root.setProperty("currentPage", page)
    except Exception:
        pass

    # рендерим виджет в пиксельную карту
    img = widget.grabFramebuffer()
    if img is None or img.isNull():
        pixmap = QPixmap(widget.size())
        widget.render(pixmap)
        img = pixmap.toImage()

    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print(f">>> saved {out} ({img.width()}x{img.height()})")

    try:
        app.quit()
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())