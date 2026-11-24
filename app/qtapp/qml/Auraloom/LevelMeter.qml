import QtQuick
import Auraloom 1.0

/// Вертикальный уровень с пиком (как в референсе "Level / Peak").
Item {
    id: root

    property real level: 0.0      // 0..1
    property real peak: 0.0       // 0..1 пик
    property string label: "Level"

    implicitWidth: 44
    implicitHeight: 140

    Column {
        anchors.fill: parent
        spacing: Theme.spaceXS

        // шкала уровня (горизонтальные полосы)
        Item {
            id: scale
            height: 100

            Repeater {
                model: 10
                delegate: Rectangle {
                    width: parent.width
                    height: 8
                    radius: 4
                    color: index < Math.round(root.level * 10)
                        ? (index > 7 ? Theme.danger : (index > 4 ? Theme.warning : Theme.success))
                        : Theme.surface2
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: (9 - index) * 10
                }
            }
        }

        // пиковая метка
        Rectangle {
            width: parent.width
            height: 2
            color: Theme.accentBright
            anchors.horizontalCenter: parent.horizontalCenter
            y: (9 - root.peak * 10) * 10 + 4
            opacity: root.peak > 0 ? 1 : 0
        }

        Text {
            text: root.label
            color: Theme.textMuted
            font.family: Theme.fontFamilyText
            font.pixelSize: 10
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: (root.level * 100).toFixed(0) + "%"
            color: Theme.textSecondary
            font.family: Theme.fontFamilyMono
            font.pixelSize: 11
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}