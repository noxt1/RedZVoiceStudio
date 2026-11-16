import QtQuick
import RedZ 1.0

/// Кнопка только с иконкой (иконка в квадрате, hover-подсветка).
Item {
    id: root

    property string iconSource: ""
    property color color: Theme.textSecondary
    property color hoverColor: Theme.accentBright
    property int size: 36
    property int iconSize: 18
    property bool checked: false

    signal clicked()

    implicitWidth: root.size
    implicitHeight: root.size

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusInner
        color: {
            if (!root.enabled) return "transparent"
            if (root.checked) return Theme.surfaceActive
            return root.hovered ? Theme.surfaceHover : "transparent"
        }
        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
    }

    Icon {
        source: root.iconSource
        color: root.checked ? Theme.accent : (root.hovered ? root.hoverColor : root.color)
        size: root.iconSize
        anchors.centerIn: parent
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.clicked()
        onEntered: root.hovered = true
        onExited: root.hovered = false
    }

    property bool hovered: false
}