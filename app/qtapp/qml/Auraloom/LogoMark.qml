import QtQuick
import Auraloom 1.0

/// Фирменный знак Auraloom: стеклянная плитка с градиентным «A» и волной.
///
/// По брендборду: буква A нарисована из двух неоновых мазков, внутри —
/// вертикальная волна. Рисуется примитивами, без картинок.
Item {
    id: root

    property int size: 64
    property bool withTile: true
    property real glow: 0.55

    implicitWidth: size
    implicitHeight: size

    // мягкое свечение позади знака
    Rectangle {
        anchors.centerIn: parent
        width: parent.width * 0.92
        height: width
        radius: width / 2
        color: Theme.accent
        opacity: root.glow * 0.22
    }

    Rectangle {
        id: tile
        anchors.fill: parent
        radius: root.size * 0.28
        gradient: Theme.gradBrand
        visible: root.withTile
    }

    // затемнённая «стеклянная» подложка, чтобы буква читалась
    Rectangle {
        anchors.fill: tile
        anchors.margins: 1.5
        radius: tile.radius - 1
        color: "#0B1030"
        opacity: 0.55
        visible: root.withTile
    }

    // буква A: два мазка градиентом
    Canvas {
        id: alphaStroke
        anchors.centerIn: parent
        width: parent.width * 0.72
        height: width
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = width
            var h = height
            var lw = Math.max(3, w * 0.15)

            var g = ctx.createLinearGradient(0, h, w, 0)
            g.addColorStop(0, "#C084FC")
            g.addColorStop(0.55, "#7C4DFF")
            g.addColorStop(1, "#22D3EE")
            ctx.strokeStyle = g
            ctx.lineWidth = lw
            ctx.lineCap = "round"
            ctx.lineJoin = "round"

            // левая нога
            ctx.beginPath()
            ctx.moveTo(w * 0.06, h * 0.92)
            ctx.lineTo(w * 0.44, h * 0.10)
            ctx.stroke()

            // правая нога — с неоновым цианом
            var g2 = ctx.createLinearGradient(w * 0.4, h * 0.1, w, h * 0.92)
            g2.addColorStop(0, "#7C4DFF")
            g2.addColorStop(1, "#22D3EE")
            ctx.strokeStyle = g2
            ctx.beginPath()
            ctx.moveTo(w * 0.44, h * 0.10)
            ctx.lineTo(w * 0.94, h * 0.92)
            ctx.stroke()

            // перекладина
            ctx.strokeStyle = "#22D3EE"
            ctx.beginPath()
            ctx.moveTo(w * 0.26, h * 0.64)
            ctx.lineTo(w * 0.70, h * 0.64)
            ctx.stroke()
        }
    }

    // волна внутри буквы
    Row {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: root.size * 0.10
        spacing: Math.max(1, root.size * 0.035)

        Repeater {
            model: [0.30, 0.62, 1.0, 0.72, 0.44, 0.86, 0.36]
            delegate: Rectangle {
                width: Math.max(1, root.size * 0.035)
                height: root.size * 0.20 * modelData
                radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                color: "#EAF4FF"
                opacity: 0.92
            }
        }
    }
}
