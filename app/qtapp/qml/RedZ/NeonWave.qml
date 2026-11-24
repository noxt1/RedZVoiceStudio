import QtQuick
import RedZ 1.0

/// Неоновые волны на фоне — фирменный элемент референсов.
///
/// Три плавные линии с градиентом от фиолетового к циану, разной
/// прозрачности. Статичны: рисуются один раз, GPU не грузят.
Item {
    id: root

    property real opacityBoost: 1.0
    property color colorFrom: "#A855F7"
    property color colorMid: "#7C4DFF"
    property color colorTo: "#22D3EE"

    Canvas {
        id: wave
        anchors.fill: parent
        opacity: 0.55 * root.opacityBoost

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = width
            var h = height
            if (w < 10 || h < 10) return

            var lines = [
                { amp: 0.34, y: 0.42, lw: 2.6, a: 0.95 },
                { amp: 0.24, y: 0.56, lw: 1.8, a: 0.70 },
                { amp: 0.15, y: 0.68, lw: 1.3, a: 0.45 }
            ]

            for (var k = 0; k < lines.length; k++) {
                var l = lines[k]
                var g = ctx.createLinearGradient(0, 0, w, 0)
                g.addColorStop(0.0, root.colorFrom)
                g.addColorStop(0.5, root.colorMid)
                g.addColorStop(1.0, root.colorTo)

                ctx.strokeStyle = g
                ctx.globalAlpha = l.a
                ctx.lineWidth = l.lw
                ctx.beginPath()

                var steps = 120
                for (var i = 0; i <= steps; i++) {
                    var t = i / steps
                    var x = t * w
                    var y = h * l.y
                        + Math.sin(t * Math.PI * 2.1 + k * 0.9) * h * l.amp * 0.5
                        + Math.sin(t * Math.PI * 5.3 + k) * h * l.amp * 0.16
                    if (i === 0) ctx.moveTo(x, y)
                    else ctx.lineTo(x, y)
                }
                ctx.stroke()
            }
        }

        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
    }
}
