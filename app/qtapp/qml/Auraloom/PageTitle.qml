import QtQuick
import Auraloom 1.0

/// Шапка страницы: карточка с иконкой, заголовком и подзаголовком.
Item {
    id: root

    property string title: ""
    property string subtitle: ""
    property string iconSource: ""
    property color accentColor: Theme.accent

    implicitWidth: parent ? parent.width : 400
    implicitHeight: 92

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusCard
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.cardTop }
            GradientStop { position: 1.0; color: Theme.cardBottom }
        }
        border.color: Theme.border
        border.width: 1
    }

    Row {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        Rectangle {
            width: 46
            height: 46
            radius: 12
            color: Theme.accentTile
            border.color: Theme.accentDeep
            border.width: 1
            anchors.verticalCenter: parent.verticalCenter

            Glow {
                anchors.fill: parent
                glowColor: root.accentColor
                intensity: 0.25
                spread: 6
                cornerRadius: 12
            }

            Icon {
                anchors.centerIn: parent
                source: root.iconSource
                color: root.accentColor
                size: 23
            }
        }

        Column {
            spacing: 2
            anchors.verticalCenter: parent.verticalCenter

            Text {
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.fontFamilyText
                font.pixelSize: 23
                font.weight: Theme.weightSemiBold
            }
            Text {
                text: root.subtitle
                color: Theme.textSecondary
                font.family: Theme.fontFamilyText
                font.pixelSize: 12
            }
        }
    }
}
