import QtQuick
import QtQuick.Effects
import RedZ 1.0

/// Микрофонная орб из референсов: светящееся кольцо, тёмный центр,
/// микрофон и пульсация от уровня звука.
Item {
    id: root

    property real level: 0.0        // 0..1 — уровень микрофона
    property bool active: false     // идёт запись/перевод
    property color ringColor: Theme.accent
    property color ringColor2: Theme.accentCyan
    property string iconSource: "icons/mic.svg"

    implicitWidth: 220
    implicitHeight: 220

    readonly property real pulse: active ? 0.5 + Math.min(0.5, level) * 0.5 : 0.35

    // внешние кольца
    Repeater {
        model: 3
        delegate: Rectangle {
            anchors.centerIn: parent
            width: root.width * (0.86 + index * 0.10)
            height: width
            radius: width / 2
            color: "transparent"
            border.width: index === 0 ? 2 : 1
            border.color: index % 2 === 0 ? root.ringColor : root.ringColor2
            opacity: (index === 0 ? 0.9 : 0.35) * (0.55 + 0.45 * root.pulse)

            SequentialAnimation on scale {
                running: root.active
                loops: Animation.Infinite
                NumberAnimation { to: 1.035; duration: 900 + index * 220; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 1.0; duration: 900 + index * 220; easing.type: Easing.InOutQuad }
            }
        }
    }

    // мягкое свечение
    Rectangle {
        id: glowSrc
        anchors.centerIn: parent
        width: root.width * 0.78
        height: width
        radius: width / 2
        color: root.ringColor
        opacity: 0.35 * root.pulse
        layer.enabled: true
        visible: false
    }

    MultiEffect {
        anchors.fill: glowSrc
        source: glowSrc
        blurEnabled: true
        blur: 1.0
        blurMax: 64
        opacity: 0.85
    }

    // тёмный центр
    Rectangle {
        anchors.centerIn: parent
        width: root.width * 0.62
        height: width
        radius: width / 2
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#151A4A" }
            GradientStop { position: 1.0; color: "#080C26" }
        }
        border.width: 1
        border.color: Theme.borderStrong
    }

    // внутреннее неоновое кольцо
    Rectangle {
        anchors.centerIn: parent
        width: root.width * 0.55
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.accentCyan
        opacity: root.active ? 0.85 : 0.35
    }

    Icon {
        anchors.centerIn: parent
        source: root.iconSource
        color: Theme.textPrimary
        size: Math.round(root.width * 0.24)
    }
}
