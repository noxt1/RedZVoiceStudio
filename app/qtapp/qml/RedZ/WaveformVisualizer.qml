import QtQuick
import RedZ 1.0

/// Визуализатор звуковой волны (как в референсе VoxShift).
/// Набор вертикальных полос разной высоты, анимация при активном звуке.
Item {
    id: root

    property real level: 0.0      // 0..1 — текущий уровень звука
    property bool active: false   // идёт ли звук/запись
    property int bars: 20
    property color barIdle: Theme.surface2
    property color barActive: Theme.accent

    implicitWidth: 300
    implicitHeight: 100

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: Theme.border
        border.width: 1
        radius: Theme.radiusControl
    }

    Repeater {
        model: root.bars
        delegate: Rectangle {
            width: parent.width / root.bars - 4
            height: {
                let base = 4 + Math.random() * 12
                if (root.active) {
                    let pulse = 8 + Math.sin(Date.now() / 60 + index) * 8
                    base = Math.min(base + pulse * root.level, 96)
                }
                return base
            }
            color: root.active && index % 3 === 0 ? root.barActive : root.barIdle
            radius: 2
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 6
            Behavior on height { NumberAnimation { duration: 60 } }
        }
    }

    Timer {
        interval: 50
        running: root.active
        repeat: true
        onTriggered: {
            // перезапускаем таймер для анимации (Repeater пересчитает высоты)
            root.forceActiveFocus()
        }
    }
}