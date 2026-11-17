import QtQuick
import RedZ 1.0

/// Голос — по референсу: карточка с «микрофоном», настройки движка/профиля,
/// громкость и живость, горячие клавиши и запись образца.
Item {
    id: page

    property var profileItems: []
    property int profileIndex: 0
    property string newProfile: ""

    readonly property var engineItems: [
        { "label": "Русский (RUS) – XTTS", "value": "xtts" }
    ]

    readonly property bool hasRef: appState.hasReference()
    readonly property bool engineOk: appState.engineInstalled() === "да"

    function refreshProfiles() {
        var names = appState.profiles()
        var out = []
        for (var i = 0; i < names.length; i++) {
            out.push({ "label": names[i], "value": names[i] })
        }
        if (out.length === 0) {
            out.push({ "label": "по умолчанию", "value": "" })
        }
        page.profileItems = out
        var idx = 0
        for (var j = 0; j < out.length; j++) {
            if (out[j].value === appState.activeProfile) idx = j
        }
        page.profileIndex = idx
    }

    Component.onCompleted: refreshProfiles()

    Connections {
        target: appState
        function onProfilesChanged() { page.refreshProfiles() }
    }

    Column {
        anchors.fill: parent
        spacing: 16

        PageTitle {
            width: parent.width
            title: "Голос"
            subtitle: "Настройка голоса и аудио параметров"
            iconSource: "icons/mic.svg"
        }

        Row {
            width: parent.width
            height: 372
            spacing: 16

            // ---------------- живой голос: две орбы ----------------
            Card {
                width: parent.width - 336
                height: parent.height
                padding: 18

                Column {
                    anchors.fill: parent
                    spacing: 6

                    Item {
                        width: parent.width
                        height: 30

                        Row {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 10

                            Icon {
                                anchors.verticalCenter: parent.verticalCenter
                                source: "icons/mic.svg"
                                color: Theme.accentCyan
                                size: 17
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Живой голос"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }
                            StatusPill {
                                anchors.verticalCenter: parent.verticalCenter
                                text: page.hasRef ? "Голос готов" : "Нужен образец"
                                pillState: page.hasRef ? "ready" : "idle"
                                pillHeight: 22
                            }
                        }

                        Text {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: appState.activeProfile !== "" ? appState.activeProfile : "Профиль по умолчанию"
                            elide: Text.ElideRight
                            width: 200
                            horizontalAlignment: Text.AlignRight
                            color: Theme.accentBright
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                        }
                    }

                    Item {
                        width: parent.width
                        height: parent.height - 200

                        Row {
                            anchors.fill: parent
                            spacing: 6

                            Item {
                                width: (parent.width - 52) / 2
                                height: parent.height

                                MicOrb {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: Math.min(parent.width, parent.height - 40)
                                    height: width
                                    level: voiceController.recording ? 0.9 : 0.25
                                    active: voiceController.recording || liveEngine.busy
                                }

                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    text: voiceController.recording ? "Запись…" : "Говорите…"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                }
                            }

                            Icon {
                                anchors.verticalCenter: parent.verticalCenter
                                source: "icons/compare.svg"
                                color: Theme.accentBright
                                size: 22
                            }

                            Item {
                                width: (parent.width - 52) / 2
                                height: parent.height

                                MicOrb {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: Math.min(parent.width, parent.height - 40)
                                    height: width
                                    level: liveEngine.busy ? 0.8 : 0.2
                                    active: liveEngine.busy
                                    iconSource: "icons/volume.svg"
                                    ringColor: Theme.accentCyan
                                    ringColor2: Theme.accentBlue
                                }

                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    text: liveEngine.busy ? "Перевод звучит…" : "Перевод прозвучит здесь"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }

                    WaveBars {
                        width: parent.width
                        height: 40
                        level: voiceController.recording ? 0.9 : 0.3
                        active: voiceController.recording || liveEngine.busy
                    }

                    Row {
                        width: parent.width
                        spacing: 8

                        AppButton {
                            width: (parent.width - 16) / 2
                            text: voiceController.selectedCount > 0
                                  ? "Собрать из выбранных (" + voiceController.selectedCount + ")"
                                  : "Собрать из всех записей"
                            iconSource: "icons/sparkles.svg"
                            baseColor: Theme.accent
                            onClicked: voiceController.buildReference()
                        }

                        AppButton {
                            width: (parent.width - 16) / 2
                            text: "Прослушать образец"
                            iconSource: "icons/play.svg"
                            flat: true
                            onClicked: voiceController.playSample(appState.referencePath())
                        }
                    }

                    // профиль и параметры голоса
                    Row {
                        width: parent.width
                        spacing: 10

                        AppCombo {
                            width: 180
                            anchors.verticalCenter: parent.verticalCenter
                            model: page.profileItems
                            currentIndex: page.profileIndex
                            currentText: page.profileIndex >= 0 && page.profileItems.length > 0
                                         ? page.profileItems[page.profileIndex].label : "—"
                            onActivated: (i) => {
                                page.profileIndex = i
                                if (page.profileItems[i].value !== "") {
                                    appState.setProfile(page.profileItems[i].value)
                                }
                            }
                        }

                        AppSlider {
                            width: (parent.width - 200) / 2
                            anchors.verticalCenter: parent.verticalCenter
                            label: "Громкость"
                            from: 0
                            to: 150
                            value: appState.voiceVolume
                            suffix: "%"
                            onMoved: (v) => appState.setVoiceVolume(Math.round(v))
                        }

                        AppSlider {
                            width: (parent.width - 200) / 2
                            anchors.verticalCenter: parent.verticalCenter
                            label: "Живость"
                            from: 0
                            to: 3
                            value: appState.liveliness
                            onMoved: (v) => {
                                appState.setLiveliness(Math.round(v))
                                liveEngine.setLiveliness(Math.round(v))
                            }
                        }
                    }
                }
            }

            // ---------------- справа: режим и статистика ----------------
            Column {
                width: 336
                height: parent.height
                spacing: 14

                Card {
                    width: parent.width
                    height: 200
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: "Режим работы"
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
                        }
                    }
                }

                Card {
                    width: parent.width
                    height: parent.height - 214
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 8

                        Text {
                            text: "Статистика"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 14
                            font.weight: Theme.weightSemiBold
                        }

                        Repeater {
                            model: [
                                { "label": "Распознавание", "key": "asr_ms" },
                                { "label": "Перевод", "key": "mt_ms" },
                                { "label": "Синтез", "key": "tts_ms" }
                            ]

                            delegate: Row {
                                width: parent.width
                                height: 22
                                spacing: 8

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.label
                                    width: parent.width - 70
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 62
                                    horizontalAlignment: Text.AlignRight
                                    text: (liveEngine.lastMetrics
                                           && liveEngine.lastMetrics[modelData.key] !== undefined)
                                          ? liveEngine.lastMetrics[modelData.key] + " мс" : "—"
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyMono
                                    font.pixelSize: 11
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: Theme.border
                        }

                        Row {
                            width: parent.width
                            height: 20

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "VRAM"
                                width: parent.width - 70
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 62
                                horizontalAlignment: Text.AlignRight
                                text: appState.vramTotal > 0
                                      ? (appState.vramUsed / 1024).toFixed(1)
                                        + " / " + Math.round(appState.vramTotal / 1024) + " GB"
                                      : "—"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 11
                            }
                        }

                        StatSpark {
                            width: parent.width
                            height: Math.max(0, parent.height - 158)
                            visible: height > 20
                        }

                        Text {
                            width: parent.width
                            text: voiceController.progressText + " подсказок записано"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 11
                            visible: parent.height > 210
                        }
                    }
                }
            }
        }

        // ---------------- запись образца ----------------
        Card {
            width: parent.width
            height: parent.height - 372 - 92 - 48
            padding: 20

            Column {
                anchors.fill: parent
                spacing: 10

                Row {
                    width: parent.width
                    spacing: 10

                    Icon {
                        source: "icons/record.svg"
                        color: Theme.danger
                        size: 18
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "Запись образца"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 17
                        font.weight: Theme.weightSemiBold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    StatusPill {
                        text: voiceController.takeStatus
                        pillState: voiceController.recording ? "loading"
                                 : (voiceController.takeOk ? "ready" : "idle")
                        pillHeight: 22
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Item { width: 1; height: 1 }

                    Text {
                        text: voiceController.progressText
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: 12
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Row {
                    width: parent.width
                    height: 62
                    spacing: 12

                    Rectangle {
                        width: 56
                        height: parent.height
                        radius: 10
                        color: prevHover.hovered ? Theme.surface2 : Theme.surface1
                        border.color: Theme.border
                        border.width: 1
                        Icon {
                            anchors.centerIn: parent
                            source: "icons/chevron-right.svg"
                            color: Theme.textSecondary
                            size: 18
                            rotation: 180
                        }
                        MouseArea {
                            id: prevHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: voiceController.prevPrompt()
                        }
                    }

                    Column {
                        width: parent.width - 350
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        Text {
                            text: voiceController.currentPromptRu()
                            width: parent.width
                            elide: Text.ElideRight
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 15
                            font.weight: Theme.weightMedium
                        }
                        Text {
                            text: voiceController.currentPromptText()
                            width: parent.width
                            elide: Text.ElideRight
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                        }
                    }

                    Rectangle {
                        width: 56
                        height: parent.height
                        radius: 10
                        color: nextHover.hovered ? Theme.surface2 : Theme.surface1
                        border.color: Theme.border
                        border.width: 1
                        Icon {
                            anchors.centerIn: parent
                            source: "icons/chevron-right.svg"
                            color: Theme.textSecondary
                            size: 18
                        }
                        MouseArea {
                            id: nextHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: voiceController.nextPrompt()
                        }
                    }

                    AppButton {
                        width: 190
                        controlHeight: 56
                        text: voiceController.recording ? "Остановить" : "Записать"
                        iconSource: voiceController.recording ? "icons/stop.svg" : "icons/record.svg"
                        baseColor: voiceController.recording ? Theme.danger : Theme.accent
                        onClicked: voiceController.toggleRecording()
                    }
                }

                // Инструменты над списком: отметить записи, собрать из них
                // образец и сохранить результат отдельным профилем (клоном).
                // Две строки — на 1280 px фиксированные ширины в один ряд не лезли
                // и кнопка «Создать профиль» обрезалась.
                Column {
                    width: parent.width
                    spacing: 8

                    Row {
                        width: parent.width
                        spacing: 8

                        AppButton {
                            width: 130
                            controlHeight: 30
                            text: "Выбрать все"
                            flat: true
                            onClicked: voiceController.selectAllSamples()
                        }
                        AppButton {
                            width: 130
                            controlHeight: 30
                            text: "Снять выбор"
                            flat: true
                            onClicked: voiceController.clearSelection()
                        }
                        AppButton {
                            width: Math.max(210, parent.width - 276)
                            controlHeight: 30
                            text: voiceController.selectedCount > 0
                                  ? "Собрать из отмеченных (" + voiceController.selectedCount + ")"
                                  : "Собрать из всех"
                            onClicked: voiceController.buildReference()
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 8

                        AppField {
                            width: parent.width - 188
                            fieldHeight: 30
                            placeholderText: "имя нового профиля"
                            onTextEdited: (t) => page.newProfile = t
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppButton {
                            width: 180
                            controlHeight: 30
                            text: "Создать профиль"
                            iconSource: "icons/star.svg"
                            flat: true
                            onClicked: voiceController.saveProfile(page.newProfile)
                        }
                    }
                }

                ListView {
                    width: parent.width
                    height: parent.height - 150
                    clip: true
                    spacing: 2
                    model: voiceController.takeModel

                    delegate: Item {
                        id: takeRow
                        width: ListView.view.width
                        height: 34

                        readonly property bool picked: !!modelData.selected

                        Rectangle {
                            anchors.fill: parent
                            radius: 7
                            color: takeRow.picked ? "#20180E" : "transparent"
                        }

                        // клик по строке — выбрать подсказку (текст справа)
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: voiceController.selectPrompt(modelData.index)
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 6
                            anchors.rightMargin: 6
                            spacing: 8

                            // галочка: взять запись в образец
                            Rectangle {
                                width: 18
                                height: 18
                                radius: 5
                                anchors.verticalCenter: parent.verticalCenter
                                color: takeRow.picked ? Theme.accent : Theme.surface1
                                border.color: takeRow.picked ? Theme.accent : Theme.border
                                border.width: 1

                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/check.svg"
                                    size: 12
                                    color: "#1A1206"
                                    visible: takeRow.picked
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: modelData.ok
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: voiceController.toggleSample(
                                        modelData.ok ? modelData.path : "")
                                }
                            }

                            Text {
                                text: ("0" + (modelData.index + 1)).slice(-2)
                                width: 24
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 11
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: modelData.text
                                width: parent.width - 175
                                elide: Text.ElideRight
                                color: modelData.ok ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: modelData.ok ? modelData.duration.toFixed(1) + " в" : "—"
                                width: 46
                                horizontalAlignment: Text.AlignRight
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 11
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Item {
                                width: 26
                                height: 26
                                anchors.verticalCenter: parent.verticalCenter
                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/play.svg"
                                    size: 14
                                    color: modelData.ok ? Theme.accent : Theme.surface3
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: modelData.ok
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: voiceController.playSampleAt(modelData.index)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
