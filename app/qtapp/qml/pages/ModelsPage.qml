import QtQuick
import QtQuick.Controls
import RedZ 1.0

/// Модели и языки — по композиции референса «Models & Languages»:
///   • шапка с поиском
///   • сегменты ASR / Перевод / TTS / Языки
///   • карточки моделей: иконка, статус, описание, языки, размеры, действия
///   • справа: состояние моделей, быстрые действия, движок
/// Все данные — из движка, ничего фиктивного.
Item {
    id: page

    property string tab: "asr"          // asr | mt | tts | packs
    property string query: ""
    // растёт при каждом обновлении каталога: заставляет пересчитать списки
    property int revision: 0

    readonly property var typeItems: [
        { "key": "asr", "label": "ASR", "sub": "Распознавание", "icon": "icons/wave.svg" },
        { "key": "mt", "label": "Перевод", "sub": "Машинный перевод", "icon": "icons/translate.svg" },
        { "key": "tts", "label": "TTS", "sub": "Синтез речи", "icon": "icons/volume.svg" },
        { "key": "packs", "label": "Языки", "sub": "Языковые пакеты", "icon": "icons/layers.svg" }
    ]

    function items() {
        var rev = page.revision   // зависимость биндинга от обновлений
        var out = []
        var cat = liveEngine.catalog
        for (var i = 0; i < cat.length; i++) {
            var m = cat[i]
            if (m.type !== page.tab) continue
            if (page.query !== ""
                    && String(m.name).toLowerCase().indexOf(page.query.toLowerCase()) < 0) continue
            out.push(m)
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
        if (m.state === "READY") return "Готова"
        if (m.installed) return "На диске"
        return "Не установлена"
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

    function sizeText(mb) {
        if (!mb || mb <= 0) return "—"
        if (mb >= 1024) return (mb / 1024).toFixed(1) + " ГБ"
        return Math.round(mb) + " МБ"
    }

    // Влезет ли модель в свободную VRAM вместе с запущенной игрой.
    function fitText(m) {
        if (!m.vram_mb || m.vram_mb <= 0) return "не занимает VRAM (CPU)"
        if (appState.vramTotal <= 0) return "нужно VRAM " + page.sizeText(m.vram_mb)
        var free = appState.vramTotal - appState.vramUsed
        if (m.vram_mb <= free) return "влезает с игрой (свободно " + page.sizeText(free) + ")"
        return "только без игры (свободно " + page.sizeText(free) + ")"
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

    function verifyAll() {
        var cat = liveEngine.catalog
        for (var i = 0; i < cat.length; i++) {
            if (cat[i].installed) liveEngine.verifyModel(cat[i].id)
        }
    }

    function downloadMissing() {
        var cat = liveEngine.catalog
        for (var i = 0; i < cat.length; i++) {
            if (!cat[i].installed && !page.downloadOf(cat[i].id)) {
                liveEngine.downloadModel(cat[i].id)
            }
        }
    }

    function installedCount() {
        var rev = page.revision
        var n = 0
        var cat = liveEngine.catalog
        for (var i = 0; i < cat.length; i++) if (cat[i].installed) n++
        return n
    }

    Component.onCompleted: {
        liveEngine.requestCatalog()
        liveEngine.requestPacks()
    }

    // Каталог приходит от движка асинхронно: страница может открыться раньше,
    // чем движок готов — тогда запрос уходит в пустоту. Повторяем по READY.
    Connections {
        target: liveEngine

        function onStateChanged(state) {
            if (state === "READY") {
                liveEngine.requestCatalog()
                liveEngine.requestPacks()
            }
        }

        function onCatalogChanged() { page.revision++ }
        function onPacksChanged() { page.revision++ }
        function onDownloadsChanged() { page.revision++ }
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
                        source: "icons/layers.svg"
                        color: Theme.accentCyan
                        size: 26
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: "Модели и языки"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 27
                        font.weight: Theme.weightSemiBold
                    }
                    Text {
                        text: "Ставьте по свободной VRAM: в «Быстрых действиях» нажмите «Обновить каталог» — подтянутся все модели HuggingFace с размерами и требованиями"
                        width: 620
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                    }
                }
            }

            AppField {
                width: 300
                fieldHeight: 40
                anchors.right: parent.right
                anchors.rightMargin: 4
                anchors.verticalCenter: parent.verticalCenter
                placeholderText: "Поиск моделей…"
                onTextEdited: (t) => page.query = t
            }
        }

        // ---------------- сегменты ----------------
        Row {
            width: parent.width
            height: 58
            spacing: 10

            Repeater {
                model: page.typeItems

                delegate: Item {
                    width: (parent.width - 30) / 4
                    height: parent.height

                    readonly property bool active: page.tab === modelData.key

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusInner
                        gradient: active ? Theme.gradAccent : null
                        color: active ? "transparent" : "#10163A"
                        border.width: 1
                        border.color: active ? Theme.accent : Theme.border

                        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
                    }

                    Row {
                        anchors.centerIn: parent
                        spacing: 10

                        Icon {
                            anchors.verticalCenter: parent.verticalCenter
                            source: modelData.icon
                            color: active ? "#FFFFFF" : Theme.accentCyan
                            size: 18
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 0

                            Text {
                                text: modelData.label
                                color: active ? "#FFFFFF" : Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                font.weight: Theme.weightSemiBold
                            }
                            Text {
                                text: modelData.sub
                                color: active ? "#E7E3FF" : Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 10
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            page.tab = modelData.key
                            if (modelData.key === "packs") liveEngine.requestPacks()
                        }
                    }
                }
            }
        }

        // ---------------- контент ----------------
        Row {
            width: parent.width
            height: parent.height - 84 - 58 - 28
            spacing: 14

            // -------- список --------
            Flickable {
                width: parent.width - 334
                height: parent.height
                clip: true
                contentWidth: width
                contentHeight: listColumn.height
                contentY: 0
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {
                    width: 6
                    policy: ScrollBar.AsNeeded
                    background: Item { }
                    contentItem: Rectangle {
                        implicitWidth: 6
                        radius: 3
                        color: Theme.accent
                        opacity: 0.45
                    }
                }

                Column {
                    id: listColumn
                    width: parent.width
                    spacing: 12

                    // ---------- модели ----------
                    Text {
                        width: parent.width
                        visible: page.tab !== "packs" && page.items().length === 0
                        text: appState.engineState === "STOPPED"
                              ? "Движок не запущен — запустите его, чтобы увидеть модели."
                              : (appState.engineState !== "READY"
                                 ? "Каталог загружается вместе с движком…"
                                 : "Ничего не найдено.")
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                    }

                    Repeater {
                        model: page.tab === "packs" ? [] : page.items()

                        delegate: Card {
                            width: listColumn.width
                            height: 138
                            padding: 16

                            Row {
                                anchors.fill: parent
                                spacing: 14

                                // иконка типа
                                Rectangle {
                                    width: 66
                                    height: 66
                                    radius: 16
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Theme.accentTile
                                    border.width: 1
                                    border.color: Theme.accentDeep

                                    Icon {
                                        anchors.centerIn: parent
                                        source: modelData.type === "asr" ? "icons/wave.svg"
                                              : (modelData.type === "mt" ? "icons/translate.svg"
                                                                         : "icons/volume.svg")
                                        color: Theme.accentCyan
                                        size: 28
                                    }
                                }

                                // описание
                                Column {
                                    width: parent.width - 66 - 14 - 150 - 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 4

                                    Row {
                                        width: parent.width
                                        spacing: 8

                                        Text {
                                            text: modelData.name
                                            elide: Text.ElideRight
                                            width: Math.min(implicitWidth, parent.width - 130)
                                            color: Theme.textPrimary
                                            font.family: Theme.fontFamilyText
                                            font.pixelSize: 15
                                            font.weight: Theme.weightSemiBold
                                        }
                                        StatusPill {
                                            text: page.stateText(modelData)
                                            pillState: page.pillState(modelData.state)
                                            pillHeight: 22
                                        }
                                    }

                                    Text {
                                        width: parent.width
                                        text: modelData.description
                                        elide: Text.ElideRight
                                        color: Theme.textSecondary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 11
                                    }

                                    // чипы языков
                                    Row {
                                        spacing: 4
                                        height: 18

                                        Repeater {
                                            model: (modelData.languages || []).slice(0, 6)

                                            delegate: Rectangle {
                                                height: 16
                                                width: chipText.implicitWidth + 12
                                                radius: 8
                                                color: "#161D48"
                                                border.width: 1
                                                border.color: Theme.border

                                                Text {
                                                    id: chipText
                                                    anchors.centerIn: parent
                                                    text: modelData
                                                    color: Theme.textSecondary
                                                    font.family: Theme.fontFamilyMono
                                                    font.pixelSize: 9
                                                }
                                            }
                                        }

                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: "· " + modelData.license
                                            color: Theme.textMuted
                                            font.family: Theme.fontFamilyText
                                            font.pixelSize: 10
                                        }
                                    }

                                    Text {
                                        width: parent.width
                                        elide: Text.ElideRight
                                        text: "Скачать " + page.sizeText(modelData.size_mb)
                                              + "  ·  На диске " + page.sizeText(modelData.disk_mb)
                                              + "  ·  RAM " + page.sizeText(modelData.ram_mb)
                                              + (modelData.vram_mb > 0
                                                 ? "  ·  VRAM " + page.sizeText(modelData.vram_mb) : "")
                                              + "  ·  " + page.fitText(modelData)
                                              + (modelData.direction
                                                 ? "  ·  " + page.directionText(modelData.direction) : "")
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamilyMono
                                        font.pixelSize: 10
                                    }
                                }

                                // действия
                                Column {
                                    width: 136
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 6

                                    AppButton {
                                        width: parent.width
                                        controlHeight: 32
                                        visible: !modelData.installed && !page.downloadOf(modelData.id)
                                        text: "Скачать"
                                        iconSource: "icons/arrow-down.svg"
                                        onClicked: liveEngine.downloadModel(modelData.id)
                                    }
                                    AppButton {
                                        width: parent.width
                                        controlHeight: 32
                                        flat: true
                                        visible: page.downloadOf(modelData.id) !== null
                                        text: "Отменить"
                                        iconSource: "icons/close.svg"
                                        onClicked: liveEngine.cancelDownload(modelData.id)
                                    }
                                    AppButton {
                                        width: parent.width
                                        controlHeight: 32
                                        flat: true
                                        visible: modelData.installed
                                        // «Выбрать» имеет смысл только для ru->X:
                                        // обратные пары (es->ru) движок берёт сам
                                        // для входящей речи, переключить на них нельзя.
                                        readonly property bool selectable:
                                            modelData.type === "asr" && modelData.state !== "READY"
                                            || (modelData.type === "mt"
                                                && String(modelData.direction || "").indexOf("ru->") === 0)
                                        text: selectable ? "Выбрать" : "Проверить"
                                        iconSource: "icons/check.svg"
                                        onClicked: {
                                            if (selectable && modelData.type === "mt")
                                                liveEngine.selectModel("mt", modelData.id)
                                            else if (selectable)
                                                liveEngine.selectModel("asr", modelData.id)
                                            else liveEngine.verifyModel(modelData.id)
                                        }
                                    }
                                    AppButton {
                                        width: parent.width
                                        controlHeight: 30
                                        flat: true
                                        visible: modelData.installed
                                        text: "Удалить"
                                        iconSource: "icons/trash.svg"
                                        onClicked: liveEngine.removeModel(modelData.id)
                                    }
                                }
                            }
                        }
                    }

                    // ---------- языковые пакеты ----------
                    Text {
                        width: parent.width
                        visible: page.tab === "packs"
                        text: liveEngine.packageStatus
                              ? liveEngine.packageStatus
                              : "Пакет — недостающие модели перевода для языка. Общие ASR и TTS не скачиваются повторно."
                        color: liveEngine.packageStatus ? Theme.accentBright : Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Repeater {
                        model: page.tab === "packs" ? liveEngine.packs : []

                        delegate: Card {
                            width: listColumn.width
                            height: 156
                            padding: 16

                            Row {
                                anchors.fill: parent
                                spacing: 14

                                Rectangle {
                                    width: 54
                                    height: 54
                                    radius: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: Theme.accentTile
                                    border.width: 1
                                    border.color: Theme.accentDeep

                                    Text {
                                        anchors.centerIn: parent
                                        text: String(modelData.code).toUpperCase()
                                        color: Theme.accentCyan
                                        font.family: Theme.fontFamilyMono
                                        font.pixelSize: 13
                                        font.weight: Theme.weightBold
                                    }
                                }

                                Column {
                                    width: parent.width - 54 - 14 - 150 - 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 4

                                    Row {
                                        spacing: 8
                                        Text {
                                            text: modelData.title
                                            color: Theme.textPrimary
                                            font.family: Theme.fontFamilyText
                                            font.pixelSize: 15
                                            font.weight: Theme.weightSemiBold
                                        }
                                        StatusPill {
                                            text: page.packStatusText(modelData.status)
                                            pillState: page.packPill(modelData.status)
                                            pillHeight: 22
                                        }
                                    }

                                    Text {
                                        width: parent.width
                                        text: "Распознавание: " + (modelData.asr_supported ? "есть" : "нет")
                                              + " · Синтез: " + (modelData.tts_supported ? "есть" : "нет")
                                              + " · Не хватает: "
                                              + (modelData.missing.length > 0
                                                 ? (modelData.missing.length + " модел. / "
                                                    + page.sizeText(modelData.missing_mb))
                                                 : "ничего")
                                        elide: Text.ElideRight
                                        color: Theme.textSecondary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 11
                                    }

                                    Text {
                                        width: parent.width
                                        text: "Собеседник → " + modelData.to_user.lang + ": "
                                              + (modelData.to_user.models.length > 0
                                                 ? page.langText(modelData.to_user.models)
                                                 : "нет маршрута")
                                        elide: Text.ElideRight
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamilyMono
                                        font.pixelSize: 10
                                    }

                                    Text {
                                        width: parent.width
                                        visible: modelData.note !== ""
                                        text: modelData.note
                                        elide: Text.ElideRight
                                        color: Theme.warning
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 10
                                    }
                                }

                                Column {
                                    width: 136
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 6

                                    AppButton {
                                        width: parent.width
                                        controlHeight: 32
                                        visible: modelData.missing.length > 0
                                                 && modelData.asr_supported
                                                 && modelData.tts_supported
                                        text: "Скачать"
                                        iconSource: "icons/arrow-down.svg"
                                        onClicked: liveEngine.installPack(modelData.code)
                                    }
                                    AppButton {
                                        width: parent.width
                                        controlHeight: 32
                                        flat: true
                                        visible: modelData.models.length > 0
                                        text: "Удалить"
                                        iconSource: "icons/trash.svg"
                                        onClicked: liveEngine.removePack(modelData.code)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // -------- правая колонка --------
            Column {
                width: 320
                height: parent.height
                spacing: 14

                Card {
                    width: parent.width
                    height: 178
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Row {
                            spacing: 10
                            Icon {
                                anchors.verticalCenter: parent.verticalCenter
                                source: "icons/check.svg"
                                color: Theme.success
                                size: 16
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Состояние моделей"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 14
                                font.weight: Theme.weightSemiBold
                            }
                        }

                        Repeater {
                            model: [
                                { "label": "ASR", "icon": "icons/wave.svg" },
                                { "label": "Перевод", "icon": "icons/translate.svg" },
                                { "label": "TTS", "icon": "icons/volume.svg" }
                            ]

                            delegate: Row {
                                width: parent.width
                                height: 24
                                spacing: 10

                                Icon {
                                    anchors.verticalCenter: parent.verticalCenter
                                    source: modelData.icon
                                    color: Theme.textSecondary
                                    size: 14
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 110
                                    text: modelData.label
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 12
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: liveEngine.modelsLoaded ? "готов" : "нет"
                                    color: liveEngine.modelsLoaded ? Theme.success : Theme.textMuted
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }
                }

                Card {
                    width: parent.width
                    height: 224
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Row {
                            spacing: 10
                            Icon {
                                anchors.verticalCenter: parent.verticalCenter
                                source: "icons/bolt.svg"
                                color: Theme.accentCyan
                                size: 16
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Быстрые действия"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 14
                                font.weight: Theme.weightSemiBold
                            }
                        }

                        AppButton {
                            width: parent.width
                            controlHeight: 32
                            flat: true
                            text: "Проверить все модели"
                            iconSource: "icons/check.svg"
                            onClicked: page.verifyAll()
                        }
                        AppButton {
                            width: parent.width
                            controlHeight: 32
                            flat: true
                            text: "Скачать недостающие"
                            iconSource: "icons/arrow-down.svg"
                            onClicked: page.downloadMissing()
                        }
                        AppButton {
                            width: parent.width
                            controlHeight: 32
                            flat: true
                            text: "Обновить каталог"
                            iconSource: "icons/refresh.svg"
                            onClicked: liveEngine.refreshCatalog()
                        }

                        Text {
                            width: parent.width
                            text: liveEngine.catalogStatus !== ""
                                  ? liveEngine.catalogStatus
                                  : "Список моделей с HuggingFace: размер, RAM/VRAM и влезает ли с игрой"
                            color: liveEngine.catalogStatus !== ""
                                   ? Theme.accentBright : Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Card {
                    width: parent.width
                    height: parent.height - 416
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 6

                        Text {
                            text: "Движок"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 14
                            font.weight: Theme.weightSemiBold
                        }

                        Text {
                            width: parent.width
                            text: appState.engineState === "READY" ? "Готов к работе"
                                 : (appState.engineState === "LOADING" ? "Загрузка моделей…"
                                    : (appState.engineState === "ERROR" && liveEngine.error !== ""
                                       ? "Ошибка" : "Остановлен"))
                            color: appState.engineState === "READY" ? Theme.success : Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                        }

                        Text {
                            width: parent.width
                            elide: Text.ElideRight
                            text: appState.gpuName !== "" ? appState.gpuName : "GPU не определён"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyMono
                            font.pixelSize: 10
                        }

                        Text {
                            width: parent.width
                            text: appState.vramTotal > 0
                                  ? (appState.vramUsed / 1024).toFixed(1) + " / "
                                    + Math.round(appState.vramTotal / 1024) + " GB VRAM"
                                  : "VRAM: нет данных"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyMono
                            font.pixelSize: 10
                        }

                        Item { width: 1; height: 2 }

                        AppButton {
                            width: parent.width
                            controlHeight: 32
                            text: liveEngine.modelsLoaded ? "Остановить модели" : "Загрузить модели"
                            iconSource: liveEngine.modelsLoaded ? "icons/stop.svg" : "icons/play.svg"
                            onClicked: liveEngine.modelsLoaded ? liveEngine.unloadModels()
                                                              : liveEngine.loadModels()
                        }

                        Text {
                            width: parent.width
                            text: page.installedCount() + " модел. на диске"
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }
    }
}
