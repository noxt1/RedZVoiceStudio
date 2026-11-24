import QtQuick
import Auraloom 1.0

/// Версия main.qml для рендеринга в QQuickWidget (корень = Item).
Item {
    width: 1280
    height: 820

    // фон-градиент
    Rectangle {
        anchors.fill: parent
        gradient: Theme.gradAppBg
    }

    // ------------------------- боковая панель -------------------------
    Rectangle {
        id: sidebar
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 236
        color: Theme.surface0
        border.color: Theme.border
        border.width: 1

        Column {
            anchors.fill: parent
            anchors.margins: Theme.spaceLG
            spacing: Theme.spaceLG

            Row {
                spacing: Theme.spaceSM
                Rectangle {
                    width: 36; height: 36; radius: 10
                    gradient: Theme.gradAccent
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        text: "Auraloom"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontH2Px
                        font.weight: Theme.weightBold
                    }
                    Text {
                        text: "VOICE STUDIO"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 9
                        font.weight: Theme.weightMedium
                        font.letterSpacing: 2.0
                    }
                }
            }

            Divider {}

            SideNav {
                id: nav
                width: parent.width
                height: parent.height - 150
                currentIndex: 0
                items: [
                    { "index": 0, "icon": "icons/home.svg", "label": "Главная" },
                    { "index": 1, "icon": "icons/mic.svg", "label": "Голоса" },
                    { "index": 2, "icon": "icons/settings.svg", "label": "Настройки" },
                    { "index": 3, "icon": "icons/history.svg", "label": "История" }
                ]
                onItemActivated: (idx) => window.currentPage = idx
            }

            Item { height: 1 }

            StatusPill {
                id: enginePill
                width: parent.width
                text: appState.engineStatusText()
                state: {
                    var s = appState.engineState
                    if (s === "READY") return "ready"
                    if (s === "LOADING") return "loading"
                    if (s === "ERROR") return "error"
                    return "idle"
                }
            }
        }
    }

    // ------------------------- контент -------------------------
    property int currentPage: 0

    Loader {
        id: pageLoader
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spaceLG
        source: {
            if (currentPage === 0) return "pages/HomePage.qml"
            if (currentPage === 1) return "pages/VoicesPage.qml"
            if (currentPage === 2) return "pages/SettingsPage.qml"
            return "pages/HistoryPage.qml"
        }
    }

    Connections {
        target: appState
        function onStatusMessage(text, kind) {
            toast.show(text, kind)
        }
    }

    Toast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.spaceXL
    }
}