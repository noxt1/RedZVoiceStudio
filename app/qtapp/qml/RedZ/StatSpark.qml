import QtQuick
import RedZ 1.0

/// Мини-график (спарклайн) для панели статистики.
Item {
    id: root

    property var values: [0.2, 0.35, 0.3, 0.6, 0.45, 0.75, 0.5, 0.62, 0.9]
    property color lineColor: Theme.accentCyan

    implicitWidth: 180
    implicitHeight: 42

    Canvas {
        id: chart
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = width
            var h = height
            var v = root.values
            if (!v || v.length < 2) return

            var maxV = 0.0001
            for (var i = 0; i < v.length; i++) maxV = Math.max(maxV, v[i])

            var g = ctx.createLinearGradient(0, 0, 0, h)
            g.addColorStop(0, "#22D3EE")
            g.addColorStop(1, "#7C4DFF")

            ctx.strokeStyle = g
            ctx.lineWidth = 2
            ctx.lineJoin = "round"
            ctx.beginPath()
            for (var j = 0; j < v.length; j++) {
                var x = w * j / (v.length - 1)
                var y = h - (v[j] / maxV) * (h - 4) - 2
                if (j === 0) ctx.moveTo(x, y)
                else ctx.lineTo(x, y)
            }
            ctx.stroke()

            // заливка под линией
            ctx.lineTo(w, h)
            ctx.lineTo(0, h)
            ctx.closePath()
            var fill = ctx.createLinearGradient(0, 0, 0, h)
            fill.addColorStop(0, "rgba(88, 101, 242, 0.35)")
            fill.addColorStop(1, "rgba(88, 101, 242, 0.0)")
            ctx.fillStyle = fill
            ctx.fill()
        }

        onValuesChanged: requestPaint()
        Component.onCompleted: requestPaint()
    }
}
