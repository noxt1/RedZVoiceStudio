import QtQuick
import RedZ 1.0

/// Голос — по референсу: карточка с «микрофоном», настройки движка/профиля,
/// громкость и живость, горячие клавиши и запись образца.
Item {
    id: page

    property var profileItems: []
    property int profileIndex: 0

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
                        text: "Собрать reference"
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

                ListView {
                    width: parent.width
                    height: parent.height - 106
                    clip: true
                    spacing: 2
                    model: voiceController.takeModel

                    delegate: Item {
                        width: ListView.view.width
                        height: 34

                        Row {
                            anchors.fill: parent
                            spacing: 10

                            Rectangle {
                                width: 8
                                height: 8
                                radius: 4
                                color: modelData.ok ? Theme.success : Theme.surface3
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: ("0" + (modelData.index + 1)).slice(-2)
                                width: 26
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 11
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: modelData.text
                                width: parent.width - 80
                                elide: Text.ElideRight
                                color: modelData.ok ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: voiceController.selectPrompt(modelData.index)
                        }
                    }
                }
            }
        }
    }
}
