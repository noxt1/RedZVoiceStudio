import QtQuick
import QtQuick.Controls
import RedZ 1.0

/// Выпадающий список (кастомный, тёмный).
Item {
    id: root

    property var model: []          // string[] или [{label, value}]
    property string currentText: ""
    property int currentIndex: -1
    property string label: ""
    property int fieldHeight: 38

    signal activated(int index)

    implicitWidth: 240
    implicitHeight: root.label === "" ? root.fieldHeight : root.fieldHeight + 26

    function itemLabel(i) {
        var it = root.model[i]
        if (typeof it === "string") return it
        return it.label !== undefined ? it.label : String(it)
    }
    function itemValue(i) {
        var it = root.model[i]
        if (typeof it === "string") return it
        return it.value !== undefined ? it.value : it
    }

    Column {
        anchors.fill: parent
        spacing: Theme.spaceXXS

        Text {
            text: root.label
            color: Theme.textMuted
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontTinyPx
            font.weight: Theme.weightMedium
            visible: root.label !== ""
            font.letterSpacing: 0.4
        }

        Item {
            id: boxRow
            width: parent.width
            height: root.fieldHeight

            Rectangle {
                id: box
                anchors.fill: parent
                radius: Theme.radiusControl
                color: Theme.surface1
                border.color: popup.opened ? Theme.borderFocus : Theme.border
                border.width: popup.opened ? 1.5 : 1
                Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }

                Text {
                    id: boxText
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spaceMD
                    anchors.right: chevron.left
                    anchors.rightMargin: Theme.spaceSM
                    text: root.currentText
                    color: root.currentIndex >= 0 ? Theme.textPrimary : Theme.textMuted
                    font.family: Theme.fontFamilyText
                    font.pixelSize: Theme.fontBodyPx
                    elide: Text.ElideRight
                }

                Icon {
                    id: chevron
                    source: "icons/chevron-down.svg"
                    color: Theme.textMuted
                    size: 16
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.spaceSM
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: popup.opened ? popup.close() : popup.open()
            }

            Popup {
                id: popup
                y: boxRow.height - 2
                width: boxRow.width
                height: Math.min(count * 34 + 12, 280)
                padding: 6
                closePolicy: Popup.CloseOnPressOutside | Popup.CloseOnEscape
                background: Rectangle {
                    color: Theme.surface1
                    border.color: Theme.borderStrong
                    border.width: 1
                    radius: Theme.radiusInner
                }

                ListView {
                    anchors.fill: parent
                    clip: true
                    model: root.model.length
                    currentIndex: root.currentIndex
                    highlight: Rectangle {
                        color: Theme.surfaceActive
                        radius: Theme.radiusInner - 4
                    }
                    highlightFollowsCurrentItem: true

                    delegate: Item {
                        id: item
                        width: ListView.view.width
                        height: 34
                        required property int index

                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.radiusInner - 4
                            color: item.hovered ? Theme.surfaceActive
                                  : (root.currentIndex === item.index ? Theme.surface2
                                                                     : "transparent")
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.spaceSM
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.spaceSM
                            text: root.itemLabel(item.index)
                            color: root.currentIndex === item.index ? Theme.accentBright
                                                                    : Theme.textPrimary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontBodyPx
                            elide: Text.ElideRight
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onEntered: item.hovered = true
                            onExited: item.hovered = false
                            onClicked: {
                                root.currentIndex = item.index
                                root.currentText = root.itemLabel(item.index)
                                popup.close()
                                root.activated(item.index)
                            }
                        }

                        property bool hovered: false
                    }
                }
            }
        }
    }

    readonly property int count: root.model.length
}