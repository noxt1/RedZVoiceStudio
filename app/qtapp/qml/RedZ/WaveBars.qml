import QtQuick
import RedZ 1.0

/// Волновая дорожка из референсов: полосы разной высоты, «дышат» от уровня.
Item {
    id: root

    property real level: 0.0        // 0..1
    property bool active: false
    property int bars: 56
    property color colorFrom: Theme.accent
    property color colorTo: Theme.accentCyan
    property real maxHeight: height

    implicitWidth: 420
    implicitHeight: 56

    // фаза «дыхания»: волна чуть шевелится даже в тишине
    property real phase: 0.0

    Timer {
        interval: 70
        repeat: true
        running: true
        onTriggered: root.phase += 0.18
    }

    // фиксированный «рисунок» волны: без Math.random, чтобы не дёргалось
    readonly property var pattern: [
        0.18, 0.34, 0.52, 0.78, 1.00, 0.72, 0.44, 0.62, 0.90, 0.66,
        0.38, 0.56, 0.84, 1.00, 0.70, 0.46, 0.30, 0.50, 0.74, 0.94,
        0.68, 0.42, 0.26, 0.44, 0.66, 0.86, 0.58, 0.36, 0.52, 0.76,
        0.96, 0.64, 0.40, 0.28, 0.48, 0.70, 0.88, 0.60, 0.38, 0.54,
        0.80, 0.98, 0.66, 0.42, 0.30, 0.52, 0.74, 0.56, 0.34, 0.22,
        0.40, 0.62, 0.82, 0.58, 0.36, 0.24
    ]

    Row {
        anchors.centerIn: parent
        spacing: Math.max(1, Math.round(width / root.bars * 0.45))

        Repeater {
            model: root.bars
            delegate: Rectangle {
                readonly property real base: root.pattern[index % root.pattern.length]
                width: Math.max(2, Math.round(parent.parent.width / root.bars * 0.55))
                height: {
                    var amp = root.active ? (0.45 + root.level * 0.55) : 0.52
                    var breathe = root.active ? 0.0
                                             : 0.07 * Math.sin(root.phase + index * 0.45)
                    return Math.max(3, root.height * base * (amp + breathe))
                }
                radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                color: index < root.bars / 2 ? root.colorFrom : root.colorTo
                opacity: root.active ? 0.95 : 0.65
                Behavior on height { NumberAnimation { duration: 90 } }
            }
        }
    }
}
