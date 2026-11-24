"""Тест рендеринга QML в offscreen через QOpenGLContext + QQuickRenderControl."""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_APP = os.path.join(_ROOT, "app")
_QTAPP = os.path.join(_APP, "qtapp")
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
from PySide6.QtGui import (QOffscreenSurface, QSurfaceFormat, QGuiApplication,
                           QOpenGLContext, QImage)
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtQuick import QQuickRenderControl, QQuickWindow

W, H = 1280, 820

app = QGuiApplication(sys.argv[:1])

fmt = QSurfaceFormat()
fmt.setRenderableType(QSurfaceFormat.OpenGL)
fmt.setDepthBufferSize(24)
fmt.setStencilBufferSize(8)
fmt.setSamples(4)
fmt.setSwapInterval(0)
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.CoreProfile)

surface = QOffscreenSurface()
surface.setFormat(fmt)
surface.create()

context = QOpenGLContext()
context.setFormat(fmt)
if not context.create():
    print("OpenGL контекст не создался")
    sys.exit(1)

control = QQuickRenderControl()
control.initialize(context)

engine = QQmlEngine()
ctx2 = engine.rootContext()
for name in ("appState", "liveEngine", "voiceController",
             "promptModel", "takeModel", "sampleModel", "historyModel"):
    ctx2.setContextProperty(name, object())

engine.addImportPath(_QML)

component = QQmlComponent(engine)
component.loadUrl(QUrl.fromLocalFile(os.path.join(_QML, "main.qml")))
if component.isError():
    print("Ошибки загрузки QML:")
    for err in component.errors():
        print("  ", err.toString())
    sys.exit(1)

root = component.create()
if root is None or not isinstance(root, QQuickWindow):
    print("корень не QQuickWindow:", type(root).__name__ if root else None)
    sys.exit(1)

root.setGeometry(0, 0, W, H)
root.setParent(None)

context.makeCurrent(surface)

control.sync()
control.polishItems()
control.beginFrame()

for _ in range(60):
    app.processEvents()

control.endFrame()
context.doneCurrent()

img = root.grabWindow()
if img is None or img.isNull():
    print("grabWindow пусто")
else:
    out = os.path.join(_ROOT, "shots", "qt_render_test.png")
    img.save(out)
    print(f">>> saved {out} ({img.width()}x{img.height()})")

    dark = light = 0
    step = max(1, img.sizeInBytes() // 4000)
    try:
        data = bytes(img.constBits())
    except Exception:
        data = b""
    for i in range(0, len(data), step):
        b = data[i]
        if b < 40:
            dark += 1
        elif b > 230:
            light += 1
    total = max(1, len(range(0, len(data), step)))
    print(f"dark: {dark/total*100:.1f}% light: {light/total*100:.1f}%")