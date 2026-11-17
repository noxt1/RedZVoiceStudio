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

            // ---------------- «микрофон» ----------------
            Card {
                width: 300
                height: parent.height
                padding: 22
                topColor: "#231A0F"
                bottomColor: "#120F0A"
                borderColor: Theme.accentDeep

                Column {
                    anchors.fill: parent
                    spacing: 8

                    Item { width: 1; height: 2 }

                    Item {
                        width: 132
                        height: 132
                        anchors.horizontalCenter: parent.horizontalCenter

                        Glow {
                            anchors.fill: parent
                            glowColor: Theme.accent
                            intensity: 0.5
                            spread: 18
                            cornerRadius: 66
                        }
                        Rectangle {
                            anchors.fill: parent
                            radius: width / 2
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: "#2A2013" }
                                GradientStop { position: 1.0; color: "#150F08" }
                            }
                            border.color: Theme.accentDeep
                            border.width: 1.5
                        }
                        Icon {
                            anchors.centerIn: parent
                            source: "icons/mic.svg"
                            color: Theme.accent
                            size: 56
                        }
                    }

                    Text {
                        text: appState.activeProfile !== "" ? appState.activeProfile : "Профиль по умолчанию"
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        color: Theme.accentBright
                        font.family: Theme.fontFamilyBrand
                        font.pixelSize: 22
                        font.weight: Theme.weightBold
                    }

                    StatusPill {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: page.hasRef ? "Голос готов" : "Нужен образец"
                        pillState: page.hasRef ? "ready" : "idle"
                    }

                    Text {
                        text: voiceController.progressText + " подсказок записано"
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        color: Theme.textSecondary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                    }

                    Item { width: 1; height: 1 }

                    AppButton {
                        width: parent.width
                        text: voiceController.selectedCount > 0
                              ? "Собрать из выбранных (" + voiceController.selectedCount + ")"
                              : "Собрать из всех записей"
                        iconSource: "icons/sparkles.svg"
                        baseColor: Theme.accent
                        onClicked: voiceController.buildReference()
                    }

                    AppButton {
                        width: parent.width
                        text: "Прослушать образец"
                        iconSource: "icons/play.svg"
                        flat: true
                        onClicked: voiceController.playSample(appState.referencePath())
                    }
                }
            }

            // ---------------- настройки голоса ----------------
            Card {
                width: parent.width - 316
                height: parent.height
                padding: 22

                Column {
                    anchors.fill: parent
                    spacing: 14

                    // движок
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/bolt.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Голосовой движок"
                            width: 168
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        // Движок выбирается автоматически (XTTS для клона,
                        // Piper для языков, которых в XTTS нет) — ручной
                        // выбор здесь ни на что не влиял.
                        Text {
                            text: "выбирается автоматически"
                            width: parent.width - 340
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        StatusPill {
                            text: page.engineOk ? "установлен" : "нет"
                            pillState: page.engineOk ? "ready" : "warn"
                            pillHeight: 22
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // профиль
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/mic.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Голосовой профиль"
                            width: 168
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 210
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
                    }

                    // громкость
                    AppSlider {
                        width: parent.width
                        label: "Громкость голоса"
                        from: 0
                        to: 150
                        value: appState.voiceVolume
                        suffix: "%"
                        onMoved: (v) => appState.setVoiceVolume(Math.round(v))
                    }

                    // живость
                    AppSlider {
                        width: parent.width
                        label: "Живость интонации"
                        from: 0
                        to: 3
                        value: appState.liveliness
                        onMoved: (v) => {
                            appState.setLiveliness(Math.round(v))
                            liveEngine.setLiveliness(Math.round(v))
                        }
                    }

                    Rectangle {
                        width: parent.width
                        height: 1
                        color: Theme.border
                    }

                    // Горячие клавиши и выбор движка — в «Настройках».
                    Row {
                        width: parent.width
                        spacing: 10

                        AppButton {
                            width: parent.width
                            text: "Сравнить с образцом"
                            iconSource: "icons/compare.svg"
                            flat: true
                            onClicked: voiceController.compare("delay", 1.2)
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
                        width: 210
                        controlHeight: 30
                        text: voiceController.selectedCount > 0
                              ? "Собрать из отмеченных (" + voiceController.selectedCount + ")"
                              : "Собрать из всех"
                        onClicked: voiceController.buildReference()
                    }
                    Item { width: 1; height: 1 }
                    AppField {
                        width: 170
                        fieldHeight: 30
                        placeholderText: "имя нового профиля"
                        onTextEdited: (t) => page.newProfile = t
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    AppButton {
                        width: 160
                        controlHeight: 30
                        text: "Создать профиль"
                        iconSource: "icons/star.svg"
                        flat: true
                        onClicked: voiceController.saveProfile(page.newProfile)
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
