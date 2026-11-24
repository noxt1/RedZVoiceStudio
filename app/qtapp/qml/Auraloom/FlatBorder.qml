import QtQuick
import Auraloom 1.0

/// Тонкая граница (flat border) для карточек и контролов.
Item {
    id: root

    property color color: Theme.border
    property real borderWidth: 0.5
    property real cornerRadius: Theme.radiusInner

    implicitWidth: 0
    implicitHeight: 0

    Rectangle {
        anchors.fill: parent
        radius: root.cornerRadius
        border.color: root.color
        border.width: root.borderWidth
        color: "transparent"
    }
}