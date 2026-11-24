import QtQuick
import Auraloom 1.0

/// Фразы — неоновый каркас: банк реплик, добавление, прослушивание, удаление.
Item {
    id: page

    property string selectedId: ""
    property bool adding: false
    property string newEs: ""
    property string newRu: ""

    TextEdit {
        id: clip
        visible: false
        width: 1
        height: 1
    }

    function copyText(text) {
        if (!text) return
        clip.text = text
        clip.selectAll()
        clip.copy()
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
                        source: "icons/bolt.svg"
                        color: Theme.accentCyan
                        size: 26
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: "Фразы"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 27
                        font.weight: Theme.weightSemiBold
                    }
                    Text {
                        text: "Быстрые реплики и шаблоны — озвучить, скопировать, добавить свою"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                    }
                }
            }
        }

        // ---------------- контент ----------------
        Row {
            width: parent.width
            height: parent.height - 98
            spacing: 14

            Card {
                width: parent.width - 334
                height: parent.height
                padding: 16

                Column {
                    anchors.fill: parent
                    spacing: 8

                    ListView {
                        id: list
                        width: parent.width
                        height: parent.height - (page.adding ? 144 : 2)
                        clip: true
                        spacing: 4
                        model: appState.phraseBank

                        delegate: Item {
                            id: row
                            width: ListView.view.width
                            height: 50

                            readonly property bool selected: page.selectedId === String(modelData.id)

                            Rectangle {
                                anchors.fill: parent
                                radius: 10
                                color: row.selected ? "#161C4A" : "transparent"
                                border.color: row.selected ? Theme.accent : (rowHover.hovered ? Theme.borderStrong : "transparent")
                                border.width: row.selected || rowHover.hovered ? 1 : 0
                            }

                            MouseArea {
                                id: rowHover
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: page.selectedId = String(modelData.id)
                            }

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 8
                                spacing: 10

                                Rectangle {
                                    width: 28
                                    height: 28
                                    radius: 8
                                    color: Theme.accentTile
                                    border.width: 1
                                    border.color: row.selected ? Theme.accent : Theme.accentDeep
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon { anchors.centerIn: parent; source: "icons/bolt.svg"; color: row.selected ? Theme.accentBright : Theme.accentCyan; size: 13 }
                                }

                                Column {
                                    width: parent.width - 220
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 1

                                    Text {
                                        text: modelData.text
                                        width: parent.width
                                        elide: Text.ElideRight
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 14
                                    }
                                    Text {
                                        text: modelData.ru
                                        width: parent.width
                                        elide: Text.ElideRight
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 11
                                    }
                                }

                                Item { width: 1; height: 1 }

                                Rectangle {
                                    width: 32
                                    height: 32
                                    radius: 8
                                    color: playHover.hovered ? Theme.surface3 : "transparent"
                                    border.color: Theme.border
                                    border.width: 1
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon { anchors.centerIn: parent; source: "icons/play.svg"; color: Theme.accentCyan; size: 14 }
                                    MouseArea { id: playHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: appState.playPhrase(String(modelData.id), appState.bankLang) }
                                }

                                Rectangle {
                                    width: 32
                                    height: 32
                                    radius: 8
                                    color: copyHover.hovered ? Theme.surface3 : "transparent"
                                    border.color: Theme.border
                                    border.width: 1
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon { anchors.centerIn: parent; source: "icons/copy.svg"; color: Theme.textSecondary; size: 13 }
                                    MouseArea { id: copyHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: page.copyText(modelData.text) }
                                }
                            }
                        }
                    }

                    // ---- форма добавления ----
                    Rectangle {
                        width: parent.width
                        height: 132
                        radius: Theme.radiusInner
                        color: "#0E1438"
                        border.width: 1
                        border.color: Theme.border
                        visible: page.adding

                        Column {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Text {
                                text: "Новая фраза"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 13
                                font.weight: Theme.weightSemiBold
                            }

                            Row {
                                width: parent.width
                                spacing: 8

                                AppField {
                                    width: (parent.width - 216) / 2
                                    placeholderText: "Фраза (es)"
                                    onTextEdited: (t) => page.newEs = t
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                AppField {
                                    width: (parent.width - 216) / 2
                                    placeholderText: "Перевод (ru)"
                                    onTextEdited: (t) => page.newRu = t
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                AppButton {
                                    width: 100
                                    controlHeight: 34
                                    text: "Сохранить"
                                    iconSource: "icons/check.svg"
                                    anchors.verticalCenter: parent.verticalCenter
                                    onClicked: {
                                        if (appState.addPhrase(page.newEs, page.newRu) !== "") {
                                            page.newEs = ""
                                            page.newRu = ""
                                            page.adding = false
                                        }
                                    }
                                }
                                AppButton {
                                    width: 92
                                    controlHeight: 34
                                    text: "Отмена"
                                    flat: true
                                    anchors.verticalCenter: parent.verticalCenter
                                    onClicked: page.adding = false
                                }
                            }
                        }
                    }
                }
            }

            Column {
                width: 320
                height: parent.height
                spacing: 14

                Card {
                    width: parent.width
                    height: 210
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: "Действия"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 15
                            font.weight: Theme.weightSemiBold
                        }

                        AppButton {
                            width: parent.width
                            controlHeight: 34
                            text: page.adding ? "Скрыть форму" : "Добавить фразу"
                            iconSource: "icons/sparkles.svg"
                            onClicked: page.adding = !page.adding
                        }

                        AppButton {
                            width: parent.width
                            controlHeight: 34
                            text: "Удалить выбранную"
                            iconSource: "icons/trash.svg"
                            flat: true
                            enabled: page.selectedId !== ""
                            onClicked: {
                                appState.deletePhrase(page.selectedId)
                                page.selectedId = ""
                            }
                        }

                        Rectangle { width: parent.width; height: 1; color: Theme.border }

                        Row {
                            width: parent.width
                            Text { text: "Всего фраз"; width: parent.width - 40; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 12 }
                            Text { text: appState.phraseBank.length; color: Theme.accentCyan; font.family: Theme.fontFamilyMono; font.pixelSize: 16; font.weight: Theme.weightBold }
                        }
                    }
                }

                Card {
                    width: parent.width
                    height: parent.height - 224
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 8

                        Text {
                            text: "Как пользоваться"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 15
                            font.weight: Theme.weightSemiBold
                        }

                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            color: Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 12
                            lineHeight: 1.3
                            text: "Нажмите на фразу, чтобы выбрать её.\n\n▶ — озвучить выбранным языком банка.\n\nСкопировать — текст фразы в буфер.\n\n«Добавить фразу» — своя пара (испанский и перевод). Язык банка меняется в настройках."
                        }
                    }
                }
            }
        }
    }
}
