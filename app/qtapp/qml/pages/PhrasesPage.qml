import QtQuick
import RedZ 1.0

/// Фразы — по референсу: банк реплик, прослушивание, копирование,
/// добавление своих фраз и удаление выбранной.
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
        spacing: 16

        PageTitle {
            width: parent.width
            title: "Фразы"
            subtitle: "Быстрые фразы и шаблоны"
            iconSource: "icons/bolt.svg"
        }

        Card {
            width: parent.width
            height: parent.height - 92 - 16
            padding: 18

            Column {
                anchors.fill: parent
                spacing: 8

                ListView {
                    id: list
                    width: parent.width
                    height: parent.height - (page.adding ? 152 : 62)
                    clip: true
                    spacing: 2
                    model: appState.phraseBank

                    delegate: Item {
                        id: row
                        width: ListView.view.width
                        height: 46

                        readonly property bool selected: page.selectedId === String(modelData.id)

                        Rectangle {
                            anchors.fill: parent
                            radius: 9
                            color: row.selected ? Theme.accentTile
                                 : (rowHover.hovered ? Theme.surface2 : "transparent")
                            border.color: row.selected ? Theme.accentDeep : "transparent"
                            border.width: row.selected ? 1 : 0
                        }

                        // выбор строки — под кнопками, чтобы они получали клики
                        MouseArea {
                            id: rowHover
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: page.selectedId = String(modelData.id)
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 6
                            spacing: 10

                            Icon {
                                source: "icons/star.svg"
                                color: row.selected ? Theme.accentBright : Theme.accentDeep
                                size: 14
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                text: modelData.text
                                width: parent.width - 370
                                elide: Text.ElideRight
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 14
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                text: modelData.ru
                                width: 150
                                elide: Text.ElideRight
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                                anchors.verticalCenter: parent.verticalCenter
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

                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/play.svg"
                                    color: Theme.accent
                                    size: 14
                                }
                                MouseArea {
                                    id: playHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: appState.playPhrase(String(modelData.id), appState.bankLang)
                                }
                            }

                            Rectangle {
                                width: 32
                                height: 32
                                radius: 8
                                color: copyHover.hovered ? Theme.surface3 : "transparent"
                                border.color: Theme.border
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter

                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/copy.svg"
                                    color: Theme.textSecondary
                                    size: 13
                                }
                                MouseArea {
                                    id: copyHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: page.copyText(modelData.text)
                                }
                            }
                        }
                    }
                }

                // ---- форма добавления ----
                Row {
                    width: parent.width
                    height: 84
                    spacing: 10
                    visible: page.adding

                    AppField {
                        width: (parent.width - 250) / 2
                        placeholderText: "Фраза (es)"
                        onTextEdited: (t) => page.newEs = t
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    AppField {
                        width: (parent.width - 250) / 2
                        placeholderText: "Перевод (ru)"
                        onTextEdited: (t) => page.newRu = t
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    AppButton {
                        width: 120
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
                        width: 100
                        text: "Отмена"
                        flat: true
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: page.adding = false
                    }
                }

                // ---- нижняя панель ----
                Row {
                    width: parent.width
                    spacing: 12

                    AppButton {
                        controlHeight: 44
                        text: page.adding ? "Скрыть форму" : "Добавить фразу"
                        iconSource: "icons/sparkles.svg"
                        onClicked: page.adding = !page.adding
                    }

                    AppButton {
                        controlHeight: 44
                        text: "Удалить выбранные"
                        iconSource: "icons/trash.svg"
                        flat: true
                        enabled: page.selectedId !== ""
                        onClicked: {
                            appState.deletePhrase(page.selectedId)
                            page.selectedId = ""
                        }
                    }

                    Item { width: 1; height: 1 }

                    Text {
                        text: "Всего фраз: " + appState.phraseBank.length
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }
    }
}
