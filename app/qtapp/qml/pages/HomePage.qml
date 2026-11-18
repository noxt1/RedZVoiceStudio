import QtQuick
import RedZ 1.0

/// Главная — по композиции референсов 09/10:
///   • герой-баннер с знаком и волнами
///   • карточка «Живой перевод»: орб, статус, волна, кнопки
///   • справа: направление перевода, режим качества, состояние моделей
///   • снизу: последние переводы и быстрые действия
Item {
    id: page

    signal navigate(string key)

    // ---- состояние экрана (сохранено для совместимости) ----
    property bool continuous: false
    property real micLevel: 0.0

    readonly property bool ready: appState.engineState === "READY"
    readonly property bool listening: liveEngine.captureOn

    readonly property var langItems: [
        { "label": "🇪🇸  Испанский", "value": "es" },
        { "label": "🇺🇸  Английский", "value": "en" },
        { "label": "🇮🇹  Итальянский", "value": "it" },
        { "label": "🤠  Old West", "value": "ow" }
    ]
    readonly property var peerLangItems: [
        { "label": "🇪🇸  Испанский", "value": "es" },
        { "label": "🇺🇸  Английский", "value": "en" },
        { "label": "🇮🇹  Итальянский", "value": "it" }
    ]
    readonly property var voiceItems: [
        { "label": "María (ES)", "value": "maria" },
        { "label": "Diego (ES)", "value": "diego" },
        { "label": "Claude (ES)", "value": "claude" }
    ]

    property int langIndex: 0
    property int peerLangIndex: 0
    property int voiceIndex: 0

    // ---- микрофоны ----
    property var micItems: []
    property int micIndex: -1

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

    Component.onCompleted: refreshMics()

    Connections {
        target: appState
        function onDevicesChanged() { page.refreshMics() }
    }

    Connections {
        target: liveEngine
        function onLevelChanged(v) { page.micLevel = v }
    }

    // ==================================================================
    // Раскладка
    // ==================================================================
    Column {
        anchors.fill: parent
        spacing: 14

        HeroBanner {
            width: parent.width
            height: 96
        }

        Row {
            width: parent.width
            height: parent.height - 96 - 14
            spacing: 14

            // ---------- левая колонка ----------
            Column {
                id: leftCol
                width: parent.width - 336 - 14
                height: parent.height
                spacing: 14

                // ============ живой перевод ============
                Card {
                    width: leftCol.width
                    height: parent.height - 240 - 14
                    padding: 18

                    Column {
                        anchors.fill: parent
                        spacing: 8

                        // заголовок
                        Item {
                            width: parent.width
                            height: 32

                            Row {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10

                                Icon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    source: "icons/wave.svg"
                                    color: Theme.accentCyan
                                    size: 18
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Живой перевод"
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 17
                                    font.weight: Theme.weightSemiBold
                                }
                                StatusPill {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: page.listening ? "Активно" : "Ожидание"
                                    pillState: page.listening ? "ready" : "idle"
                                    pillHeight: 22
                                }
                            }

                            Row {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 8

                                ModeSegment {
                                    anchors.verticalCenter: parent.verticalCenter
                                    compact: true
                                    value: appState.mode
                                }
                            }
                        }

                        // орб + статус
                        // высота считается из фактических строк: заголовок 32,
                        // волна 34, кнопки 44, громкости 34 и 4 отступа по 8
                        Item {
                            width: parent.width
                            height: Math.max(120, parent.height - 176)

                            MicOrb {
                                anchors.centerIn: parent
                                anchors.verticalCenterOffset: -14
                                width: Math.min(parent.height * 0.88, parent.width * 0.5, 320)
                                height: width
                                level: page.micLevel
                                active: page.listening || liveEngine.busy
                            }

                            Column {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom
                                spacing: 2

                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: page.listening ? "Слушаю…" : "Нажмите и говорите"
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 14
                                    font.weight: Theme.weightMedium
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: page.listening
                                          ? (liveEngine.peerPartial || "Говорите на любом поддерживаемом языке")
                                          : "Говорите на любом поддерживаемом языке"
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                }
                            }
                        }

                        WaveBars {
                            width: parent.width
                            height: 34
                            level: page.micLevel
                            active: page.listening || liveEngine.busy
                        }

                        // кнопки
                        Row {
                            width: parent.width
                            spacing: 10

                            Rectangle {
                                width: 180
                                height: 44
                                radius: Theme.radiusControl
                                gradient: Theme.gradAccent

                                Glow {
                                    anchors.fill: parent
                                    glowColor: Theme.accent
                                    intensity: page.listening ? 0.85 : 0.45
                                    cornerRadius: Theme.radiusControl
                                }

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 8
                                    Icon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: page.listening ? "icons/stop.svg" : "icons/mic.svg"
                                        color: "#FFFFFF"
                                        size: 16
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: page.listening ? "Остановить" : "Начать слушать"
                                        color: "#FFFFFF"
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 13
                                        font.weight: Theme.weightSemiBold
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

                            // PTT
                            Rectangle {
                                width: 170
                                height: 44
                                radius: Theme.radiusControl
                                color: pttArea.pressed ? Theme.surface3 : "#10163A"
                                border.width: 1
                                border.color: Theme.accent

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 8
                                    Icon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: "icons/keyboard.svg"
                                        color: Theme.accentBright
                                        size: 16
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: pttArea.pressed ? "Говорю…" : "Зажать и говорить"
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 13
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

                            Item { width: 1; height: 1 }

                            // выбор микрофона: ширина — остаток строки,
                            // иначе на 1280 кнопка уезжала за край карточки
                            AppCombo {
                                width: Math.max(140, parent.width - 381)
                                height: 44
                                anchors.verticalCenter: parent.verticalCenter
                                model: page.micItems
                                currentIndex: page.micIndex
                                currentText: page.micIndex >= 0 && page.micItems.length > 0
                                             ? page.micItems[page.micIndex].label : "микрофон не выбран"
                                onActivated: (i) => page.selectMic(i)
                            }
                        }

                        // громкость: что слышите вы и как слышат вас в кабеле
                        Row {
                            width: parent.width
                            spacing: 14

                            AppSlider {
                                width: (parent.width - 14) / 2
                                label: "В наушниках"
                                from: 0
                                to: 150
                                value: appState.incomingVolume
                                suffix: "%"
                                onMoved: (v) => appState.setIncomingVolume(Math.round(v))
                            }

                            AppSlider {
                                width: (parent.width - 14) / 2
                                label: "В кабеле (ваш голос)"
                                from: 0
                                to: 150
                                value: appState.voiceVolume
                                suffix: "%"
                                onMoved: (v) => appState.setVoiceVolume(Math.round(v))
                            }
                        }
                    }
                }

                // ============ нижний ряд ============
                Row {
                    width: leftCol.width
                    height: 240
                    spacing: 14

                    // последние переводы
                    Card {
                        width: parent.width - 296 - 14
                        height: parent.height
                        padding: 16

                        Column {
                            anchors.fill: parent
                            spacing: 8

                            Item {
                                width: parent.width
                                height: 26

                                Row {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 8
                                    Icon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: "icons/history.svg"
                                        color: Theme.accentCyan
                                        size: 17
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Последние переводы"
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 15
                                        font.weight: Theme.weightSemiBold
                                    }
                                }

                                Text {
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Вся история →"
                                    color: Theme.accentBright
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: page.navigate("history")
                                    }
                                }
                            }

                            Text {
                                text: "Пока нет переводов — нажмите «Начать слушать»."
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 12
                                visible: historyModel.count() === 0
                            }

                            ListView {
                                width: parent.width
                                height: parent.height - 40
                                clip: true
                                spacing: 2
                                model: historyModel

                                delegate: Item {
                                    id: row
                                    width: ListView.view.width
                                    height: 38

                                    required property string dir
                                    required property string ru
                                    required property string es
                                    required property string time

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 8
                                        color: hovered.containsMouse ? Theme.surface1 : "transparent"
                                    }

                                    Row {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        spacing: 10

                                        Rectangle {
                                            width: 6; height: 6; radius: 3
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: row.dir === "out" ? Theme.accent : Theme.success
                                        }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: row.time
                                            width: 52
                                            color: Theme.textMuted
                                            font.family: Theme.fontFamilyMono
                                            font.pixelSize: 10
                                        }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: row.dir === "out"
                                                  ? "RU → " + row.es : "ES → " + row.ru
                                            width: parent.width - 130
                                            elide: Text.ElideRight
                                            color: Theme.textPrimary
                                            font.family: Theme.fontFamilyText
                                            font.pixelSize: 12
                                        }
                                    }

                                    MouseArea {
                                        id: hovered
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.NoButton
                                        z: -1
                                    }
                                }
                            }
                        }
                    }

                    // быстрые действия
                    Card {
                        width: 296
                        height: parent.height
                        padding: 16

                        Column {
                            anchors.fill: parent
                            spacing: 8

                            Text {
                                text: "Быстрые действия"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }

                            Repeater {
                                model: [
                                    { "key": "models",   "label": "Модели",   "icon": "icons/layers.svg" },
                                    { "key": "voices",   "label": "Голос",    "icon": "icons/mic.svg" },
                                    { "key": "settings", "label": "Настройки", "icon": "icons/settings.svg" },
                                    { "key": "phrases",  "label": "Фразы",    "icon": "icons/bolt.svg" }
                                ]

                                delegate: Rectangle {
                                    width: parent.width
                                    height: Math.max(30, Math.min(38, (parent.height - 34) / 4 - 6))
                                    radius: Theme.radiusControl
                                    color: qa.containsMouse ? Theme.surface2 : "#10163A"
                                    border.width: 1
                                    border.color: Theme.border

                                    Row {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 12
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 10
                                        Icon {
                                            anchors.verticalCenter: parent.verticalCenter
                                            source: modelData.icon
                                            color: Theme.accentCyan
                                            size: 15
                                        }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData.label
                                            color: Theme.textSecondary
                                            font.family: Theme.fontFamilyText
                                            font.pixelSize: 12
                                        }
                                    }

                                    Icon {
                                        anchors.right: parent.right
                                        anchors.rightMargin: 12
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: "icons/chevron-right.svg"
                                        color: Theme.textMuted
                                        size: 12
                                    }

                                    MouseArea {
                                        id: qa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: page.navigate(modelData.key)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ---------- правая колонка ----------
            Column {
                width: 336
                height: parent.height
                spacing: 14

                // направление
                Card {
                    width: parent.width
                    height: 148
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: "Направление перевода"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 14
                            font.weight: Theme.weightSemiBold
                        }

                        Row {
                            width: parent.width
                            spacing: 8

                            AppCombo {
                                width: (parent.width - 44) / 2
                                model: page.peerLangItems
                                currentIndex: page.peerLangIndex
                                currentText: page.peerLangItems[page.peerLangIndex].label
                                onActivated: (i) => {
                                    page.peerLangIndex = i
                                    liveEngine.setPeerLang(page.peerLangItems[i].value)
                                }
                            }

                            Rectangle {
                                width: 36
                                height: 36
                                radius: 18
                                anchors.verticalCenter: parent.verticalCenter
                                color: swap.containsMouse ? Theme.surface2 : "#10163A"
                                border.width: 1
                                border.color: Theme.border
                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/compare.svg"
                                    color: Theme.accentCyan
                                    size: 15
                                }
                                MouseArea {
                                    id: swap
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: page.navigate("settings")
                                }
                            }

                            Rectangle {
                                width: (parent.width - 44) / 2
                                height: 36
                                radius: Theme.radiusControl
                                color: "#10163A"
                                border.width: 1
                                border.color: Theme.border
                                Text {
                                    anchors.centerIn: parent
                                    text: "🇷🇺  Русский"
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 12
                                }
                            }
                        }

                        Row {
                            width: parent.width
                            spacing: 8

                            // Это язык ПЕРЕВОДА моей речи (ru -> X), а не язык,
                            // на котором я говорю. Старая подпись «Мой язык»
                            // путала: выбрав здесь испанский, русскую речь
                            // всё равно распознавали как русскую.
                            Text {
                                text: "Перевод на:"
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            AppCombo {
                                width: Math.max(120, parent.width - 96)
                                model: page.langItems
                                currentIndex: page.langIndex
                                currentText: page.langItems[page.langIndex].label
                                onActivated: (i) => {
                                    page.langIndex = i
                                    liveEngine.setLang(page.langItems[i].value)
                                }
                            }
                        }
                    }
                }

                // режим
                Card {
                    width: parent.width
                    height: 196
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: "Режим качества"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 14
                            font.weight: Theme.weightSemiBold
                        }

                        ModeSegment {
                            width: parent.width
                            vertical: true
                            value: appState.mode
                        }

                        Text {
                            width: parent.width
                            text: appState.mode === "fast" ? "Минимальная задержка"
                                 : (appState.mode === "quality" ? "Максимальное качество"
                                    : (appState.mode === "manual" ? "Ручные параметры"
                                       : "Баланс скорости и качества"))
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                // модели
                Card {
                    width: parent.width
                    height: parent.height - 148 - 196 - 28
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 8

                        Item {
                            width: parent.width
                            height: 24

                            Text {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Модели"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 14
                                font.weight: Theme.weightSemiBold
                            }

                            Text {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Управление"
                                color: Theme.accentBright
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: page.navigate("models")
                                }
                            }
                        }

                        Repeater {
                            model: [
                                { "name": "ASR", "value": "faster-whisper turbo", "icon": "icons/wave.svg" },
                                { "name": "MT",  "value": "opus-mt",              "icon": "icons/translate.svg" },
                                { "name": "TTS", "value": "XTTS-v2",              "icon": "icons/volume.svg" }
                            ]

                            delegate: Row {
                                width: parent.width
                                height: 30
                                spacing: 10

                                Icon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    source: modelData.icon
                                    color: Theme.accentCyan
                                    size: 15
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.name
                                    width: 34
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyMono
                                    font.pixelSize: 11
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.value
                                    width: parent.width - 150
                                    elide: Text.ElideRight
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                }
                                Rectangle {
                                    width: 7; height: 7; radius: 3.5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: page.ready ? Theme.success : Theme.textMuted
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: page.ready ? "готово" : "нет"
                                    color: page.ready ? Theme.success : Theme.textMuted
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 10
                                }
                            }
                        }

                        Item { width: 1; height: 4 }

                        // запуск/остановка движка
                        Row {
                            width: parent.width
                            spacing: 8

                            Rectangle {
                                width: (parent.width - 8) / 2
                                height: 38
                                radius: Theme.radiusControl
                                gradient: page.ready ? null : Theme.gradAccent
                                color: page.ready ? "#10163A" : "transparent"
                                border.width: page.ready ? 1 : 0
                                border.color: Theme.border
                                opacity: page.ready ? 0.5 : 1

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Icon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: "icons/play.svg"
                                        color: page.ready ? Theme.textSecondary : "#FFFFFF"
                                        size: 13
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Запустить"
                                        color: page.ready ? Theme.textSecondary : "#FFFFFF"
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 11
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    enabled: !page.ready
                                    onClicked: appState.startEngine()
                                }
                            }

                            Rectangle {
                                width: (parent.width - 8) / 2
                                height: 38
                                radius: Theme.radiusControl
                                color: "#10163A"
                                border.width: 1
                                border.color: Theme.dangerDeep
                                opacity: page.ready ? 1 : 0.5

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Icon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        source: "icons/stop.svg"
                                        color: Theme.danger
                                        size: 13
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Остановить"
                                        color: Theme.textSecondary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 11
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    enabled: page.ready
                                    onClicked: appState.stopEngine()
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
