"""Быстрая диагностика загрузки QML через QQmlComponent."""

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

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow

app = QGuiApplication(sys.argv[:1])

engine = QQmlEngine()
ctx = engine.rootContext()
# пустые контекстные свойства, чтобы QML не падал на undefined
for name in ("appState", "liveEngine", "voiceController",
             "promptModel", "takeModel", "sampleModel", "historyModel"):
    ctx.setContextProperty(name, object())

engine.addImportPath(_QML)

component = QQmlComponent(engine)
component.loadUrl(QUrl.fromLocalFile(os.path.join(_QML, "main.qml")))
if component.isError():
    print("ОШИБКИ QML:")
    for err in component.errors():
        print(f"  {err.toString()}")
else:
    root = component.create()
    print("тип:", type(root).__name__ if root else None)
    if root:
        print("успешно создано")
