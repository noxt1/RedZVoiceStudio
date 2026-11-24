import QtQuick
import Auraloom 1.0

/// Визуализатор звуковой волны: высота полос идёт от реального уровня
/// микрофона. Случайный Math.random и вечный таймер убраны — раньше полосы
/// дёргались сами по себе, даже когда микрофон молчал.
Item {
    id: root

    property real level: 0.0      // 0..1 — текущий уровень звука
    property bool active: false
    property real pressBoost: 0.0
    property int bars: 20
    property color barIdle: Theme.surface2
    property color barActive: Theme.accent

    implicitWidth: 300
    implicitHeight: 100

    readonly property var shape: [0.35, 0.55, 0.80, 1.00, 0.72, 0.46,
                                  0.62, 0.90, 0.58, 0.40, 0.74, 0.96,
                                  0.52, 0.36, 0.68, 0.84, 0.44, 0.30,
                                  0.58, 0.76]

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
                var amp = root.active
                          ? Math.min(1.3, 0.20 + root.level * 1.05
                                          + root.pressBoost * 0.30)
                          : 0.14
                return 4 + root.shape[index % root.shape.length] * 84 * amp
            }
            color: root.active && index % 3 === 0 ? root.barActive : root.barIdle
            radius: 2
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 6
            Behavior on height {
                NumberAnimation { duration: 80; easing.type: Easing.OutQuad }
            }
            Behavior on color { ColorAnimation { duration: 120 } }
        }
    }
}
