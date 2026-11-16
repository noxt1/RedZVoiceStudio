import QtQuick
import QtQuick.Window
import RedZ 1.0

/// Главное окно RedZ Voice Studio (Qt Quick) — по референсу:
///   • слева сайдбар: вывеска приложения + навигация + закатное свечение
///   • справа страница (Главная / Голоса / Настройки / История / Живой перевод)
///   • снизу общий футер: состояние приложения, ASR · MT · TTS, версия
Window {
    id: window

    width: 1600
    height: 960
    minimumWidth: 1280
    minimumHeight: 840
    visible: true
    color: Theme.bg
    title: "RedZ Voice Studio"
    // настройка «Режим экрана»
    visibility: appState.fullscreen ? Window.FullScreen : Window.Windowed

    property string section: "home"
    // текущая страница в Loader (для проверок/диагностики)
    readonly property var currentPage: pageLoader.item

    readonly property var navItems: [
        { "key": "home",     "icon": "icons/home.svg",      "label": "Главная" },
        { "key": "live",     "icon": "icons/wave.svg",      "label": "Перевод" },
        { "key": "voices",   "icon": "icons/mic.svg",       "label": "Голос" },
        { "key": "settings", "icon": "icons/settings.svg",  "label": "Настройки" },
        { "key": "history",  "icon": "icons/history.svg",   "label": "История" },
        { "key": "phrases",  "icon": "icons/bolt.svg",      "label": "Фразы" }
    ]

    readonly property string version: "1.0.0"

    Rectangle {
        anchors.fill: parent
        gradient: Theme.gradAppBg
    }

    // ==================================================================
    // Сайдбар
    // ==================================================================
    Rectangle {
        id: sidebar
        width: 236
        anchors.top: parent.top
        anchors.bottom: footer.top
        anchors.left: parent.left
        color: Theme.sidebar

        Rectangle {
            width: 1
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            color: Theme.border
        }

        Column {
            anchors.fill: parent

            // ---------- вывеска ----------
            Item {
                width: parent.width
                height: 182

                Column {
                    anchors.centerIn: parent
                    spacing: 3

                    Item {
                        width: 62
                        height: 62
                        anchors.horizontalCenter: parent.horizontalCenter

                        Rectangle {
                            anchors.fill: parent
                            radius: width / 2
                            color: Theme.accent
                            opacity: 0.10
                        }
                        Rectangle {
                            anchors.fill: parent
                            radius: width / 2
                            color: "transparent"
                            border.color: Theme.accentDeep
                            border.width: 1.5
                        }
                        Icon {
                            anchors.centerIn: parent
                            source: "icons/star.svg"
                            color: Theme.accent
                            size: 30
                        }
                    }

                    Item { width: 1; height: 6 }

                    Text {
                        text: "RedZ"
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Theme.accentBright
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 34
                        font.weight: Theme.weightBold
                    }
                    Text {
                        text: "Voice Studio"
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 17
                        font.italic: true
                    }
                    Text {
                        text: "Speak · Translate · Play"
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 11
                        font.italic: true
                    }
                }
            }

            // ---------- навигация ----------
            Column {
                id: navColumn
                x: 12
                width: parent.width - 24
                spacing: 6

                Repeater {
                    model: window.navItems

                    delegate: Item {
                        id: navItem
                        width: navColumn.width
                        height: 46

                        readonly property bool active: window.section === modelData.key
                        property bool hovered: false

                        Rectangle {
                            anchors.fill: parent
                            radius: 10
                            color: navItem.active ? "transparent"
                                 : (navItem.hovered ? Theme.surface1 : "transparent")
                            gradient: navItem.active ? Theme.gradNavActive : null
                            border.color: navItem.active ? Theme.accentDeep : "transparent"
                            border.width: navItem.active ? 1 : 0
                        }

                        Rectangle {
                            width: 3
                            height: 20
                            radius: 2
                            color: Theme.accent
                            anchors.left: parent.left
                            anchors.leftMargin: 2
                            anchors.verticalCenter: parent.verticalCenter
                            visible: navItem.active
                        }

                        Row {
                            anchors.left: parent.left
                            anchors.leftMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 12

                            Icon {
                                source: modelData.icon
                                color: navItem.active ? Theme.accentBright : Theme.textSecondary
                                size: 20
                            }
                            Text {
                                text: modelData.label
                                color: navItem.active ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: Theme.fontBodyPx
                                font.weight: navItem.active ? Theme.weightSemiBold : Theme.weightMedium
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: navItem.hovered = true
                            onExited: navItem.hovered = false
                            onClicked: window.section = modelData.key
                        }
                    }
                }
            }

            Item { width: 1; height: 14 }

            // ---------- закатное свечение внизу ----------
            Item {
                width: parent.width
                height: Math.max(90, sidebar.height - 182 - 264 - 14 - 4)
                clip: true

                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 0.65; color: "#241708" }
                        GradientStop { position: 1.0; color: "#33200C" }
                    }
                    opacity: 0.85
                }

                Rectangle {
                    width: 170
                    height: 170
                    radius: width / 2
                    color: Theme.accent
                    opacity: 0.08
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: -60
                }

                Column {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 18
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 2

                    Icon {
                        source: "icons/star.svg"
                        color: Theme.accent
                        size: 18
                        opacity: 0.85
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    Text {
                        text: "1919 · RedZ RP"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 11
                        font.italic: true
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }
            }
        }
    }

    // ==================================================================
    // Содержимое
    // ==================================================================
    Loader {
        id: pageLoader
        anchors.left: sidebar.right
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: footer.top
        anchors.margins: 18

        source: {
            if (window.section === "voices") return "pages/VoicesPage.qml"
            if (window.section === "settings") return "pages/SettingsPage.qml"
            if (window.section === "history") return "pages/HistoryPage.qml"
            if (window.section === "phrases") return "pages/PhrasesPage.qml"
            if (window.section === "live") return "pages/LivePage.qml"
            return "pages/HomePage.qml"
        }
    }

    // страница просит перейти в другой раздел («Все записи →»)
    Connections {
        target: pageLoader.item
        ignoreUnknownSignals: true
        function onNavigate(key) { window.section = key }
    }

    Connections {
        target: appState
        function onStatusMessage(text, kind) {
            // настройка «Показывать подсказки»: информационные тосты можно выключить
            if (kind === "info" && !appState.hintsOn) return
            toast.show(text, kind)
        }
    }

    Connections {
        target: liveEngine
        function onErrorMessage(msg) { toast.show(msg, "err") }
        function onLogLine(line) { if (line) toast.show(line, "info") }
    }

    // ==================================================================
    // Футер
    // ==================================================================
    Rectangle {
        id: footer
        height: 46
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        color: Theme.surface0

        Rectangle {
            height: 1
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            color: Theme.border
        }

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10

            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: appState.engineState === "READY" ? Theme.success
                     : (appState.engineState === "LOADING" ? Theme.warning : Theme.textMuted)
                anchors.verticalCenter: parent.verticalCenter

                SequentialAnimation on opacity {
                    running: appState.engineState === "LOADING"
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: 600 }
                    NumberAnimation { to: 1.0; duration: 600 }
                }
            }

            Text {
                text: appState.engineState === "LOADING" ? "Загрузка моделей…" : "Приложение готово"
                color: Theme.textSecondary
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontSmallPx
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12

            Repeater {
                model: ["ASR", "MT", "TTS"]

                delegate: Row {
                    spacing: 6
                    anchors.verticalCenter: parent.verticalCenter

                    Rectangle {
                        width: 7
                        height: 7
                        radius: 3.5
                        color: appState.engineState === "READY" ? Theme.success : Theme.textMuted
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: modelData
                        color: Theme.textSecondary
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "·"
                        color: Theme.textMuted
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                        visible: index < 2
                    }
                }
            }

            Text {
                text: "v" + window.version
                color: Theme.textMuted
                font.family: Theme.fontFamilyMono
                font.pixelSize: 11
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    Toast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: footer.top
        anchors.bottomMargin: Theme.spaceLG
    }
}
