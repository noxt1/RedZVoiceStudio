import QtQuick
import RedZ 1.0

/// Боковая навигация: иконка + текст + бейдж. Выделение при активном пункте.
Item {
    id: root

    property string label: ""
    property string iconSource: ""
    property bool active: false
    property int badge: 0

    signal clicked()

    implicitWidth: 200
    implicitHeight: 44

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusControl
        color: root.active ? Theme.surfaceActive : (root.hovered ? Theme.surfaceHover : "transparent")
        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
    }

    Row {
        anchors.centerIn: parent
        anchors.leftMargin: Theme.spaceMD
        spacing: Theme.spaceSM

        Icon {
            source: root.iconSource
            color: root.active ? Theme.accent : Theme.textSecondary
            size: 20
        }

        Text {
            text: root.label
            color: root.active ? Theme.textPrimary : Theme.textSecondary
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontBodyPx
            font.weight: root.active ? Theme.weightSemiBold : Theme.weightMedium
            verticalAlignment: Text.AlignVCenter
        }

        Rectangle {
            width: 20
            height: 20
            radius: 10
            color: Theme.accentDeep
            visible: root.badge > 0
            anchors.left: parent.left
            anchors.leftMargin: Theme.spaceXS
            Text {
                anchors.centerIn: parent
                text: root.badge > 99 ? "99+" : String(root.badge)
                color: Theme.textOnAccent
                font.family: Theme.fontFamilyMono
                font.pixelSize: 10
                font.weight: Theme.weightBold
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onEntered: root.hovered = true
        onExited: root.hovered = false
        onClicked: root.clicked()
    }

    property bool hovered: false
}