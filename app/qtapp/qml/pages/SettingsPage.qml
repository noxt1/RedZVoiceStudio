import QtQuick
import QtQuick.Controls
import Auraloom 1.0

/// Настройки — неоновый каркас: общие параметры, перевод/модели,
/// устройства и состояние движка. Вся логика и привязки сохранены.
Item {
    id: page

    property string hkDraft: appState.hotkeyCombo
    property string diagText: ""

    property var micItems: []
    property int micIndex: -1
    property var outItems: []
    property int outIndex: -1
    property var monitorItems: []
    property int monitorIndex: 0

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
        { "label": "Balanced — баланс", "value": "balanced" },
        { "label": "Quality — максимум качества", "value": "quality" },
        { "label": "Manual — ручной выбор", "value": "manual" }
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
        var mm = [{ "label": "авто (наушники по умолчанию)", "value": -1 }]
        for (var m = 0; m < outs.length; m++)
            mm.push({ "label": outs[m].name, "value": outs[m].id })
        page.monitorItems = mm

        var idx = -1
        for (var k = 0; k < mi.length; k++) if (mi[k].value === appState.inDevice) idx = k
        page.micIndex = idx
        var odx = -1
        for (var n = 0; n < mo.length; n++) if (mo[n].value === appState.outDevice) odx = n
        page.outIndex = odx
        var mdx = 0
        for (var p = 0; p < mm.length; p++)
            if (mm[p].value === appState.monitorDevice) mdx = p
        page.monitorIndex = mdx
    }

    Component.onCompleted: refreshDevices()

    // Снимок диагностики обновляется раз в секунду: устройства и мост
    // меняются на лету, а обновлять всё окно из-за этого не нужно.
    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: page.diagText = appState.diagnostics()
    }

    Connections {
        target: appState
        function onDevicesChanged() { page.refreshDevices() }
        function onSettingsChanged() { }
    }

    Column {
        anchors.fill: parent
        spacing: 14

        // ---------------- шапка ----------------
        Item {
            width: parent.width
            height: 84

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 16

                Rectangle {
                    width: 56
                    height: 56
                    radius: 16
                    color: Theme.accentTile
                    border.width: 1
                    border.color: Theme.accentDeep
                    anchors.verticalCenter: parent.verticalCenter

                    Glow {
                        anchors.fill: parent
                        glowColor: Theme.accent
                        intensity: 0.45
                        cornerRadius: 16
                    }

                    Icon {
                        anchors.centerIn: parent
                        source: "icons/settings.svg"
                        color: Theme.accentCyan
                        size: 26
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: "Настройки"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 27
                        font.weight: Theme.weightSemiBold
                    }
                    Text {
                        text: "Интерфейс, перевод, устройства и состояние движка"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                    }
                }
            }
        }

        // ---------------- контент ----------------
        Flickable {
            width: parent.width
            height: parent.height - 98
            clip: true
            contentWidth: width
            contentHeight: body.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            // Без видимого ползунка было непонятно, что низ «Управления»
            // не обрезан, а просто требует прокрутки.
            ScrollBar.vertical: ScrollBar {
                policy: body.implicitHeight > parent.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                width: 6
                contentItem: Rectangle {
                    implicitWidth: 6
                    radius: 3
                    color: Theme.accent
                    opacity: 0.55
                }
                background: Rectangle { color: "transparent" }
            }

            Row {
                id: body
                width: parent.width
                spacing: 14

                // ============ левая колонка ============
                Column {
                    width: parent.width - 334
                    spacing: 14

                    // ---------- общие ----------
                    Card {
                        width: parent.width
                        implicitHeight: general.implicitHeight + 32
                        padding: 16

                        Column {
                            id: general
                            width: parent.width
                            spacing: 10

                            Text {
                                text: "Общие"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Icon { source: "icons/layers.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Язык интерфейса"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppCombo { width: parent.width - 206; model: page.uiLangItems; currentIndex: 0; currentText: page.uiLangItems[0].label }
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Icon { source: "icons/translate.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Язык банка фраз"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppCombo { width: parent.width - 206; model: page.bankLangItems; currentIndex: page.bankIndex(); currentText: page.bankLangItems[page.bankIndex()].label; onActivated: (i) => appState.setBankLang(page.bankLangItems[i].value) }
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Icon { source: "icons/folder.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Режим экрана"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppCombo { width: parent.width - 206; model: page.screenItems; currentIndex: appState.fullscreen ? 0 : 1; currentText: appState.fullscreen ? "Полный экран" : "Окно"; onActivated: (i) => appState.setFullscreen(i === 0) }
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.border }

                            Row {
                                width: parent.width; spacing: 10
                                Icon { source: "icons/info.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Показывать подсказки"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppSwitch { checked: appState.hintsOn; onToggled: (on) => appState.setHints(on) }
                            }

                            Row {
                                width: parent.width; spacing: 10
                                Icon { source: "icons/bolt.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Автозагрузка моделей"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppSwitch { checked: appState.autoStartEngine; onToggled: (on) => appState.setAutoStartEngine(on) }
                                Text { text: "по умолчанию выкл."; color: Theme.textMuted; font.family: Theme.fontFamilyText; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                            }

                            Row {
                                width: parent.width; spacing: 10
                                Icon { source: "icons/folder.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Автоскачивание пакетов"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppSwitch { checked: appState.autoDownload; onToggled: (on) => appState.setAutoDownload(on) }
                                Text { text: "может скачивать из интернета"; color: Theme.textMuted; font.family: Theme.fontFamilyText; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }
                    }

                    // ---------- перевод и модели ----------
                    Card {
                        width: parent.width
                        implicitHeight: trans.implicitHeight + 32
                        padding: 16

                        Column {
                            id: trans
                            width: parent.width
                            spacing: 10

                            Text {
                                text: "Перевод и модели"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Text { text: "Режим работы"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppCombo { width: parent.width - 206; model: page.modeItems; currentIndex: page.modeIndex(); currentText: page.modeItems[page.modeIndex()].label; onActivated: (i) => appState.setMode(page.modeItems[i].value) }
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

                            Row {
                                width: parent.width
                                spacing: 10
                                Text { text: "Распознавание"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppCombo {
                                    width: parent.width - 206
                                    model: liveEngine.asrModels
                                    currentIndex: liveEngine.asrModels.length > 0 ? page.asrIndex() : -1
                                    currentText: liveEngine.asrModels.length > 0 ? liveEngine.asrModels[page.asrIndex()].label : "движок не запущен"
                                    enabled: appState.mode === "manual" && liveEngine.asrModels.length > 1
                                    opacity: enabled ? 1.0 : 0.7
                                    onActivated: (i) => appState.setAsrModel(liveEngine.asrModels[i].name)
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Text { text: "Озвучка (TTS)"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: liveEngine.ttsModel || "—"; width: parent.width - 206; color: Theme.textPrimary; font.family: Theme.fontFamilyMono; font.pixelSize: 11; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter }
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
                                Text { text: "В списке только установленные модели"; color: Theme.textMuted; font.family: Theme.fontFamilyText; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                                Item { width: 1; height: 1 }
                                AppButton { width: 150; controlHeight: 30; text: "Обновить список"; flat: true; onClicked: liveEngine.requestModels() }
                            }
                        }
                    }

                    // ---------- горячие клавиши ----------
                    Card {
                        width: parent.width
                        implicitHeight: hotkeys.implicitHeight + 32
                        padding: 16

                        Column {
                            id: hotkeys
                            width: parent.width
                            spacing: 10

                            Text {
                                text: "Управление"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Icon { source: "icons/plug.svg"; color: Theme.textMuted; size: 16; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Мост микрофон → кабель"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppSwitch { checked: appState.bridgeOn; onToggled: (on) => appState.toggleBridge() }
                                StatusPill { text: appState.bridgeOn ? "работает" : "выключен"; pillState: appState.bridgeOn ? "ready" : "idle"; pillHeight: 22; anchors.verticalCenter: parent.verticalCenter }
                            }

                            Row {
                                width: parent.width
                                spacing: 10
                                Text { text: "Горячая клавиша"; width: 180; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                AppField { width: 170; fieldHeight: 34; text: page.hkDraft; placeholderText: "alt+capslock"; onTextEdited: (t) => page.hkDraft = t; anchors.verticalCenter: parent.verticalCenter }
                                AppButton { width: 110; controlHeight: 34; text: "Применить"; flat: true; onClicked: appState.setHotkey(page.hkDraft) }
                                AppButton { width: 110; controlHeight: 34; text: appState.hotkeysOn ? "Выключить" : "Включить"; flat: true; onClicked: appState.toggleHotkeys() }
                            }

                            Text {
                                text: "Говорить (удерживать) · " + appState.hotkeyPretty()
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                            }
                        }
                    }

                    // ---------- диагностика ----------
                    Card {
                        width: parent.width
                        implicitHeight: diag.implicitHeight + 32
                        padding: 16

                        Column {
                            id: diag
                            width: parent.width
                            spacing: 8

                            Text {
                                text: "Диагностика"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
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
                                         : "нет данных — скажите фразу в игре")
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                text: "отброшено: " + (liveEngine.lastMetrics["dropped"] || 0)
                                      + " · отменено: " + (liveEngine.lastMetrics["cancelled"] || 0)
                                      + " · logs/diagnostics.log"
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.border }

                            Text {
                                width: parent.width
                                text: page.diagText
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 10
                                lineHeight: 1.3
                                wrapMode: Text.WrapAnywhere
                            }

                            Row {
                                width: parent.width
                                spacing: 8
                                AppButton {
                                    width: 170
                                    controlHeight: 34
                                    text: "Собрать отчёт"
                                    onClicked: appState.collectReport()
                                }
                                AppButton {
                                    width: 150
                                    controlHeight: 34
                                    text: "Открыть папку"
                                    flat: true
                                    visible: appState.reportPath !== ""
                                    onClicked: appState.openReportsFolder()
                                }
                            }

                            Text {
                                width: parent.width
                                text: appState.reportStatus !== ""
                                      ? (appState.reportStatus + ". Логи и настройки, без истории и образцов голоса.")
                                      : "Отчёт: логи, настройки и версия сборки. История переводов и образцы голоса в него не попадают."
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }

                // ============ правая колонка ============
                Column {
                    width: 320
                    spacing: 14

                    Card {
                        width: parent.width
                        implicitHeight: dev.implicitHeight + 32
                        padding: 16

                        Column {
                            id: dev
                            width: parent.width
                            spacing: 10

                            Text {
                                text: "Устройства"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }

                            Text { text: "Микрофон"; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 12 }
                            AppCombo {
                                width: parent.width
                                model: page.micItems
                                currentIndex: page.micIndex
                                currentText: page.micIndex >= 0 && page.micItems.length > 0 ? page.micItems[page.micIndex].label : "нет устройств"
                                onActivated: (i) => {
                                    page.micIndex = i
                                    appState.setInDevice(page.micItems[i].value)
                                    liveEngine.setMicDevice(page.micItems[i].value)
                                }
                            }

                            Text { text: "Выход"; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 12 }
                            AppCombo {
                                width: parent.width
                                model: page.outItems
                                currentIndex: page.outIndex
                                currentText: page.outIndex >= 0 && page.outItems.length > 0 ? page.outItems[page.outIndex].label : "нет устройств"
                                onActivated: (i) => {
                                    page.outIndex = i
                                    appState.setOutDevice(page.outItems[i].value)
                                    liveEngine.setOutDevice(page.outItems[i].value)
                                }
                            }

                            Text { text: "Наушники для перевода"; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 12 }
                            AppCombo {
                                width: parent.width
                                model: page.monitorItems
                                currentIndex: page.monitorIndex
                                currentText: page.monitorIndex >= 0 && page.monitorItems.length > 0
                                             ? page.monitorItems[page.monitorIndex].label
                                             : "авто (наушники по умолчанию)"
                                onActivated: (i) => {
                                    page.monitorIndex = i
                                    appState.setMonitorDevice(page.monitorItems[i].value)
                                }
                            }

                            AppButton {
                                width: parent.width
                                text: "Настроить под кабель"
                                iconSource: "icons/bolt.svg"
                                onClicked: appState.autoRoute()
                            }
                        }
                    }

                    Card {
                        width: parent.width
                        implicitHeight: cab.implicitHeight + 32
                        padding: 16

                        Column {
                            id: cab
                            width: parent.width
                            spacing: 10

                            Text {
                                text: "Кабель и движок"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 15
                                font.weight: Theme.weightSemiBold
                            }

                            Row {
                                width: parent.width
                                spacing: 8
                                Text { text: "Виртуальный кабель"; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                Item { width: 1; height: 1 }
                                StatusPill { text: appState.cableStatus(); pillState: appState.cableStatus() === "установлен" ? "ready" : (appState.cableStatus() === "нужна перезагрузка" ? "loading" : "warn"); pillHeight: 22; anchors.verticalCenter: parent.verticalCenter }
                            }

                            AppButton {
                                width: parent.width
                                text: "Установить VB-CABLE"
                                iconSource: "icons/folder.svg"
                                flat: true
                                visible: appState.cableStatus() === "не установлен"
                                onClicked: appState.installCable()
                            }

                            Text {
                                width: parent.width
                                visible: appState.cableStatus() === "нужна перезагрузка"
                                text: "Драйвер уже установлен, но Windows ещё не видит устройств: перезагрузи компьютер, потом нажми «Перечитать устройства»."
                                wrapMode: Text.WordWrap
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                            }

                            AppButton {
                                width: parent.width
                                text: "Перечитать устройства"
                                iconSource: "icons/refresh.svg"
                                flat: true
                                onClicked: appState.refreshAudioDevices()
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.border }

                            Row {
                                width: parent.width
                                spacing: 8
                                Text { text: "Движок XTTS"; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                Item { width: 1; height: 1 }
                                StatusPill { text: appState.engineInstalled() === "да" ? "установлен" : "нет"; pillState: appState.engineInstalled() === "да" ? "ready" : "warn"; pillHeight: 22; anchors.verticalCenter: parent.verticalCenter }
                            }

                            Text {
                                text: "Движок ставится один раз:\ntools\\setup_env.ps1"
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 11
                                lineHeight: 1.3
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.border }

                            Row {
                                width: parent.width
                                spacing: 8
                                Text { text: "Русский микрофон в кабеле"; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                                Item { width: 1; height: 1 }
                                AppSwitch {
                                    checked: appState.cableMicOn
                                    onToggled: (on) => appState.setCableMic(on)
                                }
                            }
                            Text {
                                width: parent.width
                                text: "Выключено: в игру уходит только перевод. Включено: собеседники слышат и ваш русский голос."
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }

                            Rectangle { width: parent.width; height: 1; color: Theme.border }

                            Text {
                                width: parent.width
                                text: appState.gpuName !== "" ? appState.gpuName : "GPU не определён"
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 10
                            }
                            Text {
                                width: parent.width
                                text: appState.vramTotal > 0 ? (appState.vramUsed / 1024).toFixed(1) + " / " + Math.round(appState.vramTotal / 1024) + " GB VRAM" : "VRAM: нет данных"
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }
        }
    }
}
