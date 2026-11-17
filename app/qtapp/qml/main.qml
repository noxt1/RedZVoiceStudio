import QtQuick
import QtQuick.Window
import RedZ 1.0

/// Главное окно Auraloom (Qt Quick) — по референсу:
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
    title: brandName
    // настройка «Режим экрана»
    visibility: appState.fullscreen ? Window.FullScreen : Window.Windowed

    property string section: "home"
    // текущая страница в Loader (для проверок/диагностики)
    readonly property var currentPage: pageLoader.item

    readonly property var navItems: [
        { "key": "home",     "icon": "icons/home.svg",      "label": "Главная" },
        { "key": "live",     "icon": "icons/wave.svg",      "label": "Перевод" },
        { "key": "voices",   "icon": "icons/mic.svg",       "label": "Голос" },
        { "key": "models",   "icon": "icons/layers.svg",    "label": "Модели" },
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
                    spacing: 4

                    LogoMark {
                        size: 66
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Item { width: 1; height: 4 }

                    Text {
                        text: brandShort
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 31
                        font.weight: Theme.weightSemiBold
                        font.letterSpacing: 0.4
                    }
                    Text {
                        text: brandTagline
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 11
                        font.letterSpacing: 0.6
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
                            radius: Theme.radiusControl
                            color: navItem.active ? "transparent"
                                 : (navItem.hovered ? Theme.surface1 : "transparent")
                            gradient: navItem.active ? Theme.gradNavActive : null
                            border.color: navItem.active ? Theme.accent : "transparent"
                            border.width: navItem.active ? 1 : 0

                            Glow {
                                anchors.fill: parent
                                glowColor: Theme.accent
                                intensity: navItem.active ? 0.5 : 0.0
                                cornerRadius: Theme.radiusControl
                            }
                        }

                        Row {
                            anchors.left: parent.left
                            anchors.leftMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 12

                            Icon {
                                source: modelData.icon
                                color: navItem.active ? "#FFFFFF" : Theme.textSecondary
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
                        GradientStop { position: 0.6; color: "#0C1236" }
                        GradientStop { position: 1.0; color: "#111A4A" }
                    }
                    opacity: 0.9
                }

                Rectangle {
                    width: 180
                    height: 180
                    radius: width / 2
                    color: Theme.accentCyan
                    opacity: 0.10
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: -70
                }

                NeonWave {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 90
                    opacityBoost: 0.7
                }

                Text {
                    text: "Auraloom · v" + window.version
                    color: Theme.textMuted
                    font.family: Theme.fontFamilyMono
                    font.pixelSize: 10
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 12
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }

    // ==================================================================
    // Содержимое
    // ==================================================================
    // фирменное свечение и волны под содержимым страницы
    Item {
        anchors.left: sidebar.right
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: footer.top
        clip: true

        Rectangle {
            width: 520
            height: 520
            radius: width / 2
            x: parent.width - 260
            y: -300
            color: Theme.accent
            opacity: 0.16
        }

        NeonWave {
            anchors.right: parent.right
            anchors.top: parent.top
            width: Math.min(760, parent.width * 0.7)
            height: 230
        }
    }

    Loader {
        id: pageLoader
        anchors.left: sidebar.right
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: footer.top
        anchors.margins: 18
        asynchronous: false

        source: {
            if (window.section === "voices") return "pages/VoicesPage.qml"
            if (window.section === "settings") return "pages/SettingsPage.qml"
            if (window.section === "history") return "pages/HistoryPage.qml"
            if (window.section === "phrases") return "pages/PhrasesPage.qml"
            if (window.section === "live") return "pages/LivePage.qml"
            if (window.section === "models") return "pages/ModelsPage.qml"
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
