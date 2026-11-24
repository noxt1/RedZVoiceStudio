import QtQuick
import Auraloom 1.0

/// Заголовок страницы: заголовок + подзаголовок + действия справа.
Item {
    id: root

    property string title: ""
    property string subtitle: ""
    property string primaryAction: ""
    property string primaryIcon: ""
    signal primaryClicked()

    implicitWidth: parent ? parent.width : 600
    implicitHeight: 64

    Row {
        anchors.fill: parent
        spacing: Theme.spaceMD

        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.spaceXXS

            Text {
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontH1Px
                font.weight: Theme.weightSemiBold
            }

            Text {
                text: root.subtitle
                color: Theme.textSecondary
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontSmallPx
                visible: root.subtitle !== ""
            }
        }

        Item { width: 1; height: 1 }

        AppButton {
            text: root.primaryAction
            iconSource: root.primaryIcon
            visible: root.primaryAction !== ""
            anchors.verticalCenter: parent.verticalCenter
            onClicked: root.primaryClicked()
        }
    }
}