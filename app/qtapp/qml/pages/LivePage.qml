import QtQuick
import RedZ 1.0

/// Страница «Перевод»: живой перевод в обе стороны.
///
/// Исходящее: русская речь (PTT / непрерывно) -> язык вывода -> кабель.
/// Входящее: речь собеседника (loopback) -> русский -> наушники.
Item {
    id: page
    anchors.fill: parent

    property real micLevel: 0.0
    property real micPeak: 0.0
    property string activeControl: ""   // "live" | ""

    readonly property var inputLangItems: [
        { "label": "Русский - ru_RU", "value": "ru" }
    ]
    readonly property var outputLangItems: appState.targetLangItems

    function targetIndex() {
        var items = appState.targetLangItems
        for (var i = 0; i < items.length; i++)
            if (items[i].value === appState.targetLang) return i
        return 0
    }

    readonly property var srcItems: {
        var out = []
        var m = liveEngine.srcModels
        for (var i = 0; i < m.length; i++)
            out.push({ "label": m[i].label, "value": m[i].code })
        if (out.length === 0)
            out.push({ "label": "Русский", "value": "ru" })
        return out
    }

    function srcIndex() {
        var items = page.srcItems
        for (var i = 0; i < items.length; i++)
            if (items[i].value === appState.srcLang) return i
        return 0
    }

    function peerIndex() {
        var items = appState.peerLangItems
        for (var i = 0; i < items.length; i++)
            if (items[i].value === appState.peerLang) return i
        return 0
    }

    Column {
        anchors.fill: parent
        spacing: 16

        // ====================== профиль перевода ======================
        Card {
            width: parent.width
            height: 196
            padding: 18

            Column {
                anchors.fill: parent
                spacing: 12

                Row {
                    width: parent.width
                    spacing: 10

                    Text {
                        text: "ЖИВОЙ ПЕРЕВОД"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: Theme.fontBodyPx
                        font.weight: Theme.weightSemiBold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "русский → выбранный язык"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: Theme.fontTinyPx
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Item { width: 1; height: 1 }

                    AppSwitch {
                        label: "Исходящий"
                        checked: appState.outgoingOn
                        onToggled: (on) => appState.setOutgoing(on)
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    StatusPill {
                        text: appState.engineStatusText()
                        state: {
                            var s = appState.engineState
                            if (s === "READY") return "ready"
                            if (s === "LOADING") return "loading"
                            if (s === "ERROR") return "error"
                            return "idle"
                        }
                        pillHeight: 24
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    AppButton {
                        controlHeight: 34
                        text: appState.engineState === "READY" ? "Остановить движок"
                                                              : "Запустить движок"
                        iconSource: appState.engineState === "READY"
                                    ? "icons/stop.svg" : "icons/play.svg"
                        flat: true
                        onClicked: {
                            if (appState.engineState === "READY") appState.stopEngine()
                            else appState.startEngine()
                        }
                    }
                }

                Row {
                    width: parent.width
                    spacing: 16

                    LangCombo {
                        label: "ЯЗЫК ПОЛЬЗОВАТЕЛЯ"
                        width: 220
                        items: page.srcItems
                        currentLabel: page.srcItems[page.srcIndex()].label
                        currentIndex: page.srcIndex()
                        onChanged: (i) => appState.setSrcLang(
                            page.srcItems[i].value)
                    }

                    LangCombo {
                        label: "ЯЗЫК ВЫВОДА"
                        width: 240
                        items: page.outputLangItems
                        currentLabel: appState.targetLangItems[page.targetIndex()].label
                        currentIndex: page.targetIndex()
                        onChanged: (i) => appState.setTargetLang(
                            page.outputLangItems[i].value)
                    }

                    Item { width: 1; height: 1 }
                }

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
                        text: "УРОВЕНЬ МИКРОФОНА"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: Theme.fontTinyPx
                        font.weight: Theme.weightBold
                        font.letterSpacing: 1.0
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    WaveformVisualizer {
                        width: parent.width - 190
                        height: 44
                        level: page.micLevel
                        active: liveEngine.state === "READY"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

            }
        }

        // ====================== основная область ======================
        Row {
            width: parent.width
            height: parent.height - 196 - 16
            spacing: 16

            // ----- слева: PTT и история -----
            Card {
                width: parent.width * 0.62
                height: parent.height
                padding: 18

                Column {
                    anchors.fill: parent
                    spacing: 12

                    Rectangle {
                        id: pttBtn
                        width: parent.width
                        height: 80
                        radius: Theme.radiusInner
                        color: pttArea.pressed ? Theme.outgoingDeep : Theme.surface1
                        border.color: pttArea.pressed ? Theme.outgoing : Theme.borderStrong
                        border.width: 1.5
                        Behavior on color { ColorAnimation { duration: 80 } }

                        Column {
                            anchors.centerIn: parent
                            spacing: 2
                            Text {
                                text: page.activeControl === "live" ? "ГОВОРИТЬ…"
                                                                    : "ЗАЖМИ И ГОВОРИ"
                                color: pttArea.pressed ? Theme.textOnAccent : Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: Theme.fontBodyPx
                                font.weight: Theme.weightBold
                                anchors.horizontalCenter: parent.horizontalCenter
                            }
                            Text {
                                text: page.activeControl === "live" ? "отпусти, чтобы отправить"
                                                                    : "Push-to-Talk"
                                color: pttArea.pressed ? Theme.accentInk : Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: Theme.fontTinyPx
                                anchors.horizontalCenter: parent.horizontalCenter
                            }
                        }

                        MouseArea {
                            id: pttArea
                            anchors.fill: parent
                            onPressed: {
                                page.activeControl = "live"
                                liveEngine.pressToTalk()
                            }
                            onReleased: {
                                page.activeControl = ""
                                liveEngine.releaseToTalk()
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "НЕПРЕРЫВНЫЙ"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            font.weight: Theme.weightBold
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppSwitch {
                            checked: false
                            onToggled: (on) => liveEngine.setContinuous(on)
                        }
                        Item { width: 1; height: 1 }
                        StatusPill {
                            text: liveEngine.busy ? "перевожу…" : "готов"
                            state: liveEngine.busy ? "loading" : "idle"
                            pillHeight: 22
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // последняя реплика: оригинал и перевод в обе стороны
                    Column {
                        width: parent.width
                        spacing: 2

                        Text {
                            text: "ПОСЛЕДНЯЯ РЕПЛИКА"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            font.weight: Theme.weightBold
                            font.letterSpacing: 1.0
                        }
                        Text {
                            width: parent.width
                            text: liveEngine.lastOutOriginal
                                  ? "Вы: " + liveEngine.lastOutOriginal : "Вы: —"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            visible: liveEngine.lastOutTranslation !== ""
                            text: "→ " + liveEngine.lastOutTranslation
                            color: Theme.outgoing
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            visible: liveEngine.lastInOriginal !== ""
                            text: "Собеседник: " + liveEngine.lastInOriginal
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            visible: liveEngine.lastInTranslation !== ""
                            text: "→ " + liveEngine.lastInTranslation
                            color: Theme.incoming
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        text: "ПОСЛЕДНИЕ ПЕРЕВОДЫ"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: Theme.fontTinyPx
                        font.weight: Theme.weightBold
                        font.letterSpacing: 1.0
                    }

                    ListView {
                        id: recentList
                        width: parent.width
                        height: parent.height - 300
                        clip: true
                        model: historyModel
                        delegate: Item {
                            width: ListView.view.width
                            height: 30
                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: Theme.spaceSM
                                anchors.rightMargin: Theme.spaceSM
                                spacing: Theme.spaceSM
                                Rectangle {
                                    width: 3; height: 18; radius: 1
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: model.dir === "out" ? Theme.outgoing : Theme.incoming
                                }
                                Text {
                                    text: model.dir === "out"
                                          ? model.ru + " → " + model.es
                                          : model.es + " → " + model.ru
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: Theme.fontTinyPx
                                    elide: Text.ElideRight
                                    width: parent.width - 10
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    }
                }
            }

            // ----- справа: уровень и входящий перевод -----
            Column {
                width: parent.width * 0.38 - 16
                height: parent.height
                spacing: 16

                Card {
                    width: parent.width
                    height: 130
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 8

                        Text {
                            text: "УРОВЕНЬ"
                            color: Theme.accent
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            font.weight: Theme.weightBold
                            font.letterSpacing: 1.2
                        }
                        LevelMeter {
                            level: page.micLevel
                            peak: page.micPeak
                            label: "Микрофон"
                            width: parent.width
                        }
                    }
                }

                Card {
                    width: parent.width
                    height: parent.height - 130 - 16
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: "ВХОДЯЩИЙ ПЕРЕВОД"
                            color: Theme.accent
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                            font.weight: Theme.weightBold
                            font.letterSpacing: 1.2
                        }
                        Text {
                            text: "Речь собеседника → русский → наушники"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                        }

                        AppSwitch {
                            label: "Переводить речь собеседника"
                            checked: appState.incomingOn
                            onToggled: (on) => appState.setIncoming(on)
                        }

                        AppCombo {
                            label: "Язык собеседника"
                            width: parent.width
                            model: appState.peerLangItems
                            currentIndex: page.peerIndex()
                            currentText: appState.peerLangItems[page.peerIndex()].label
                            onActivated: (i) => appState.setPeerLang(
                                appState.peerLangItems[i].value)
                        }

                        AppSlider {
                            label: "Громкость в наушниках"
                            width: parent.width
                            from: 0; to: 150
                            value: appState.incomingVolume
                            decimals: 0; suffix: "%"
                            onMoved: (v) => appState.setIncomingVolume(Math.round(v))
                        }

                        StatusPill {
                            text: liveEngine.incomingActive
                                  ? "озвучиваю"
                                  : (liveEngine.captureOn ? "слушаю игру" : "выключено")
                            state: liveEngine.incomingActive ? "ready"
                                   : (liveEngine.captureOn ? "loading" : "idle")
                            pillHeight: 22
                        }

                        Text {
                            text: liveEngine.mtSummary()
                            width: parent.width
                            wrapMode: Text.WordWrap
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontTinyPx
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: liveEngine
        function onLevelChanged(v) { page.micLevel = v }
        function onPeerLevelChanged(v) { page.micPeak = v }
    }
}
