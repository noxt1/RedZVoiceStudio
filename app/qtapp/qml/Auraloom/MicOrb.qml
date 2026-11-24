import QtQuick
import QtQuick.Effects
import Auraloom 1.0

/// Микрофонная орб: внутри диска «наливается» неоновая жидкость по уровню
/// голоса, наружу расходятся волны-рябь, свечение дышит вместе с речью.
///
/// Сглаженный уровень (`smoothLevel`) убирает дрожь между отсчётами, а
/// `phase` двигает поверхность жидкости и кольца — поэтому орб выглядит
/// живой и без постоянного таймера на каждое свойство.
Item {
    id: root

    property real level: 0.0        // 0..1 — уровень микрофона
    property bool active: false
    property real pressBoost: 0.0   // импульс от нажатия (0..1)
    property color ringColor: Theme.accent
    property color ringColor2: Theme.accentCyan
    property string iconSource: "icons/mic.svg"

    implicitWidth: 220
    implicitHeight: 220

    // сглаженный уровень: стрелка не дёргается на каждом отсчёте
    property real smoothLevel: root.level
    Behavior on smoothLevel {
        NumberAnimation { duration: 130; easing.type: Easing.OutQuad }
    }

    // energy — «насколько громко сейчас»: 0 в тишине, 1 на пике
    readonly property real energy: {
        var e = Math.min(1.0, root.smoothLevel + root.pressBoost * 0.45)
        if (root.active)
            return Math.max(0.05, e)
        return Math.max(0.0, e * 0.7)
    }

    // фаза анимации: двигает жидкость и кольца (~30 кадров в секунду)
    property real phase: 0.0
    Timer {
        interval: 33
        repeat: true
        running: true
        onTriggered: root.phase += 0.038
    }

    // ---------------------------------------------------------------
    // мягкое неоновое свечение (растёт и меняет цвет с громкостью)
    // ---------------------------------------------------------------
    Rectangle {
        id: glowSrc
        anchors.centerIn: parent
        width: root.width * (0.78 + root.energy * 0.12)
        height: width
        radius: width / 2
        color: root.energy > 0.55 ? root.ringColor2 : root.ringColor
        opacity: 0.28 + root.energy * 0.55
        visible: false
        layer.enabled: true
        Behavior on width {
            NumberAnimation { duration: 180; easing.type: Easing.OutQuad }
        }
        Behavior on opacity {
            NumberAnimation { duration: 140; easing.type: Easing.OutQuad }
        }
    }

    MultiEffect {
        anchors.fill: glowSrc
        source: glowSrc
        blurEnabled: true
        blur: 1.0
        blurMax: 72
        opacity: 0.9
    }

    // ---------------------------------------------------------------
    // расходящиеся волны: красиво реагируют даже на тихую речь
    // ---------------------------------------------------------------
    Repeater {
        model: 4
        delegate: Rectangle {
            readonly property real p: (root.phase * 0.42 + index / 4) % 1.0
            anchors.centerIn: parent
            width: root.width * (0.60 + p * 0.46)
            height: width
            radius: width / 2
            color: "transparent"
            border.width: index === 0 ? 2 : 1
            border.color: index % 2 === 0 ? root.ringColor : root.ringColor2
            opacity: (1.0 - p) * (0.08 + root.energy * 0.62)
        }
    }

    // чёткое кольцо вокруг диска
    Rectangle {
        anchors.centerIn: parent
        width: root.width * 0.70
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 1
        border.color: root.ringColor2
        opacity: 0.35 + root.energy * 0.5
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }

    // ---------------------------------------------------------------
    // диск с «жидкостью»: уровень голоса наполняет его снизу вверх
    // ---------------------------------------------------------------
    Item {
        id: disc
        anchors.centerIn: parent
        width: root.width * 0.62
        height: width

        Canvas {
            id: liquid
            anchors.fill: parent
            onPaint: root.paintLiquid(liquid)
            onWidthChanged: liquid.requestPaint()
            onHeightChanged: liquid.requestPaint()

            Connections {
                target: root
                function onEnergyChanged() { liquid.requestPaint() }
                function onPhaseChanged() { liquid.requestPaint() }
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.borderStrong
        }

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: root.ringColor2
            opacity: root.active ? 0.20 + root.energy * 0.55 : 0.18
            Behavior on opacity { NumberAnimation { duration: 120 } }
        }
    }

    // иконка микрофона поверх жидкости; на пике жидкость яркая, поэтому
    // под иконкой появляется тёмное пятно — она не сливается с заливкой
    Rectangle {
        anchors.centerIn: parent
        width: root.width * (0.26 + root.energy * 0.06)
        height: width
        radius: width / 2
        color: "#05091E"
        opacity: 0.10 + root.energy * 0.45
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }

    Icon {
        anchors.centerIn: parent
        source: root.iconSource
        color: Theme.textPrimary
        size: Math.round(root.width * 0.24)
        scale: 1.0 + root.energy * 0.10
        Behavior on scale {
            NumberAnimation { duration: 110; easing.type: Easing.OutQuad }
        }
    }

    // ---------------------------------------------------------------
    // рисование жидкости
    // ---------------------------------------------------------------
    function paintLiquid(canvas) {
        var ctx = canvas.getContext("2d")
        if (!ctx)
            return
        var w = canvas.width
        var h = canvas.height
        if (w <= 2 || h <= 2)
            return
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.clearRect(0, 0, w, h)

        var r = w / 2
        ctx.save()
        ctx.beginPath()
        ctx.arc(r, r, r - 0.5, 0, Math.PI * 2)
        ctx.clip()

        // тёмная подложка диска
        var bg = ctx.createLinearGradient(0, 0, 0, h)
        bg.addColorStop(0, "#151A4A")
        bg.addColorStop(1, "#080C26")
        ctx.fillStyle = bg
        ctx.fillRect(0, 0, w, h)

        // уровень: в тишине тонкая полоска, на пике — почти весь диск
        var e = root.energy
        var levelPart = 0.10 + Math.min(1.0, e) * 0.88
        var top = h * (1.0 - levelPart)
        var amp = 1.5 + Math.min(1.0, e) * 7.0

        function surfaceY(x) {
            return top + Math.sin(x * 0.055 + root.phase * 2.4) * amp
                       + Math.sin(x * 0.115 - root.phase * 1.7) * amp * 0.45
        }

        var grad = ctx.createLinearGradient(0, top, 0, h)
        grad.addColorStop(0.0, "#7DE7FF")
        grad.addColorStop(0.45, "#38BDF8")
        grad.addColorStop(1.0, "#6D3BF5")

        ctx.beginPath()
        ctx.moveTo(0, surfaceY(0))
        for (var x = 4; x <= w; x += 4)
            ctx.lineTo(x, surfaceY(x))
        ctx.lineTo(w, h)
        ctx.lineTo(0, h)
        ctx.closePath()
        ctx.globalAlpha = 0.92
        ctx.fillStyle = grad
        ctx.fill()
        ctx.globalAlpha = 1.0

        // светящаяся кромка жидкости
        ctx.beginPath()
        ctx.moveTo(0, surfaceY(0))
        for (var x2 = 4; x2 <= w; x2 += 4)
            ctx.lineTo(x2, surfaceY(x2))
        ctx.strokeStyle = "rgba(200,245,255,0.95)"
        ctx.lineWidth = 1.6
        ctx.stroke()

        ctx.restore()
    }
}
