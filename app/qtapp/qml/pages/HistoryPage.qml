import QtQuick
import Auraloom 1.0

/// История — неоновый каркас: список переводов сессии и быстрые действия.
Item {
    id: page

    /// Куда сохранился последний экспорт (пусто — ничего не сохраняли).
    property string exportNote: ""

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
                        source: "icons/history.svg"
                        color: Theme.accentCyan
                        size: 26
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: "История"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 27
                        font.weight: Theme.weightSemiBold
                    }
                    Text {
                        text: "Переводы этой сессии: прослушать, скопировать, удалить"
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

                    Text {
                        text: "Пока пусто — нажмите «Говорить (PTT)» на главной, и переводы появятся здесь."
                        color: Theme.textMuted
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 12
                        visible: historyModel.count() === 0
                    }

                    ListView {
                        width: parent.width
                        height: parent.height - 2
                        clip: true
                        spacing: 6
                        model: historyModel

                        delegate: Item {
                            id: row
                            width: ListView.view.width
                            height: 64

                            required property int index
                            required property string dir
                            required property string ru
                            required property string es
                            required property string time

                            Rectangle {
                                anchors.fill: parent
                                radius: 12
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Theme.cardTop }
                                    GradientStop { position: 1.0; color: Theme.cardBottom }
                                }
                                border.color: rowHover.hovered ? Theme.accentDeep : Theme.border
                                border.width: 1
                            }

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                spacing: 12

                                Rectangle {
                                    width: 30
                                    height: 30
                                    radius: 10
                                    color: Theme.accentTile
                                    border.color: row.dir === "out" ? Theme.accentDeep : Theme.successDeep
                                    border.width: 1
                                    anchors.verticalCenter: parent.verticalCenter

                                    Icon {
                                        anchors.centerIn: parent
                                        source: row.dir === "out" ? "icons/translate.svg" : "icons/wave.svg"
                                        color: row.dir === "out" ? Theme.accentCyan : Theme.success
                                        size: 14
                                    }
                                }

                                Column {
                                    width: parent.width - 210
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2

                                    Text {
                                        text: row.dir === "out" ? row.es : row.ru
                                        width: parent.width
                                        elide: Text.ElideRight
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamilyText
                                        font.pixelSize: 14
                                        font.weight: Theme.weightMedium
                                    }
                                    Text {
                                        text: (row.dir === "out" ? "RU → ES  ·  " : "ES → RU  ·  ") + row.time
                                        color: Theme.textMuted
                                        font.family: Theme.fontFamilyMono
                                        font.pixelSize: 11
                                    }
                                }

                                Item { width: 1; height: 1 }

                                Rectangle {
                                    width: 34
                                    height: 34
                                    radius: 9
                                    color: playHover.hovered ? Theme.surface3 : "transparent"
                                    border.color: Theme.border
                                    border.width: 1
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon { anchors.centerIn: parent; source: "icons/play.svg"; color: Theme.accentCyan; size: 15 }
                                    MouseArea { id: playHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: liveEngine.replay(row.ru) }
                                }

                                Rectangle {
                                    width: 34
                                    height: 34
                                    radius: 9
                                    color: copyHover.hovered ? Theme.surface3 : "transparent"
                                    border.color: Theme.border
                                    border.width: 1
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon { anchors.centerIn: parent; source: "icons/copy.svg"; color: Theme.textSecondary; size: 14 }
                                    MouseArea { id: copyHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: page.copyText(row.es + " / " + row.ru) }
                                }

                                Rectangle {
                                    width: 34
                                    height: 34
                                    radius: 9
                                    color: delHover.hovered ? Theme.dangerTile : "transparent"
                                    border.color: Theme.border
                                    border.width: 1
                                    anchors.verticalCenter: parent.verticalCenter
                                    Icon { anchors.centerIn: parent; source: "icons/trash.svg"; color: delHover.hovered ? Theme.danger : Theme.textMuted; size: 14 }
                                    MouseArea { id: delHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: historyModel.removeAt(row.index) }
                                }
                            }

                            MouseArea {
                                id: rowHover
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.NoButton
                                z: -1
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
                    height: 268
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: "Сводка"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 15
                            font.weight: Theme.weightSemiBold
                        }

                        Row {
                            width: parent.width
                            Text { text: "Записей"; width: parent.width - 60; color: Theme.textSecondary; font.family: Theme.fontFamilyText; font.pixelSize: 12 }
                            Text { text: historyModel.count(); color: Theme.accentCyan; font.family: Theme.fontFamilyMono; font.pixelSize: 16; font.weight: Theme.weightBold }
                        }

                        Text {
                            width: parent.width
                            text: "Новые переводы сверху. Хранится "
                                  + historyModel.retentionDays()
                                  + " дня, затем записи удаляются автоматически."
                            wrapMode: Text.WordWrap
                            color: Theme.textMuted
                            font.family: Theme.fontFamilyText
                            font.pixelSize: 11
                        }

                        Row {
                            width: parent.width
                            spacing: 8

                            AppButton {
                                width: (parent.width - 8) / 2
                                controlHeight: 30
                                text: "Экспорт JSON"
                                flat: true
                                enabled: historyModel.count() > 0
                                onClicked: {
                                    var p = historyModel.exportJson()
                                    page.exportNote = p !== "" ? ("сохранено: " + p) : "не удалось сохранить"
                                }
                            }
                            AppButton {
                                width: (parent.width - 8) / 2
                                controlHeight: 30
                                text: "Экспорт TXT"
                                flat: true
                                enabled: historyModel.count() > 0
                                onClicked: {
                                    var p = historyModel.exportTxt()
                                    page.exportNote = p !== "" ? ("сохранено: " + p) : "не удалось сохранить"
                                }
                            }
                        }

                        Text {
                            width: parent.width
                            visible: page.exportNote !== ""
                            text: page.exportNote
                            elide: Text.ElideMiddle
                            color: Theme.success
                            font.family: Theme.fontFamilyMono
                            font.pixelSize: 10
                        }

                        AppButton {
                            width: parent.width
                            controlHeight: 34
                            text: "Очистить историю"
                            iconSource: "icons/trash.svg"
                            flat: true
                            enabled: historyModel.count() > 0
                            onClicked: {
                                historyModel.clear()
                                page.exportNote = ""
                            }
                        }
                    }
                }

                Card {
                    width: parent.width
                    height: parent.height - 282
                    padding: 16

                    Column {
                        anchors.fill: parent
                        spacing: 8

                        Text {
                            text: "Подсказка"
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
                            text: "Нажмите ▶, чтобы снова озвучить русский текст.\n\nНажмите значок копирования — в буфер попадут обе версии фразы.\n\nПоследняя реплика также видна на главной."
                        }
                    }
                }
            }
        }
    }
}
