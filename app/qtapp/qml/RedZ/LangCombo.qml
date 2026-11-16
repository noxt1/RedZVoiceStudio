import QtQuick
import QtQuick.Controls
import RedZ 1.0

/// Выпадающий список выбора языка (как в референсе).
Item {
    id: root

    property string label: ""
    property var items: []   // [{label, value}]
    property string currentLabel: ""
    property int currentIndex: -1

    signal changed(int index)

    property bool dropdownOpen: false

    implicitWidth: 220
    implicitHeight: 72

    Column {
        anchors.fill: parent
        spacing: Theme.spaceXXS

        Text {
            text: root.label
            color: Theme.textMuted
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontTinyPx
            font.weight: Theme.weightMedium
            font.letterSpacing: 0.8
        }

        Rectangle {
            id: field
            width: parent.width
            height: 32
            radius: Theme.radiusControl
            color: Theme.surface1
            border.color: root.dropdownOpen ? Theme.borderFocus : Theme.border
            border.width: 1

            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: Theme.spaceMD
                anchors.right: parent.right
                anchors.rightMargin: Theme.spaceMD
                text: root.currentLabel
                color: root.currentIndex >= 0 ? Theme.textPrimary : Theme.textMuted
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontBodyPx
                elide: Text.ElideRight
            }

            Icon {
                source: "icons/chevron-down.svg"
                color: Theme.textMuted
                size: 14
                anchors.right: parent.right
                anchors.rightMargin: Theme.spaceSM
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Popup {
            id: dropdown
            y: field.height + 4
            width: field.width
            padding: 4
            closePolicy: Popup.CloseOnPressOutside | Popup.CloseOnEscape
            // opened — свойство только для чтения: открываем через open()
            onOpened: root.dropdownOpen = true
            onClosed: root.dropdownOpen = false
            background: Rectangle {
                color: Theme.surface1
                border.color: Theme.borderStrong
                border.width: 1
                radius: Theme.radiusInner
            }

            ListView {
                anchors.fill: parent
                clip: true
                model: root.items.length
                currentIndex: root.currentIndex
                highlight: Rectangle {
                    color: Theme.surfaceActive
                    radius: Theme.radiusInner - 4
                }
                highlightFollowsCurrentItem: true

                delegate: Item {
                    id: item
                    width: parent.width
                    height: 30
                    required property int index

                    Rectangle {
                        anchors.fill: parent
                        color: root.currentIndex === item.index ? Theme.surfaceActive
                              : (item.hovered ? Theme.surfaceHover : "transparent")
                        radius: Theme.radiusInner - 4
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.spaceMD
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.spaceMD
                        text: (item.index >= 0 && item.index < root.items.length)
                              ? root.items[item.index].label : ""
                        color: root.currentIndex === item.index ? Theme.accentBright
                                                                   : Theme.textPrimary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: Theme.fontBodyPx
                        elide: Text.ElideRight
                    }

                    MouseArea {
                        id: itemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onEntered: item.hovered = true
                        onExited: item.hovered = false
                        onClicked: {
                            if (item.index < 0 || item.index >= root.items.length)
                                return
                            root.currentIndex = item.index
                            root.currentLabel = root.items[item.index].label
                            dropdown.close()
                            root.changed(item.index)
                        }
                    }

                    property bool hovered: false
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: root.dropdownOpen ? dropdown.close() : dropdown.open()
        }
    }
}