import QtQuick
import QtQuick.Controls
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
    property real pressBoost: 0.0

    // Короткий импульс от нажатия кнопки: полоса реагирует на действие,
    // а потом слушается реального уровня микрофона.
    PropertyAnimation {
        id: pressAnim
        target: page
        property: "pressBoost"
        to: 0.0
        duration: 620
        easing.type: Easing.OutCubic
    }
    function micPulse() {
        page.pressBoost = 1.0
        pressAnim.restart()
    }

    // ---- адаптив: раскладка подстраивается под размер окна ----
    // compact — окно уже ~1600: боковая колонка чуть уже, отступы меньше.
    // narrow — совсем тесно: правая колонка сужается, подписи короче.
    readonly property bool compact: width < 1180
    readonly property bool narrow: width < 980
    readonly property bool shortScreen: height < 690
    readonly property int gap: compact ? 10 : 14
    readonly property int heroH: compact ? (shortScreen ? 66 : 80) : 96
    readonly property int sideW: narrow ? 268 : (compact ? 300 : 336)

    readonly property bool ready: appState.engineState === "READY"
    readonly property bool listening: liveEngine.captureOn

    // Без флагов: в узком комбо они съедали место и текст обрезался
    // («ES Исп…»). Сам язык однозначно читается по названию.
    readonly property var langItems: [
        { "label": "Испанский", "value": "es" },
        { "label": "Английский", "value": "en" },
        { "label": "Итальянский", "value": "it" },
        { "label": "Old West", "value": "ow" }
    ]
    // Короткие подписи: в колонке 130 px «ES Испанский» обрезалось до «ES Исп…».
    readonly property var peerLangItems: [
        { "label": "ES", "value": "es" },
        { "label": "EN", "value": "en" },
        { "label": "IT", "value": "it" }
    ]
    readonly property var voiceItems: [
        { "label": "María (ES)", "value": "maria" },
        { "label": "Diego (ES)", "value": "diego" },
        { "label": "Claude (ES)", "value": "claude" }
    ]

    property var profileItems: []
    property int profileIndex: -1
    // растёт при смене профиля: пересчитывает строку с reference
    property int voiceRev: 0

    function refreshProfiles() {
        var names = appState.profiles()
        var out = []
        for (var i = 0; i < names.length; i++)
            out.push({ "label": names[i], "value": names[i] })
        if (out.length === 0)
            out.push({ "label": "нет профилей — создайте на вкладке «Голос»", "value": "" })
        page.profileItems = out
        var idx = 0
        for (var j = 0; j < out.length; j++)
            if (out[j].value === appState.activeProfile) idx = j
        page.profileIndex = idx
    }

    property int langIndex: 0
    property int peerLangIndex: 0
    property int voiceIndex: 0

    function refreshLang() {
        var ids = ["es", "en", "it", "ow"]
        page.langIndex = Math.max(0, ids.indexOf(appState.targetLang))
    }

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

    Component.onCompleted: {
        refreshMics()
        refreshProfiles()
        refreshLang()
    }

    Connections {
        target: appState
        function onDevicesChanged() { page.refreshMics() }
        function onProfilesChanged() {
            page.refreshProfiles()
            page.voiceRev++
        }
        function onSettingsChanged() { page.refreshLang() }
    }

    Connections {
        target: liveEngine
        function onLevelChanged(v) { page.micLevel = v }
        function onTranslationStarted() { page.micPulse() }
        function onTranslationFinished() { page.micPulse() }
        function onCaptureChanged(on) { if (on) page.micPulse() }
    }

    // ==================================================================
    // Раскладка
    // ==================================================================
    Column {
        anchors.fill: parent
        spacing: page.gap

        HeroBanner {
            width: parent.width
            height: page.heroH
        }

        Row {
            width: parent.width
            height: parent.height - page.heroH - page.gap
            spacing: page.gap

            // ---------- левая колонка ----------
            Column {
                id: leftCol
                width: parent.width - page.sideW - page.gap
                height: parent.height
                spacing: page.gap

                // ============ живой перевод ============
                Card {
                    width: leftCol.width
                    // высота — остаток колонки: нижний ряд фиксирован,
                    // орб растёт/сжимается вместе с окном
                    height: Math.max(page.shortScreen ? 280 : 300,
                                     parent.height - bottomRow.height - page.gap)
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
                        // высота = остаток после заголовка (32), волны, кнопок (44),
                        // громкостей (30) и четырёх отступов по 8
                        Item {
                            width: parent.width
                            height: Math.max(110, parent.height - (138 + wave.height))

                            MicOrb {
                                anchors.centerIn: parent
                                anchors.verticalCenterOffset: -14
                                width: Math.min(parent.height * 0.88, parent.width * 0.5, 320)
                                height: width
                                level: page.micLevel
                                active: page.listening || liveEngine.busy
                                pressBoost: page.pressBoost
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
                            id: wave
                            width: parent.width
                            // «широко раздвигается»: под волну отдаём больше высоты
                            height: page.shortScreen ? 34 : 48
                            level: page.micLevel
                            active: page.listening || liveEngine.busy
                            pressBoost: page.pressBoost
                        }

                        // кнопки
                        Row {
                            width: parent.width
                            spacing: 10

                            Rectangle {
                                id: startBtn
                                width: Math.max(150, Math.min(190, parent.width * 0.22))
                                height: 44
                                radius: Theme.radiusControl
                                gradient: Theme.gradAccent

                                Glow {
                                    anchors.fill: parent
                                    glowColor: Theme.accent
                                    intensity: (page.listening ? 0.85 : 0.45)
                                               + page.pressBoost * 0.5
                                               + page.micLevel * 0.25
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
                                        page.micPulse()
                                        if (liveEngine.captureOn) liveEngine.stopCapture()
                                        else liveEngine.startCapture()
                                    }
                                }
                            }

                            // PTT
                            Rectangle {
                                id: pttBtn
                                width: Math.max(138, Math.min(176, parent.width * 0.20))
                                height: 44
                                radius: Theme.radiusControl
                                color: pttArea.pressed ? Theme.surface3 : "#10163A"
                                border.width: 1
                                border.color: Theme.accent

                                Glow {
                                    anchors.fill: parent
                                    glowColor: Theme.accent
                                    intensity: page.pressBoost * 0.9
                                               + page.micLevel * 0.35
                                    cornerRadius: Theme.radiusControl
                                }

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
                                    onPressed: {
                                        page.micPulse()
                                        liveEngine.pressToTalk()
                                    }
                                    onReleased: liveEngine.releaseToTalk()
                                }
                            }

                            Item { width: 1; height: 1 }

                            // выбор микрофона: ширина — остаток строки,
                            // иначе на 1280 кнопка уезжала за край карточки
                            AppCombo {
                                width: Math.max(120, parent.width - startBtn.width
                                                 - pttBtn.width - 41)
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
                                label: "Перевод в наушниках"
                                from: 0
                                to: 150
                                value: appState.incomingVolume
                                suffix: "%"
                                onMoved: (v) => appState.setIncomingVolume(Math.round(v))
                            }

                            AppSlider {
                                width: (parent.width - 14) / 2
                                label: "Перевод в кабеле"
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
                    id: bottomRow
                    width: leftCol.width
                    height: Math.max(190, Math.min(252, leftCol.height * 0.30))
                    spacing: page.gap

                    // последние переводы
                    Card {
                        width: parent.width - quick.width - page.gap
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
                                    id: historyNote
                                    anchors.right: allHistoryLink.left
                                    anchors.rightMargin: 12
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "хранение "
                                          + historyModel.retentionDays() + " дн."
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 10
                                }

                                Text {
                                    id: allHistoryLink
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
                        id: quick
                        width: page.narrow ? 232 : 296
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
                                    // на низком окне кнопки чуть ниже, иначе
                                    // последняя («Фразы») уезжает за карточку
                                    height: Math.max(22, Math.min(38, (parent.height - 34) / 4 - 6))
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
            // На 1280×840 карточки не влезали: кнопки «Моделей» уходили
            // под нижнюю кромку. Колонка прокручивается, высота карточек
            // фиксированная — ничего не обрезается.
            Flickable {
                width: page.sideW
                height: parent.height
                contentWidth: width
                contentHeight: rightCol.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {
                    policy: rightCol.height > parent.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                    width: 6
                }

                Column {
                    id: rightCol
                    width: parent.width - 8
                    spacing: 10

                // мой голос
                Card {
                    width: parent.width
                    height: 90
                    padding: 12

                    Column {
                        anchors.fill: parent
                        spacing: 6

                        Item {
                            width: parent.width
                            height: 20

                            Text {
                                anchors.left: parent.left
                                anchors.right: voiceSetup.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                elide: Text.ElideRight
                                text: {
                                    var rev = page.voiceRev
                                    return appState.voiceInfoText()
                                }
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 10
                            }
                            Text {
                                id: voiceSetup
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: "настроить →"
                                color: Theme.accentBright
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: page.navigate("voices")
                                }
                            }
                        }

                        AppCombo {
                            width: parent.width
                            height: 38
                            model: page.profileItems
                            currentIndex: page.profileIndex
                            currentText: page.profileIndex >= 0
                                         && page.profileIndex < page.profileItems.length
                                         ? page.profileItems[page.profileIndex].label
                                         : "профиль не выбран"
                            onActivated: (i) => {
                                if (i < 0 || i >= page.profileItems.length) return
                                var name = page.profileItems[i].value
                                if (name === "") {
                                    page.navigate("voices")
                                    return
                                }
                                appState.setProfile(name)
                            }
                        }
                    }
                }

                // направление
                Card {
                    width: parent.width
                    height: dirCol.implicitHeight + 32
                    padding: 16

                    Column {
                        id: dirCol
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
                                width: (parent.width - (page.narrow ? 38 : 44)) / 2
                                model: page.peerLangItems
                                currentIndex: page.peerLangIndex
                                currentText: page.peerLangItems[page.peerLangIndex].label
                                onActivated: (i) => {
                                    page.peerLangIndex = i
                                    liveEngine.setPeerLang(page.peerLangItems[i].value)
                                }
                            }

                            Rectangle {
                                width: page.narrow ? 30 : 36
                                height: page.narrow ? 30 : 36
                                radius: width / 2
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
                                width: (parent.width - (page.narrow ? 38 : 44)) / 2
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
                                width: Math.max(110, parent.width - 88)
                                model: page.langItems
                                currentIndex: page.langIndex
                                currentText: page.langItems[page.langIndex].label
                                onActivated: (i) => {
                                    page.langIndex = i
                                    appState.setTargetLang(page.langItems[i].value)
                                }
                            }
                        }
                    }
                }

                // режим
                // Высота — по содержимому: четыре кнопки вертикально
                // (4×34 + 3×6) выше прежних 196 px, и «Модели» наезжали
                // на кнопку «Вручную».
                Card {
                    width: parent.width
                    height: modeCol.implicitHeight + 32
                    padding: 16

                    Column {
                        id: modeCol
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
                    height: modelsCol.implicitHeight + 28
                    padding: 14

                    Column {
                        id: modelsCol
                        anchors.fill: parent
                        spacing: 4

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
                                height: 26
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

                        // запуск/остановка движка
                        Row {
                            width: parent.width
                            spacing: 8

                            Rectangle {
                                width: (parent.width - 8) / 2
                                height: 32
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
                                height: 32
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
}
