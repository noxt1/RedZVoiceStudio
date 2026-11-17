import QtQuick
import RedZ 1.0

/// Нижняя строка состояния из референсов:
/// слева версия, по центру «все системы в порядке», справа наушники.
Rectangle {
    id: root

    implicitHeight: 38
    color: "#070B24"

    Rectangle {
        height: 1
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        color: Theme.border
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        LogoMark { size: 20; withTile: false; glow: 0.0 }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: brandName + "  v" + window.version
            color: Theme.textMuted
            font.family: Theme.fontFamilyMono
            font.pixelSize: 11
        }
    }

    Row {
        anchors.centerIn: parent
        spacing: 8

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
            text: appState.engineState === "READY" ? "Все системы в порядке"
                 : (appState.engineState === "LOADING" ? "Загрузка моделей…" : "Движок остановлен")
            color: Theme.textSecondary
            font.family: Theme.fontFamilyText
            font.pixelSize: 11
        }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 7

        Icon {
            anchors.verticalCenter: parent.verticalCenter
            source: "icons/volume.svg"
            color: appState.bridgeOn ? Theme.accentCyan : Theme.textMuted
            size: 15
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: appState.bridgeOn ? "Мост в кабель: включён" : "Мост в кабель: выключен"
            color: appState.bridgeOn ? Theme.textSecondary : Theme.textMuted
            font.family: Theme.fontFamilyText
            font.pixelSize: 11
        }
    }
}
