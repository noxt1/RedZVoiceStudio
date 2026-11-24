import QtQuick
import QtQuick.Window
import Auraloom 1.0

/// Отдельное окно-инструкция: что переключить в самом Discord, чтобы
/// перевод доходил до собеседника. Auraloom Discord не настраивает —
/// только показывает шаги, поэтому окно ничего не меняет само.
Window {
    id: help

    width: 640
    height: 660
    minimumWidth: 480
    minimumHeight: 420
    color: Theme.bg
    title: "Discord — что переключить"
    modality: Qt.NonModal

    function openHelp() {
        show()
        raise()
        requestActivate()
    }

    Shortcut {
        sequences: ["Escape"]
        onActivated: help.close()
    }

    Rectangle {
        anchors.fill: parent
        gradient: Theme.gradAppBg
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        // ---------------- заголовок ----------------
        Item {
            width: parent.width
            height: 26

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                Icon {
                    source: "icons/plug.svg"
                    color: Theme.accentBright
                    size: 18
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "Что переключить в Discord"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamilyText
                    font.pixelSize: 17
                    font.weight: Theme.weightSemiBold
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Icon {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                source: "icons/close.svg"
                color: closeMouse.containsMouse ? Theme.textPrimary : Theme.textMuted
                size: 16

                MouseArea {
                    id: closeMouse
                    anchors.fill: parent
                    anchors.margins: -6
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: help.close()
                }
            }
        }

        Text {
            width: parent.width
            text: "Auraloom ничего не меняет в Discord сам — эти настройки включаются один раз вручную. Без них собеседник слышит тишину или обрывки перевода."
            color: Theme.textMuted
            font.family: Theme.fontFamilyText
            font.pixelSize: 11
            lineHeight: 1.35
            wrapMode: Text.WordWrap
        }

        Rectangle { width: parent.width; height: 1; color: Theme.border }

        Flickable {
            width: parent.width
            height: parent.height - 143
            contentWidth: width
            contentHeight: steps.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: steps
                width: parent.width - 8
                spacing: 14

                Repeater {
                    model: [
                        {
                            "n": "1",
                            "title": "Микрофон — виртуальный кабель",
                            "text": "Discord → шестерёнка «Настройки пользователя» → «Голос и видео» → «Устройство ввода». Выберите CABLE Output (VB-Audio Virtual Cable): именно в этот кабель Auraloom отправляет перевод. Если оставить физический микрофон, в канал пойдёт ваша русская речь, а перевода собеседник не услышит."
                        },
                        {
                            "n": "2",
                            "title": "Изоляция голоса — «Студия»",
                            "text": "В том же разделе, блок «Обработка входного сигнала». Переключите «Изоляция голоса» с «Изоляция голоса» на «Студия» — или выключите совсем. В режиме изоляции Discord считает синтезированный голос шумом и вырезает его: получаются обрывки или полная тишина."
                        },
                        {
                            "n": "3",
                            "title": "Шумодав, эхо и автогромкость — выключить",
                            "text": "«Шумоподавление» (Krisp) — выключить или оставить минимум. «Эхо-подавление» и «Автоматическая регулировка усиления» — тоже выключить: они подстраиваются под паузы и приглушают начало фразы."
                        },
                        {
                            "n": "4",
                            "title": "Проверка",
                            "text": "«Громкость ввода» — около 100 %. Нажмите «Проверить микрофон» и произнесите фразу в Auraloom: должен быть слышен испанский перевод, а не русский голос. Если перевод тихий — поднимите «Громкость перевода в кабель» в «Настройках» Auraloom."
                        }
                    ]

                    delegate: Row {
                        width: steps.width
                        spacing: 10

                        Rectangle {
                            width: 22
                            height: 22
                            radius: 11
                            color: Theme.surface2
                            border.color: Theme.border
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: modelData.n
                                color: Theme.accentBright
                                font.family: Theme.fontFamilyMono
                                font.pixelSize: 11
                            }
                        }

                        Column {
                            width: parent.width - 32
                            spacing: 4

                            Text {
                                width: parent.width
                                text: modelData.title
                                color: Theme.textPrimary
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 12
                                font.weight: Theme.weightSemiBold
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                width: parent.width
                                text: modelData.text
                                color: Theme.textMuted
                                font.family: Theme.fontFamilyText
                                font.pixelSize: 11
                                lineHeight: 1.35
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }

                // шаг 2 — то, из-за чего чаще всего пропадал звук
                Rectangle {
                    width: steps.width
                    height: isolText.height + 24
                    radius: Theme.radiusControl
                    color: Theme.surface1
                    border.color: Theme.accent
                    border.width: 1

                    Text {
                        id: isolText
                        anchors.fill: parent
                        anchors.margins: 12
                        text: "Частая причина «звук не проходит»: в Discord включена «Изоляция голоса». Синтез для неё — шум, и она его давит. Режим «Студия» пропускает перевод целиком."
                        color: Theme.textSecondary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 11
                        lineHeight: 1.35
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }

        Item {
            width: parent.width
            height: 6
        }

        Row {
            width: parent.width
            spacing: 8

            Text {
                width: parent.width - 140
                text: "Приложение Discord не настраивает — эти переключатели только в нём."
                color: Theme.textMuted
                font.family: Theme.fontFamilyText
                font.pixelSize: 10
                lineHeight: 1.3
                wrapMode: Text.WordWrap
                anchors.verticalCenter: parent.verticalCenter
            }

            AppButton {
                width: 120
                controlHeight: 32
                fontSize: 12
                text: "Понятно"
                onClicked: help.close()
            }
        }
    }
}
