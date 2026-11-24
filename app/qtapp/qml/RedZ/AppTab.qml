import QtQuick
import RedZ 1.0

/// Верхняя вкладка приложения (как в референсе).
Item {
    id: root

    property string label: ""
    property bool active: false

    signal clicked()

    implicitWidth: 120
    implicitHeight: 44

    Rectangle {
        anchors.fill: parent
        color: root.active ? Theme.surface1 : "transparent"
        border.color: root.active ? Theme.accent : "transparent"
        border.width: root.active ? 2 : 0
        radius: Theme.radiusControl
        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
    }

    Text {
        anchors.centerIn: parent
        text: root.label
        color: root.active ? Theme.textPrimary : Theme.textSecondary
        font.family: Theme.fontFamilyText
        font.pixelSize: Theme.fontBodyPx
        font.weight: root.active ? Theme.weightSemiBold : Theme.weightMedium
    }

    MouseArea {
        anchors.fill: parent
        onClicked: root.clicked()
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
    }
}