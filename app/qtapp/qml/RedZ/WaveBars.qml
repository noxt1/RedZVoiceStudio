import QtQuick
import RedZ 1.0

/// Волновая дорожка: бегущая неоновая волна на всю ширину карточки.
///
/// Раньше это были отдельные столбики с лёгкой пульсацией. Теперь это
/// непрерывная волна на Canvas: она «бежит» вбок, раздвигается по высоте
/// от реального уровня микрофона и мягко дышит в тишине. Рисунок живёт
/// строго внутри своей области, поэтому соседние элементы не задевает.
Item {
    id: root

    property real level: 0.0        // 0..1 — реальный уровень микрофона
    property bool active: false
    property real pressBoost: 0.0   // короткий импульс от нажатия кнопки
    property int bars: 56           // оставлено для совместимости
    property color colorFrom: Theme.accent
    property color colorTo: Theme.accentCyan
    property real maxHeight: height

    implicitWidth: 420
    implicitHeight: 56

    // сглаженный уровень и бегущая фаза
    property real smoothLevel: root.level
    Behavior on smoothLevel {
        NumberAnimation { duration: 120; easing.type: Easing.OutQuad }
    }

    readonly property real energy: {
        var e = Math.min(1.0, root.smoothLevel + root.pressBoost * 0.5)
        return root.active ? Math.max(0.08, e) : Math.max(0.0, e * 0.6)
    }

    property real phase: 0.0
    Timer {
        interval: 33
        repeat: true
        running: true
        onTriggered: root.phase += 0.055
    }

    Canvas {
        id: wave
        anchors.fill: parent
        onPaint: root.paintWave(wave)
        onWidthChanged: wave.requestPaint()
        onHeightChanged: wave.requestPaint()

        Connections {
            target: root
            function onEnergyChanged() { wave.requestPaint() }
            function onPhaseChanged() { wave.requestPaint() }
        }
    }

    // тонкая осевая линия — чтобы волна читалась и в полной тишине
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: 1
        color: Theme.border
        opacity: 0.45
    }

    function paintWave(canvas) {
        var ctx = canvas.getContext("2d")
        if (!ctx)
            return
        var w = canvas.width
        var h = canvas.height
        if (w <= 4 || h <= 4)
            return

        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.clearRect(0, 0, w, h)

        var mid = h / 2
        var e = root.energy
        // амплитуда: в тишине еле заметная, на пике — почти на всю высоту
        var amp = (h * 0.42) * (0.16 + Math.min(1.0, e) * 0.9)

        function sampleAmp(t) {
            return Math.sin(t * 12.0 + root.phase * 3.4) * 0.58
                 + Math.sin(t * 23.0 - root.phase * 2.1) * 0.26
                 + Math.sin(t * 5.0 + root.phase * 0.9) * 0.16
        }
        function envelope(t) {
            // к краям волна стихает — дорожка выглядит аккуратной
            return 0.30 + 0.70 * Math.sin(Math.PI * t)
        }

        var grad = ctx.createLinearGradient(0, 0, w, 0)
        grad.addColorStop(0.0, "#8B5CF6")
        grad.addColorStop(0.5, "#3B82F6")
        grad.addColorStop(1.0, "#22D3EE")

        // тело волны: зеркально сверху и снизу от оси
        var step = 3
        ctx.beginPath()
        ctx.moveTo(0, mid)
        for (var x = 0; x <= w; x += step) {
            var t = x / Math.max(1, w)
            var y = mid - Math.abs(sampleAmp(t)) * envelope(t) * amp
            ctx.lineTo(x, y)
        }
        for (var x2 = w; x2 >= 0; x2 -= step) {
            var t2 = x2 / Math.max(1, w)
            var y2 = mid + Math.abs(sampleAmp(t2)) * envelope(t2) * amp
            ctx.lineTo(x2, y2)
        }
        ctx.closePath()
        ctx.globalAlpha = 0.22 + Math.min(1.0, e) * 0.18
        ctx.fillStyle = grad
        ctx.fill()

        // неоновый контур: широкий полупрозрачный + тонкий яркий
        ctx.beginPath()
        for (var x3 = 0; x3 <= w; x3 += step) {
            var t3 = x3 / Math.max(1, w)
            var y3 = mid - Math.abs(sampleAmp(t3)) * envelope(t3) * amp
            if (x3 === 0)
                ctx.moveTo(x3, y3)
            else
                ctx.lineTo(x3, y3)
        }
        ctx.globalAlpha = 0.22 + Math.min(1.0, e) * 0.18
        ctx.strokeStyle = "#22D3EE"
        ctx.lineWidth = 6
        ctx.stroke()

        ctx.globalAlpha = 0.92
        ctx.strokeStyle = grad
        ctx.lineWidth = 2.2
        ctx.stroke()

        ctx.globalAlpha = 1.0
    }
}
