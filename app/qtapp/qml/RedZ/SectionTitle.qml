import QtQuick
import RedZ 1.0

/// Заголовок секции: малая капслок-подпись + опциональная кнопка действия.
Item {
    id: root

    property string text: ""
    property string actionText: ""
    property string actionIcon: ""
    signal actionClicked()

    implicitWidth: parent ? parent.width : 300
    implicitHeight: 28

    Row {
        anchors.fill: parent
        spacing: Theme.spaceSM

        Text {
            text: root.text.toUpperCase()
            color: Theme.accent
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontTinyPx
            font.weight: Theme.weightBold
            font.letterSpacing: 1.4
            verticalAlignment: Text.AlignVCenter
        }

        Item { width: Math.max(0, parent.width - 400) }

        Text {
            text: root.actionText
            color: Theme.accentBright
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontSmallPx
            font.weight: Theme.weightMedium
            verticalAlignment: Text.AlignVCenter
            visible: root.actionText !== ""
        }

        Icon {
            source: root.actionIcon
            color: Theme.accentBright
            size: 16
            visible: root.actionIcon !== ""
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.actionText !== "" || root.actionIcon !== ""
        onClicked: root.actionClicked()
        hoverEnabled: true
        cursorShape: (root.actionText !== "" || root.actionIcon !== "") ? Qt.PointingHandCursor : Qt.ArrowCursor
    }
}