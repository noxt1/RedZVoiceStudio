import QtQuick
import RedZ 1.0

/// Главная — по референсу.
///
///   • верхняя карточка движка: статус, запуск/остановка, VRAM справа
///   • две карточки: «Мой голос» (исходящий перевод) и «Собеседник» (входящий)
///   • «Последние переводы»
///   • правая колонка: VRAM + фирменная панель
Item {
    id: page

    signal navigate(string key)

    // ---- состояние экрана ----
    property bool continuous: false
    property real micLevel: 0.0

    readonly property bool ready: appState.engineState === "READY"

    // ---- модели списков ----
    property var micItems: []
    property int micIndex: -1

    property var sourceItems: []
    property int sourceIndex: -1

    readonly property var langItems: [
        { "label": "🇪🇸  Испанский", "value": "es" },
        { "label": "🇺🇸  Английский", "value": "en" },
        { "label": "🇮🇹  Итальянский", "value": "it" },
        { "label": "🤠  Old West", "value": "ow" }
    ]
    readonly property var peerLangItems: [
        { "label": "🇪🇸  Испанский", "value": "es" },
        { "label": "🇺🇸  Английский", "value": "en" },
        { "label": "🇮🇹  Итальянский", "value": "it" },
        { "label": "🇷🇺  Русский", "value": "ru" }
    ]
    readonly property var voiceItems: [
        { "label": "María (ES)", "value": "maria" },
        { "label": "Diego (ES)", "value": "diego" },
        { "label": "Claude (ES)", "value": "claude" }
    ]

    property int langIndex: 0
    property int peerLangIndex: 0
    property int voiceIndex: 0

    // ---- данные ----
    function refreshMics() {
        var devs = appState.inputDevices
        var out = []
        for (var i = 0; i < devs.length; i++) {
            out.push({ "label": devs[i].name, "value": devs[i].id })
        }
        page.micItems = out
        var cur = appState.inDevice
        var idx = -1
        for (var j = 0; j < out.length; j++) {
            if (out[j].value === cur) idx = j
        }
        page.micIndex = idx >= 0 ? idx : (out.length > 0 ? 0 : -1)
    }

    function refreshSources() {
        var devs = appState.outputDevices
        var out = []
        for (var i = 0; i < devs.length; i++) {
            out.push({ "label": devs[i].name, "value": devs[i].id })
        }
        page.sourceItems = out
        page.sourceIndex = out.length > 0 ? 0 : -1
    }

    function selectMic(i) {
        if (i < 0 || i >= page.micItems.length) return
        var id = page.micItems[i].value
        page.micIndex = i
        appState.setInDevice(id)
        liveEngine.setMicDevice(id)
    }

    function setMode(cont) {
        if (page.continuous === cont) return
        page.continuous = cont
        liveEngine.setContinuous(cont)
    }

    Component.onCompleted: {
        refreshMics()
        refreshSources()
    }

    Connections {
        target: appState
        function onDevicesChanged() { page.refreshMics(); page.refreshSources() }
    }

    Connections {
        target: liveEngine
        function onLevelChanged(v) { page.micLevel = v }
    }

    // ==================================================================
    // Раскладка
    // ==================================================================
    Row {
        anchors.fill: parent
        spacing: 16

        // ---------- левая колонка ----------
        Column {
            id: mainCol
            width: parent.width - 320 - 16
            height: parent.height
            spacing: 16

            // ======================= карточка движка =======================
            Card {
                width: mainCol.width
                height: 96
                padding: 18

                Item {
                    anchors.fill: parent

                    Row {
                        id: engineLeft
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 14

                    // статус-кружок
                    Item {
                        width: 52
                        height: 52
                        anchors.verticalCenter: parent.verticalCenter

                        Rectangle {
                            anchors.fill: parent
                            radius: width / 2
                            color: page.ready ? Theme.success : Theme.surface2
                            opacity: page.ready ? 0.18 : 1
                        }
                        Rectangle {
                            width: 22
                            height: 22
                            radius: 11
                            anchors.centerIn: parent
                            color: page.ready ? Theme.success
                                 : (appState.engineState === "LOADING" ? Theme.warning : Theme.textMuted)
                        }
                    }

                    // заголовок + подпись
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3

                        Row {
                            spacing: 8
                            Text {
                                text: "Движок:"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 21
                                font.weight: Theme.weightSemiBold
                            }
                            Text {
                                text: {
                                    var s = appState.engineState
                                    if (s === "READY") return "Готов к работе"
                                    if (s === "LOADING") return "Загрузка моделей…"
                                    if (s === "ERROR") return "Ошибка"
                                    return "Остановлен"
                                }
                                color: {
                                    var s = appState.engineState
                                    if (s === "READY") return Theme.success
                                    if (s === "LOADING") return Theme.warning
                                    if (s === "ERROR") return Theme.danger
                                    return Theme.textMuted
                                }
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 21
                                font.weight: Theme.weightBold
                            }
                        }

                        Text {
                            text: page.ready ? "Модели загружены" + (appState.gpuName ? " · " + appState.gpuName : "")
                                             : "Модели не загружены"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                        }
                    }

                    }

                    Row {
                        id: engineRight
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 12

                    // запуск
                    Rectangle {
                        width: 196
                        height: 54
                        radius: 11
                        anchors.verticalCenter: parent.verticalCenter
                        enabled: !page.ready
                        opacity: page.ready ? 0.45 : 1.0
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: "#16341F" }
                            GradientStop { position: 1.0; color: "#10251A" }
                        }
                        border.color: Theme.success
                        border.width: 1

                        Glow {
                            anchors.fill: parent
                            glowColor: Theme.success
                            intensity: 0.75
                            spread: 13
                            cornerRadius: 11
                        }

                        Row {
                            anchors.centerIn: parent
                            spacing: 8
                            Icon { source: "icons/play.svg"; color: Theme.success; size: 16 }
                            Text {
                                text: "Запустить модель"
                                color: "#D8F5E3"
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 14
                                font.weight: Theme.weightMedium
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: if (!page.ready) appState.startEngine()
                        }
                    }

                    // остановка
                    Rectangle {
                        width: 196
                        height: 54
                        radius: 11
                        anchors.verticalCenter: parent.verticalCenter
                        enabled: page.ready
                        opacity: page.ready ? 1.0 : 0.45
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: "#3A1B1A" }
                            GradientStop { position: 1.0; color: "#2A1312" }
                        }
                        border.color: Theme.danger
                        border.width: 1

                        Glow {
                            anchors.fill: parent
                            glowColor: Theme.danger
                            intensity: 0.65
                            spread: 13
                            cornerRadius: 11
                        }

                        Row {
                            anchors.centerIn: parent
                            spacing: 8
                            Icon { source: "icons/stop.svg"; color: Theme.danger; size: 16 }
                            Text {
                                text: "Остановить модель"
                                color: "#F7DEDC"
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 14
                                font.weight: Theme.weightMedium
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: if (page.ready) appState.stopEngine()
                        }
                    }
                    }
                }
            }

            // ======================= две карточки =======================
            Row {
                width: mainCol.width
                height: 360
                spacing: 16

                // -------- Мой голос --------
                Card {
                    width: (parent.width - 16) / 2
                    height: parent.height

                    Column {
                        anchors.fill: parent
                        spacing: 12

                        Row {
                            width: parent.width
                            spacing: 12

                            Rectangle {
                                width: 40; height: 40; radius: 11
                                color: "#241B10"
                                border.color: Theme.accentDeep
                                border.width: 1
                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/mic.svg"
                                    color: Theme.accent
                                    size: 20
                                }
                            }

                            Column {
                                spacing: 3
                                width: parent.width - 52
                                anchors.verticalCenter: parent.verticalCenter
                                Row {
                                    spacing: 8
                                    Text {
                                        text: "Мой голос"
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 20
                                        font.weight: Theme.weightSemiBold
                                    }
                                    StatusPill {
                                        text: page.ready ? "Готов" : "Не готов"
                                        pillState: page.ready ? "ready" : "idle"
                                        pillHeight: 22
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                                Text {
                                    text: "Русский → Испанский, Английский, Итальянский"
                                    width: parent.width
                                    elide: Text.ElideRight
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 12
                                }
                            }
                        }

                        // ---- микрофон ----
                        Row {
                            width: parent.width
                            spacing: 8

                            Icon {
                                source: "icons/mic.svg"
                                color: Theme.textMuted
                                size: 15
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Микрофон:"
                                width: 118
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            AppCombo {
                                width: parent.width - 150
                                model: page.micItems
                                currentIndex: page.micIndex
                                currentText: page.micIndex >= 0 && page.micItems.length > 0
                                             ? page.micItems[page.micIndex].label : "нет устройств"
                                onActivated: (i) => page.selectMic(i)
                            }
                        }

                        // ---- язык перевода ----
                        Row {
                            width: parent.width
                            spacing: 8

                            Icon {
                                source: "icons/translate.svg"
                                color: Theme.textMuted
                                size: 15
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Язык перевода:"
                                width: 118
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            AppCombo {
                                width: parent.width - 150
                                model: page.langItems
                                currentIndex: page.langIndex
                                currentText: page.langItems[page.langIndex].label
                                onActivated: (i) => {
                                    page.langIndex = i
                                    liveEngine.setLang(page.langItems[i].value)
                                }
                            }
                        }

                        // ---- режимы ----
                        Row {
                            width: parent.width
                            spacing: 14

                            AppSwitch {
                                id: pttSwitch
                                label: "Push-to-Talk"
                                onToggled: (on) => page.setMode(!on)
                            }

                            Rectangle {
                                width: 1
                                height: 20
                                color: Theme.border
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            AppSwitch {
                                id: contSwitch
                                label: "Непрерывный режим"
                                onToggled: (on) => page.setMode(on)
                            }
                        }

                        Binding { target: pttSwitch; property: "checked"; value: !page.continuous }
                        Binding { target: contSwitch; property: "checked"; value: page.continuous }

                        // ---- кнопка PTT ----
                        Rectangle {
                            id: pttBtn
                            width: parent.width
                            height: 62
                            radius: 12
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: pttArea.pressed ? Theme.accentBright : "#C79B4E" }
                                GradientStop { position: 1.0; color: pttArea.pressed ? Theme.accent : "#8A5D1E" }
                            }
                            border.color: Theme.accentBright
                            border.width: pttArea.pressed ? 2 : 1

                            Glow {
                                anchors.fill: parent
                                glowColor: Theme.accent
                                intensity: pttArea.pressed ? 0.9 : 0.55
                                spread: 14
                                cornerRadius: 12
                            }

                            Row {
                                anchors.centerIn: parent
                                spacing: 10
                                Icon {
                                    source: "icons/mic.svg"
                                    color: Theme.accentInk
                                    size: 22
                                }
                                Text {
                                    text: pttArea.pressed ? "Говорю…" : "Говорить (PTT)"
                                    color: Theme.accentInk
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 17
                                    font.weight: Theme.weightSemiBold
                                }
                            }

                            MouseArea {
                                id: pttArea
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onPressed: liveEngine.pressToTalk()
                                onReleased: liveEngine.releaseToTalk()
                            }
                        }

                        // ---- уровень ----
                        Row {
                            width: parent.width
                            spacing: 3

                            Repeater {
                                model: 26
                                delegate: Rectangle {
                                    width: 6
                                    height: 20
                                    radius: 3
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: index < Math.round(page.micLevel * 26)
                                         ? (index < 17 ? Theme.success
                                            : (index < 22 ? Theme.warning : "#E08A3C"))
                                         : Theme.surface2
                                    Behavior on color { ColorAnimation { duration: 60 } }
                                }
                            }

                            Item { width: 1; height: 1 }

                            Icon {
                                source: "icons/volume.svg"
                                color: Theme.textMuted
                                size: 18
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }

                // -------- Собеседник --------
                Card {
                    width: (parent.width - 16) / 2
                    height: parent.height

                    Column {
                        anchors.fill: parent
                        spacing: 12

                        Row {
                            width: parent.width
                            spacing: 12

                            Rectangle {
                                width: 40; height: 40; radius: 11
                                color: "#241B10"
                                border.color: Theme.accentDeep
                                border.width: 1
                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/layers.svg"
                                    color: Theme.accent
                                    size: 20
                                }
                            }

                            Column {
                                spacing: 3
                                width: parent.width - 52
                                anchors.verticalCenter: parent.verticalCenter
                                Row {
                                    spacing: 8
                                    Text {
                                        text: "Собеседник"
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 20
                                        font.weight: Theme.weightSemiBold
                                    }
                                    StatusPill {
                                        text: liveEngine.captureOn ? "Активен" : "Ожидание"
                                        pillState: liveEngine.captureOn ? "ready" : "idle"
                                        pillHeight: 22
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                                Text {
                                    text: "Испанский → Русский"
                                    width: parent.width
                                    elide: Text.ElideRight
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 12
                                }
                            }
                        }

                        // ---- источник речи ----
                        Row {
                            width: parent.width
                            spacing: 8

                            Icon {
                                source: "icons/volume.svg"
                                color: Theme.textMuted
                                size: 15
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Источник речи:"
                                width: 118
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            AppCombo {
                                width: parent.width - 150
                                model: page.sourceItems.length > 0
                                       ? page.sourceItems
                                       : [{ "label": "Игра / Discord", "value": "game" }]
                                currentIndex: page.sourceIndex >= 0 ? page.sourceIndex : 0
                                currentText: page.sourceIndex >= 0 && page.sourceItems.length > 0
                                             ? page.sourceItems[page.sourceIndex].label : "Игра / Discord"
                                onActivated: (i) => { page.sourceIndex = i }
                            }
                        }

                        // ---- язык собеседника ----
                        Row {
                            width: parent.width
                            spacing: 8

                            Icon {
                                source: "icons/translate.svg"
                                color: Theme.textMuted
                                size: 15
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Язык собеседника:"
                                width: 118
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            AppCombo {
                                width: parent.width - 150
                                model: page.peerLangItems
                                currentIndex: page.peerLangIndex
                                currentText: page.peerLangItems[page.peerLangIndex].label
                                onActivated: (i) => {
                                    page.peerLangIndex = i
                                    liveEngine.setPeerLang(page.peerLangItems[i].value)
                                }
                            }
                        }

                        // ---- голос ----
                        Row {
                            width: parent.width
                            spacing: 8

                            Icon {
                                source: "icons/mic.svg"
                                color: Theme.textMuted
                                size: 15
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Голос:"
                                width: 118
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            AppCombo {
                                width: parent.width - 150
                                model: page.voiceItems
                                currentIndex: page.voiceIndex
                                currentText: page.voiceItems[page.voiceIndex].label
                                onActivated: (i) => { page.voiceIndex = i }
                            }
                        }

                        // ---- включить перевод ----
                        Rectangle {
                            id: peerBtn
                            width: parent.width
                            height: 56
                            radius: 12
                            color: liveEngine.captureOn ? "#1A2B3B" : "transparent"
                            border.color: liveEngine.captureOn ? Theme.incoming : Theme.borderStrong
                            border.width: 1.5

                            Glow {
                                anchors.fill: parent
                                glowColor: liveEngine.captureOn ? Theme.incoming : Theme.accentDeep
                                intensity: liveEngine.captureOn ? 0.7 : 0.28
                                spread: 12
                                cornerRadius: 12
                            }

                            Row {
                                anchors.centerIn: parent
                                spacing: 10
                                Icon {
                                    source: "icons/volume.svg"
                                    color: liveEngine.captureOn ? Theme.incoming : Theme.textPrimary
                                    size: 20
                                }
                                Text {
                                    text: liveEngine.captureOn ? "Выключить перевод" : "Включить перевод"
                                    color: liveEngine.captureOn ? Theme.incoming : Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 16
                                    font.weight: Theme.weightMedium
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (liveEngine.captureOn) liveEngine.stopCapture()
                                    else liveEngine.startCapture()
                                }
                            }
                        }

                        // ---- индикаторы ----
                        Row {
                            width: parent.width
                            spacing: 10

                            Icon {
                                source: "icons/wave.svg"
                                color: liveEngine.captureOn ? Theme.incoming : Theme.textMuted
                                size: 18
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: liveEngine.captureOn ? "Распознавание…" : "Распознавание выключено"
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 12
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Item { width: 1; height: 1 }

                            Rectangle {
                                width: 8; height: 8; radius: 4
                                color: liveEngine.busy ? Theme.warning : Theme.success
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Воспроизведение"
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 12
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }
            }

            // ======================= история =======================
            Card {
                width: mainCol.width
                height: mainCol.height - 96 - 360 - 32
                padding: 18

                Column {
                    anchors.fill: parent
                    spacing: 8

                    Item {
                        width: parent.width
                        height: 26

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 10

                            Icon {
                                source: "icons/history.svg"
                                color: Theme.accent
                                size: 20
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Последние переводы"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 17
                                font.weight: Theme.weightSemiBold
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        Text {
                            text: "Все записи →"
                            color: Theme.accent
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        MouseArea {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 116
                            height: 26
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.navigate("history")
                        }
                    }

                    Text {
                        text: "Пока нет переводов — нажми «Говорить (PTT)»."
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                        visible: historyModel.count() === 0
                    }

                    ListView {
                        width: parent.width
                        height: parent.height - 34
                        clip: true
                        spacing: 2
                        model: historyModel

                        delegate: Item {
                            id: row
                            width: ListView.view.width
                            height: 44

                            required property string dir
                            required property string ru
                            required property string es
                            required property string time

                            Rectangle {
                                anchors.fill: parent
                                radius: 8
                                color: rowHover.hovered ? Theme.surface1 : "transparent"
                            }

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 12

                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: row.dir === "out" ? Theme.incoming : Theme.success
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    text: row.dir === "out" ? "RU → ES" : "ES → RU"
                                    width: 66
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyMono
                                    font.pixelSize: 11
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    text: row.dir === "out" ? row.es : row.ru
                                    width: parent.width - 260
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 14
                                    elide: Text.ElideRight
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    text: row.time
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyMono
                                    font.pixelSize: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Rectangle {
                                    width: 28; height: 28; radius: 14
                                    color: rowPlay.containsMouse ? Theme.surface3 : Theme.surface2
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon {
                                        anchors.centerIn: parent
                                        source: "icons/play.svg"
                                        color: Theme.textSecondary
                                        size: 12
                                    }
                                    MouseArea {
                                        id: rowPlay
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: liveEngine.replay(row.ru)
                                    }
                                }
                            }

                            MouseArea {
                                id: rowHover
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.NoButton
                                z: -1
                            }
                        }
                    }
                }
            }
        }

        // ---------- правая колонка ----------
        Column {
            width: 320
            height: parent.height
            spacing: 16

            // ---- VRAM ----
            Card {
                width: parent.width
                height: 96
                padding: 16

                Row {
                    width: parent.width
                    spacing: 12

                    Rectangle {
                        width: 40; height: 40; radius: 11
                        color: "#241B10"
                        border.color: Theme.accentDeep
                        border.width: 1
                        Icon {
                            anchors.centerIn: parent
                            source: "icons/cpu.svg"
                            color: Theme.accent
                            size: 20
                        }
                    }

                    Column {
                        spacing: 3
                        anchors.verticalCenter: parent.verticalCenter
                        Text {
                            text: "VRAM"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 10
                            font.weight: Theme.weightBold
                            font.letterSpacing: 1.4
                        }
                        Text {
                            text: appState.vramTotal > 0
                                  ? (appState.vramUsed / 1024).toFixed(1) + " / "
                                    + Math.round(appState.vramTotal / 1024) + " GB"
                                  : "нет данных"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 15
                            font.weight: Theme.weightSemiBold
                        }
                    }
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 6
                    radius: 3
                    color: Theme.surface2

                    Rectangle {
                        width: parent.width * (appState.vramTotal > 0
                                               ? Math.min(1, appState.vramUsed / appState.vramTotal)
                                               : 0)
                        height: parent.height
                        radius: 3
                        gradient: Theme.gradAccent
                    }
                }
            }

            // ---- фирменная панель ----
            Card {
                width: parent.width
                height: parent.height - 96 - 16
                padding: 22
                topColor: "#241A0E"
                bottomColor: "#120E09"
                borderColor: Theme.accentDeep

                Column {
                    anchors.fill: parent
                    spacing: 10

                    Item { width: 1; height: 6 }

                    Icon {
                        source: "icons/star.svg"
                        color: Theme.accent
                        size: 46
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Text {
                        text: "RedZ Voice Studio"
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        color: Theme.accentBright
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 25
                        font.weight: Theme.weightBold
                    }

                    Text {
                        text: "Ваш голос\nна любом языке"
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 15
                        font.italic: true
                        lineHeight: 1.15
                    }

                    Rectangle {
                        width: 60
                        height: 1
                        color: Theme.accentDeep
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Item { width: 1; height: 4 }

                    Repeater {
                        model: [
                            "Распознавание речи",
                            "Мгновенный перевод",
                            "Высококачественный синтез"
                        ]

                        delegate: Row {
                            width: parent.width
                            spacing: 10

                            Rectangle {
                                width: 20; height: 20; radius: 10
                                color: "#2A1F0F"
                                border.color: Theme.accentDeep
                                border.width: 1
                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/check.svg"
                                    color: Theme.accent
                                    size: 11
                                }
                            }
                            Text {
                                text: modelData
                                width: parent.width - 34
                                wrapMode: Text.WordWrap
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }

                    Item { width: 1; height: 1 }

                    Icon {
                        source: "icons/star.svg"
                        color: Theme.accent
                        size: 96
                        opacity: 0.75
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Item { width: 1; height: 1 }
                }
            }
        }
    }
}
