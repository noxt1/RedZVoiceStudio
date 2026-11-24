import QtQuick
import Auraloom 1.0

/// Тонкий разделитель.
Item {
    id: root

    property color color: Theme.border
    property real heightValue: 1

    implicitWidth: parent ? parent.width : 200
    implicitHeight: root.heightValue

    Rectangle {
        anchors.fill: parent
        color: root.color
    }
}