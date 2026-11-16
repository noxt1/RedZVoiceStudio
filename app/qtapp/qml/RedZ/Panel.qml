import QtQuick
import RedZ 1.0

/// Карточка панели (как в референсе): заголовок + содержимое, тонкая рамка.
Item {
    id: root

    property string title: ""
    property string subtitle: ""
    property alias contentItem: column.children

    implicitWidth: 300
    implicitHeight: column.implicitHeight + 70

    Column {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.spaceMD
        spacing: Theme.spaceMD

        // заголовок панели
        Row {
            spacing: Theme.spaceXS
            Text {
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontBodyPx
                font.weight: Theme.weightSemiBold
            }
            Text {
                text: root.subtitle
                color: Theme.textMuted
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontTinyPx
                anchors.verticalCenter: parent.verticalCenter
            }
            Item { width: 1; height: 1 }
        }

        Divider {}

        // содержимое
        Item {
            anchors.fill: parent
            width: parent.width
            height: implicitHeight
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusCard
        color: Theme.surface0
        border.color: Theme.border
        border.width: 1
        z: -1
    }
}