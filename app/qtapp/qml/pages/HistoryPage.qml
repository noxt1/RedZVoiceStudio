import QtQuick
import RedZ 1.0

/// История — по референсу: список переводов сессии с действиями.
Item {
    id: page

    // буфер обмена без QtQuick.Controls
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
            title: "История"
            subtitle: "Ваши записи и сессии"
            iconSource: "icons/history.svg"
        }

        Card {
            width: parent.width
            height: parent.height - 92 - 16
            padding: 18

            Column {
                anchors.fill: parent
                spacing: 8

                Text {
                    text: "Пока пусто — нажми «Говорить (PTT)» на главной, "
                          + "и переводы появятся здесь."
                    color: Theme.textMuted
                    font.family: Theme.fontFamilyText
                    font.pixelSize: 12
                    visible: historyModel.count() === 0
                }

                ListView {
                    width: parent.width
                    height: parent.height - 62
                    clip: true
                    spacing: 4
                    model: historyModel

                    delegate: Item {
                        id: row
                        width: ListView.view.width
                        height: 58

                        required property int index
                        required property string dir
                        required property string ru
                        required property string es
                        required property string time

                        Rectangle {
                            anchors.fill: parent
                            radius: 10
                            color: rowHover.hovered ? Theme.surface2 : Theme.surface1
                            border.color: Theme.border
                            border.width: 1
                        }

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 12

                            Rectangle {
                                width: 26
                                height: 26
                                radius: 13
                                color: row.dir === "out" ? "#1B2B3A" : "#1B2A22"
                                border.color: row.dir === "out" ? Theme.incoming : Theme.success
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter

                                Icon {
                                    anchors.centerIn: parent
                                    source: row.dir === "out" ? "icons/translate.svg" : "icons/wave.svg"
                                    color: row.dir === "out" ? Theme.incoming : Theme.success
                                    size: 13
                                }
                            }

                            Column {
                                width: parent.width - 220
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2

                                Text {
                                    text: row.dir === "out" ? row.es : row.ru
                                    width: parent.width
                                    elide: Text.ElideRight
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamilyText
                                    font.pixelSize: 14
                                }
                                Text {
                                    text: (row.dir === "out" ? "RU → ES" : "ES → RU") + "  ·  " + row.time
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamilyMono
                                    font.pixelSize: 11
                                }
                            }

                            Item { width: 1; height: 1 }

                            // проиграть
                            Rectangle {
                                width: 34
                                height: 34
                                radius: 9
                                color: playHover.hovered ? Theme.surface3 : "transparent"
                                border.color: Theme.border
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter

                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/play.svg"
                                    color: Theme.accent
                                    size: 15
                                }
                                MouseArea {
                                    id: playHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: liveEngine.replay(row.ru)
                                }
                            }

                            // копировать
                            Rectangle {
                                width: 34
                                height: 34
                                radius: 9
                                color: copyHover.hovered ? Theme.surface3 : "transparent"
                                border.color: Theme.border
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter

                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/copy.svg"
                                    color: Theme.textSecondary
                                    size: 14
                                }
                                MouseArea {
                                    id: copyHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: page.copyText(row.es + " / " + row.ru)
                                }
                            }

                            // удалить
                            Rectangle {
                                width: 34
                                height: 34
                                radius: 9
                                color: delHover.hovered ? "#3A1B1A" : "transparent"
                                border.color: Theme.border
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter

                                Icon {
                                    anchors.centerIn: parent
                                    source: "icons/trash.svg"
                                    color: delHover.hovered ? Theme.danger : Theme.textMuted
                                    size: 14
                                }
                                MouseArea {
                                    id: delHover
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: historyModel.removeAt(row.index)
                                }
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

                // итог
                Row {
                    width: parent.width
                    spacing: 12

                    AppButton {
                        controlHeight: 40
                        text: "Очистить историю"
                        iconSource: "icons/trash.svg"
                        flat: true
                        enabled: historyModel.count() > 0
                        onClicked: historyModel.clear()
                    }

                    Item { width: 1; height: 1 }

                    Text {
                        text: "Всего записей: " + historyModel.count()
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
