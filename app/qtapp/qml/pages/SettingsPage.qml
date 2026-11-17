import QtQuick
import RedZ 1.0

/// Настройки — по референсу: общие переключатели и устройства/маршрут.
Item {
    id: page

    property string hkDraft: appState.hotkeyCombo

    property var micItems: []
    property int micIndex: -1
    property var outItems: []
    property int outIndex: -1

    readonly property var uiLangItems: [{ "label": "Русский", "value": "ru" }]
    readonly property var bankLangItems: [
        { "label": "Испанский (es)", "value": "es" },
        { "label": "Английский (en)", "value": "en" },
        { "label": "Old West (ow)", "value": "ow" },
        { "label": "Итальянский (it)", "value": "it" }
    ]
    readonly property var screenItems: [
        { "label": "Полный экран", "value": "full" },
        { "label": "Окно", "value": "window" }
    ]
    readonly property var modeItems: [
        { "label": "Fast — минимальная задержка", "value": "fast" },
        { "label": "Balanced — баланс (по умолчанию)", "value": "balanced" },
        { "label": "Quality — максимум качества", "value": "quality" },
        { "label": "Manual — ручной выбор моделей", "value": "manual" }
    ]

    function modeIndex() {
        for (var i = 0; i < modeItems.length; i++)
            if (modeItems[i].value === appState.mode) return i
        return 1
    }

    function bankIndex() {
        for (var i = 0; i < bankLangItems.length; i++) {
            if (bankLangItems[i].value === appState.bankLang) return i
        }
        return 0
    }

    function asrIndex() {
        var items = liveEngine.asrModels
        var want = appState.asrModel
        for (var i = 0; i < items.length; i++)
            if (want && items[i].name === want) return i
        for (var j = 0; j < items.length; j++)
            if (items[j].active) return j
        return 0
    }

    function refreshDevices() {
        var ins = appState.inputDevices
        var outs = appState.outputDevices
        var mi = []
        for (var i = 0; i < ins.length; i++) mi.push({ "label": ins[i].name, "value": ins[i].id })
        var mo = []
        for (var j = 0; j < outs.length; j++) mo.push({ "label": outs[j].name, "value": outs[j].id })
        page.micItems = mi
        page.outItems = mo

        var idx = -1
        for (var k = 0; k < mi.length; k++) if (mi[k].value === appState.inDevice) idx = k
        page.micIndex = idx
        var odx = -1
        for (var n = 0; n < mo.length; n++) if (mo[n].value === appState.outDevice) odx = n
        page.outIndex = odx
    }

    Component.onCompleted: refreshDevices()

    Connections {
        target: appState
        function onDevicesChanged() { page.refreshDevices() }
        function onSettingsChanged() { }
    }

    Column {
        anchors.fill: parent
        spacing: 16

        PageTitle {
            width: parent.width
            title: "Настройки"
            subtitle: "Общие настройки приложения"
            iconSource: "icons/settings.svg"
        }

        Row {
            width: parent.width
            height: parent.height - 92 - 16
            spacing: 16

            // ---------------- общие ----------------
            Card {
                width: parent.width - 396
                height: parent.height
                padding: 22

                Column {
                    anchors.fill: parent
                    spacing: 12

                    // язык интерфейса
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/layers.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Язык интерфейса"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 226
                            model: page.uiLangItems
                            currentIndex: 0
                            currentText: page.uiLangItems[0].label
                        }
                    }

                    // язык банка фраз
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/translate.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Язык банка фраз"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 226
                            model: page.bankLangItems
                            currentIndex: page.bankIndex()
                            currentText: page.bankLangItems[page.bankIndex()].label
                            onActivated: (i) => appState.setBankLang(page.bankLangItems[i].value)
                        }
                    }

                    // режим экрана
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/folder.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Режим экрана"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 226
                            model: page.screenItems
                            currentIndex: appState.fullscreen ? 0 : 1
                            currentText: appState.fullscreen ? "Полный экран" : "Окно"
                            onActivated: (i) => appState.setFullscreen(i === 0)
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // переключатели
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/info.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Показывать подсказки"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppSwitch {
                            checked: appState.hintsOn
                            onToggled: (on) => appState.setHints(on)
                        }
                    }

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
                            text: "Автозагрузка моделей"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppSwitch {
                            checked: appState.autoStartEngine
                            onToggled: (on) => appState.setAutoStartEngine(on)
                        }
                    }

                    // автоскачивание языковых пакетов (по умолчанию выкл.)
                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/folder.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Автоскачивание пакетов"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppSwitch {
                            checked: appState.autoDownload
                            onToggled: (on) => appState.setAutoDownload(on)
                        }
                        Text {
                            text: "может скачивать модели из интернета"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/plug.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Мост микрофон → кабель"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppSwitch {
                            checked: appState.bridgeOn
                            onToggled: (on) => appState.toggleBridge()
                        }
                        StatusPill {
                            text: appState.bridgeOn ? "работает" : "выключен"
                            pillState: appState.bridgeOn ? "ready" : "idle"
                            pillHeight: 22
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Item { width: 1; height: 1 }

                    // горячие клавиши
                    Row {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "Горячие клавиши"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        // Любая комбинация: alt+capslock, ctrl+alt+l, f9…
                        AppField {
                            width: 190
                            fieldHeight: 34
                            text: page.hkDraft
                            placeholderText: "alt+capslock"
                            onTextEdited: (t) => page.hkDraft = t
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        AppButton {
                            width: 120
                            controlHeight: 34
                            text: "Применить"
                            flat: true
                            onClicked: appState.setHotkey(page.hkDraft)
                        }

                        Text {
                            text: "непрерывный режим · " + appState.hotkeyPretty()
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Item { width: 1; height: 1 }

                        AppButton {
                            width: 170
                            controlHeight: 34
                            text: appState.hotkeysOn ? "Выключить" : "Включить"
                            flat: true
                            onClicked: appState.toggleHotkeys()
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // ---- режим работы: реальные параметры движка ----
                    Row {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "Режим работы"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 226
                            model: page.modeItems
                            currentIndex: page.modeIndex()
                            currentText: page.modeItems[page.modeIndex()].label
                            onActivated: (i) => appState.setMode(
                                page.modeItems[i].value)
                        }
                    }

                    Text {
                        width: parent.width
                        visible: liveEngine.modeInfo !== ""
                        text: liveEngine.modeInfo
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // ---- модели: только те, что реально установлены ----
                    Row {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "Распознавание"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 226
                            model: liveEngine.asrModels
                            currentIndex: liveEngine.asrModels.length > 0 ? page.asrIndex() : -1
                            currentText: liveEngine.asrModels.length > 0
                                         ? liveEngine.asrModels[page.asrIndex()].label
                                         : "движок не запущен"
                            // ручной выбор имеет смысл только в режиме Manual
                            enabled: appState.mode === "manual"
                                      && liveEngine.asrModels.length > 1
                            opacity: enabled ? 1.0 : 0.7
                            onActivated: (i) => appState.setAsrModel(
                                liveEngine.asrModels[i].name)
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 10

                        Text {
                            text: "Озвучка (TTS)"
                            width: 196
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: liveEngine.ttsModel || "—"
                            width: parent.width - 226
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyMono
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Text {
                        text: "Перевод: " + liveEngine.mtSummary()
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 11
                    }

                    Row {
                        width: parent.width
                        spacing: 10
                        Text {
                            text: "В списке только установленные модели"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Item { width: 1; height: 1 }
                        AppButton {
                            width: 170
                            controlHeight: 32
                            text: "Обновить список"
                            flat: true
                            onClicked: liveEngine.requestModels()
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // ---- диагностика: метрики последней реплики ----
                    Text {
                        text: "ДИАГНОСТИКА"
                        color: Theme.accent
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 10
                        font.weight: Theme.weightBold
                        font.letterSpacing: 1.4
                    }
                    Text {
                        width: parent.width
                        text: liveEngine.lastMetrics["total_ms"] !== undefined
                              ? ("ASR " + liveEngine.lastMetrics["asr_ms"] + " мс · перевод "
                                 + liveEngine.lastMetrics["mt_ms"] + " мс · до первого звука "
                                 + liveEngine.lastMetrics["total_ms"] + " мс · очередь "
                                 + liveEngine.lastMetrics["queue"])
                              : (liveEngine.lastMetrics["tts_first_ms"] !== undefined
                                 ? ("первый аудиочанк " + liveEngine.lastMetrics["tts_first_ms"] + " мс")
                                 : "нет данных — скажи фразу в игре")
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: "отброшено: " + liveEngine.lastMetrics["dropped"]
                              + " · отменено: " + liveEngine.lastMetrics["cancelled"]
                              + " · подробности: logs/diagnostics.log"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // ---------------- устройства и маршрут ----------------
            Card {
                width: 380
                height: parent.height
                padding: 22

                Column {
                    anchors.fill: parent
                    spacing: 12

                    Text {
                        text: "УСТРОЙСТВА"
                        color: Theme.accent
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 10
                        font.weight: Theme.weightBold
                        font.letterSpacing: 1.4
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
                            text: "Микрофон"
                            width: 96
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 126
                            model: page.micItems
                            currentIndex: page.micIndex
                            currentText: page.micIndex >= 0 && page.micItems.length > 0
                                         ? page.micItems[page.micIndex].label : "нет устройств"
                            onActivated: (i) => {
                                page.micIndex = i
                                appState.setInDevice(page.micItems[i].value)
                                liveEngine.setMicDevice(page.micItems[i].value)
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 10

                        Icon {
                            source: "icons/volume.svg"
                            color: Theme.textMuted
                            size: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "Выход"
                            width: 96
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        AppCombo {
                            width: parent.width - 126
                            model: page.outItems
                            currentIndex: page.outIndex
                            currentText: page.outIndex >= 0 && page.outItems.length > 0
                                         ? page.outItems[page.outIndex].label : "нет устройств"
                            onActivated: (i) => {
                                page.outIndex = i
                                appState.setOutDevice(page.outItems[i].value)
                                liveEngine.setOutDevice(page.outItems[i].value)
                            }
                        }
                    }

                    AppButton {
                        width: parent.width
                        text: "Настроить под кабель"
                        iconSource: "icons/bolt.svg"
                        onClicked: appState.autoRoute()
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    Row {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: "Виртуальный кабель"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Item { width: 1; height: 1 }

                        StatusPill {
                            text: appState.cableStatus()
                            pillState: appState.cableStatus() === "установлен" ? "ready" : "warn"
                            pillHeight: 22
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    AppButton {
                        width: parent.width
                        text: "Установить VB-CABLE"
                        iconSource: "icons/folder.svg"
                        flat: true
                        visible: appState.cableStatus() !== "установлен"
                        onClicked: appState.installCable()
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    Row {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: "Движок XTTS"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 13
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Item { width: 1; height: 1 }
                        StatusPill {
                            text: appState.engineInstalled() === "да" ? "установлен" : "нет"
                            pillState: appState.engineInstalled() === "да" ? "ready" : "warn"
                            pillHeight: 22
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Text {
                        text: "Движок ставится один раз:\ntools\\setup_env.ps1"
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: 11
                        lineHeight: 1.3
                    }
                }
            }
        }
    }
}
