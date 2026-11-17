import QtQuick
import RedZ 1.0

/// Верхний баннер из референсов: знак, название, подпись, волны, статус.
Item {
    id: root

    implicitWidth: 640
    implicitHeight: 96
    property string subtitle: brandTagline

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusCard
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#101540" }
            GradientStop { position: 1.0; color: "#0A0E2C" }
        }
        border.width: 1
        border.color: Theme.border
        clip: true

        NeonWave {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: parent.width * 0.64
            opacityBoost: 1.0
        }

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 16

            LogoMark { size: 58 }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1

                Text {
                    text: brandName
                    color: Theme.textPrimary
                    font.family: Theme.fontFamilyBrand
                    font.pixelSize: 30
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

        // статус справа
        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            width: pillRow.width + 24
            height: 32
            radius: 16
            color: "#0B1030"
            border.width: 1
            border.color: appState.engineState === "READY" ? Theme.successDeep : Theme.borderStrong

            Row {
                id: pillRow
                anchors.centerIn: parent
                spacing: 7

                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: appState.engineState === "READY" ? Theme.success
                         : (appState.engineState === "LOADING" ? Theme.warning : Theme.textMuted)
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: appState.engineState === "READY" ? "Готов к работе"
                         : (appState.engineState === "LOADING" ? "Загрузка…" : "Остановлен")
                    color: Theme.textPrimary
                    font.family: Theme.fontFamilyText
                    font.pixelSize: 12
                }
            }
        }
    }
}
