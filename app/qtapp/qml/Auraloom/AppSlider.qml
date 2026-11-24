import QtQuick
import Auraloom 1.0

/// Слайдер с меткой и значением. Кастомный — без QtQuick.Controls.
Item {
    id: root

    property real value: 0.5
    property real from: 0.0
    property real to: 1.0
    property string label: ""
    property string suffix: ""
    property int decimals: 0
    property color accent: Theme.accent

    signal moved(real value)

    implicitWidth: 240
    implicitHeight: 30

    readonly property real pos: {
        var r = (root.to - root.from)
        return r === 0 ? 0 : (root.value - root.from) / r
    }

    Row {
        anchors.fill: parent
        spacing: Theme.spaceSM

        Text {
            id: labelText
            text: root.label
            // метка получает всю нужную ширину, если остаётся место под
            // дорожку (минимум 30 px); иначе ужимается и обрезается
            width: Math.min(implicitWidth,
                            Math.max(40, parent.width - valueText.width
                                     - 30 - Theme.spaceSM * 2))
            elide: Text.ElideRight
            color: Theme.textSecondary
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontSmallPx
            verticalAlignment: Text.AlignVCenter
            visible: root.label !== ""
        }

        Item {
            id: trackArea
            implicitWidth: 130
            width: Math.max(30, parent.width - labelText.width
                            - valueText.width - Theme.spaceSM * 2)
            implicitHeight: 30
            anchors.verticalCenter: parent.verticalCenter

            Rectangle {
                id: track
                anchors.verticalCenter: parent.verticalCenter
                x: 0
                width: trackArea.width
                height: 6
                radius: 3
                color: Theme.surface3
            }

            Rectangle {
                id: fill
                anchors.verticalCenter: track.verticalCenter
                x: 0
                width: track.width * root.pos
                height: 6
                radius: 3
                color: root.accent
            }

            Rectangle {
                id: handle
                width: 16
                height: 16
                radius: 8
                color: Theme.textPrimary
                anchors.verticalCenter: track.verticalCenter
                x: track.width * root.pos - 8
                Behavior on x { NumberAnimation { duration: 60 } }
            }

            MouseArea {
                anchors.fill: parent
                onPressed: update(mouseX)
                onPositionChanged: update(mouseX)

                function update(mx) {
                    var p = Math.max(0, Math.min(1, mx / track.width))
                    root.value = root.from + (root.to - root.from) * p
                    root.moved(root.value)
                }
            }
        }

        Text {
            id: valueText
            text: root.value.toFixed(root.decimals) + root.suffix
            color: Theme.textPrimary
            font.family: Theme.fontFamilyMono
            font.pixelSize: Theme.fontSmallPx
            verticalAlignment: Text.AlignVCenter
        }
    }
}