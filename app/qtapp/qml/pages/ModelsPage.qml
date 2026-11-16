import QtQuick
import RedZ 1.0

/// Модели — единый раздел управления моделями (ASR / перевод / синтез)
/// и языковыми пакетами. Данные целиком приходят из движка: ничего
/// фиктивного здесь не создаётся.
Item {
    id: page

    property string tab: "models"        // models | packs
    property string typeFilter: "asr"    // asr | mt | tts
    property int selectedPack: -1

    readonly property var typeItems: [
        { "key": "asr", "label": "Распознавание" },
        { "key": "mt", "label": "Перевод" },
        { "key": "tts", "label": "Синтез" }
    ]

    function items() {
        var out = []
        var cat = liveEngine.catalog
        for (var i = 0; i < cat.length; i++) {
            if (cat[i].type === page.typeFilter) out.push(cat[i])
        }
        return out
    }

    function downloadOf(id) {
        var d = liveEngine.downloads[id]
        return d ? d : null
    }

    function pillState(state) {
        if (state === "READY") return "ready"
        if (state === "DOWNLOADING" || state === "INSTALLING") return "loading"
        if (state === "ERROR") return "error"
        if (state === "STOPPED") return "warn"
        return "idle"
    }

    function stateText(m) {
        var d = page.downloadOf(m.id)
        if (d) {
            var s = d.state
            if (d.percent > 0) s += " " + d.percent + "%"
            return s
        }
        return m.state
    }

    function typeLabel(t) {
        if (t === "asr") return "ASR"
        if (t === "mt") return "Перевод"
        if (t === "tts") return "TTS"
        return t
    }

    function langText(list) {
        if (!list) return "—"
        var names = []
        var max = Math.min(list.length, 12)
        for (var i = 0; i < max; i++) names.push(list[i])
        var s = names.join(", ")
        if (list.length > max) s += " … (+" + (list.length - max) + ")"
        return s
    }

    function packPill(status) {
        if (status === "READY") return "ready"
        if (status === "PARTIAL") return "warn"
        if (status === "UNSUPPORTED") return "error"
        return "idle"
    }

    function packStatusText(status) {
        if (status === "READY") return "готов"
        if (status === "PARTIAL") return "частично"
        if (status === "UNSUPPORTED") return "не поддержан"
        return "не установлен"
    }

    function directionText(dir) {
        if (!dir) return ""
        var parts = dir.split("->")
        if (parts.length !== 2) return dir
        return parts[0] + " → " + parts[1]
    }

    Component.onCompleted: {
        liveEngine.requestCatalog()
        liveEngine.requestPacks()
    }

    Column {
        anchors.fill: parent
        spacing: 16

        PageTitle {
            width: parent.width
            title: "Модели и языки"
            subtitle: "Реальные модели на диске: установка, проверка, выбор"
            iconSource: "icons/layers.svg"
        }

        Row {
            width: parent.width
            spacing: 10

            AppButton {
                text: "Модели"
                flat: true
                highlighted: page.tab === "models"
                controlHeight: 34
                onClicked: { page.tab = "models"; page.selectedPack = -1 }
            }
            AppButton {
                text: "Языковые пакеты"
                flat: true
                highlighted: page.tab === "packs"
                controlHeight: 34
                onClicked: { page.tab = "packs"; liveEngine.requestPacks() }
            }

            Item { width: 12; height: 1 }

            AppButton {
                text: liveEngine.modelsLoaded ? "Остановить модели" : "Загрузить модели"
                flat: true
                controlHeight: 34
                iconSource: liveEngine.modelsLoaded ? "icons/stop.svg" : "icons/play.svg"
                onClicked: liveEngine.modelsLoaded ? liveEngine.unloadModels()
                                                  : liveEngine.loadModels()
            }
            AppButton {
                text: "Обновить"
                flat: true
                controlHeight: 34
                iconSource: "icons/refresh.svg"
                onClicked: {
                    liveEngine.requestCatalog()
                    liveEngine.requestPacks()
                    liveEngine.requestModels()
                }
            }
        }

        // ---------------- модели ----------------
        Column {
            width: parent.width
            height: parent.height - 92 - 16 - 34 - 16
            spacing: 12
            visible: page.tab === "models"

            Row {
                width: parent.width
                spacing: 8

                Repeater {
                    model: page.typeItems
                    delegate: AppButton {
                        text: modelData.label
                        flat: true
                        highlighted: page.typeFilter === modelData.key
                        controlHeight: 30
                        onClicked: page.typeFilter = modelData.key
                    }
                }
            }

            Flickable {
                width: parent.width
                height: parent.height - 42
                clip: true
                contentWidth: width
                contentHeight: modelColumn.height
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: modelColumn
                    width: parent.width
                    spacing: 12

                    Text {
                        width: parent.width
                        visible: page.items().length === 0
                        text: appState.engineState === "STOPPED"
                              ? "Движок не запущен — запусти его, чтобы увидеть модели."
                              : "Нет данных каталога."
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Repeater {
                        model: page.items()

                        delegate: Card {
                            width: modelColumn.width
                            height: contentColumn.implicitHeight + 36
                            padding: 18

                            Column {
                                id: contentColumn
                                width: parent.width
                                spacing: 8

                                Row {
                                    width: parent.width
                                    spacing: 10

                                    Text {
                                        text: modelData.name
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 16
                                        font.weight: Theme.weightSemiBold
                                    }
                                    StatusPill {
                                        text: page.typeLabel(modelData.type)
                                        pillState: "idle"
                                    }
                                    StatusPill {
                                        text: page.stateText(modelData)
                                        pillState: page.pillState(modelData.state)
                                    }
                                    Item { width: 1; height: 1 }
                                    Text {
                                        text: modelData.installed
                                              ? ("на диске " + modelData.disk_mb + " МБ")
                                              : ("нужно скачать ~" + modelData.size_mb + " МБ")
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 11
                                    }
                                }

                                Text {
                                    width: parent.width
                                    text: modelData.description
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    width: parent.width
                                    text: modelData.developer + " · " + modelData.source
                                          + " · лицензия " + modelData.license
                                          + " · RAM " + modelData.ram_mb + " МБ"
                                          + (modelData.vram_mb > 0
                                             ? (" · VRAM " + modelData.vram_mb + " МБ") : "")
                                          + " · " + (modelData.devices || []).join("/")
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    width: parent.width
                                    text: (modelData.direction
                                           ? ("Направление: " + page.directionText(modelData.direction) + " · ")
                                           : "")
                                          + "Языки: " + page.langText(modelData.languages)
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }

                                Row {
                                    spacing: 8

                                    AppButton {
                                        visible: !modelData.installed
                                                 && !page.downloadOf(modelData.id)
                                        text: "Скачать"
                                        flat: true
                                        controlHeight: 30
                                        iconSource: "icons/arrow-down.svg"
                                        onClicked: liveEngine.downloadModel(modelData.id)
                                    }
                                    AppButton {
                                        visible: page.downloadOf(modelData.id) !== null
                                        text: "Отменить"
                                        flat: true
                                        controlHeight: 30
                                        iconSource: "icons/close.svg"
                                        onClicked: liveEngine.cancelDownload(modelData.id)
                                    }
                                    AppButton {
                                        visible: modelData.installed
                                        text: "Проверить"
                                        flat: true
                                        controlHeight: 30
                                        iconSource: "icons/check.svg"
                                        onClicked: liveEngine.verifyModel(modelData.id)
                                    }
                                    AppButton {
                                        visible: modelData.installed && modelData.type === "asr"
                                                 && modelData.state !== "READY"
                                        text: "Выбрать"
                                        flat: true
                                        controlHeight: 30
                                        onClicked: liveEngine.selectModel("asr", modelData.id)
                                    }
                                    AppButton {
                                        visible: modelData.installed && modelData.type === "mt"
                                        text: "Выбрать"
                                        flat: true
                                        controlHeight: 30
                                        onClicked: liveEngine.selectModel("mt", modelData.id)
                                    }
                                    AppButton {
                                        visible: modelData.installed
                                        text: "Удалить"
                                        flat: true
                                        controlHeight: 30
                                        iconSource: "icons/trash.svg"
                                        onClicked: liveEngine.removeModel(modelData.id)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ---------------- языковые пакеты ----------------
        Column {
            width: parent.width
            height: parent.height - 92 - 16 - 34 - 16
            spacing: 10
            visible: page.tab === "packs"

            Text {
                width: parent.width
                text: liveEngine.packageStatus
                      ? liveEngine.packageStatus
                      : "Пакет = недостающие модели перевода для языка. Общие ASR и TTS не скачиваются повторно."
                color: liveEngine.packageStatus ? Theme.accentBright : Theme.textMuted
                font.family: Theme.fontFamilyText
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Flickable {
                width: parent.width
                height: parent.height - 32
                clip: true
                contentWidth: width
                contentHeight: packColumn.height
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: packColumn
                    width: parent.width
                    spacing: 10

                    Text {
                        width: parent.width
                        visible: liveEngine.packs.length === 0
                        text: "Нет данных — запусти движок."
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                    }

                    Repeater {
                        model: liveEngine.packs

                        delegate: Card {
                            width: packColumn.width
                            height: packContent.implicitHeight + 32
                            padding: 16

                            Column {
                                id: packContent
                                width: parent.width
                                spacing: 6

                                Row {
                                    width: parent.width
                                    spacing: 10

                                    Text {
                                        text: modelData.title
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 15
                                        font.weight: Theme.weightSemiBold
                                    }
                                    Text {
                                        text: modelData.code
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamilyMono
                                        font.pixelSize: 11
                                    }
                                    StatusPill {
                                        text: page.packStatusText(modelData.status)
                                        pillState: page.packPill(modelData.status)
                                    }
                                }

                                Text {
                                    width: parent.width
                                    text: "Распознавание: " + (modelData.asr_supported ? "есть" : "нет")
                                          + " · Синтез: " + (modelData.tts_supported ? "есть" : "нет")
                                          + " · Не хватает: "
                                          + (modelData.missing.length > 0
                                             ? (modelData.missing.length + " модел. / "
                                                + modelData.missing_mb + " МБ")
                                             : "ничего")
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    width: parent.width
                                    text: "Речь собеседника → " + modelData.to_user.lang + ": "
                                          + (modelData.to_user.models.length > 0
                                             ? page.langText(modelData.to_user.models)
                                             : "нет маршрута")
                                          + "  ·  " + modelData.code + " → " + modelData.to_user.lang
                                          + ": " + modelData.from_user.kind
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyMono
                                    font.pixelSize: 10
                                    wrapMode: Text.WrapAnywhere
                                }

                                Text {
                                    width: parent.width
                                    visible: modelData.note !== ""
                                    text: modelData.note
                                    color: Theme.warning
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }

                                Row {
                                    spacing: 8

                                    AppButton {
                                        visible: modelData.missing.length > 0
                                                 && modelData.asr_supported
                                                 && modelData.tts_supported
                                        text: "Скачать пакет"
                                        flat: true
                                        controlHeight: 28
                                        iconSource: "icons/arrow-down.svg"
                                        onClicked: liveEngine.installPack(modelData.code)
                                    }
                                    AppButton {
                                        visible: modelData.missing.length === 0
                                        text: "Проверить"
                                        flat: true
                                        controlHeight: 28
                                        iconSource: "icons/check.svg"
                                        onClicked: liveEngine.verifyPack(modelData.code)
                                    }
                                    AppButton {
                                        visible: modelData.models.length > 0
                                        text: "Удалить"
                                        flat: true
                                        controlHeight: 28
                                        iconSource: "icons/trash.svg"
                                        onClicked: liveEngine.removePack(modelData.code)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
