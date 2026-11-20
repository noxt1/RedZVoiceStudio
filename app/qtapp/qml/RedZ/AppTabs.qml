import QtQuick
import RedZ 1.0

/// Компоновка вкладок (segmented control).
Item {
    id: root

    property var tabs: [] // [{text, icon}]
    property int currentIndex: -1
    signal tabSelected(int index)

    implicitWidth: parent ? parent.width : 600
    implicitHeight: 48

    readonly property int activeTab: root.currentIndex !== -1 ? root.currentIndex : 0

    Row {
        anchors.fill: parent
        spacing: 4

        Repeater {
            model: root.tabs
            delegate: Item {
                property int index: modelData.index
                width: tabItem.implicitWidth + 24
                height: 48

                Rectangle {
                    id: tabItem
                    anchors.fill: parent
                    anchors.margins: 0
                    anchors.left: parent.left
                    anchors.right: parent.right
                    radius: 20
                    color: root.activeTab === modelData.index ? Theme.surfaceActive : "transparent"
                    border.color: root.activeTab === modelData.index ? Theme.borderFocus : "transparent"
                    border.width: 1.5
                    Behavior on color { ColorAnimation { duration: Theme.motionFast } }

                    Row {
                        anchors.centerIn: parent
                        spacing: Theme.spaceXS

                        Icon {
                            source: modelData.icon
                            color: root.activeTab === modelData.index ? Theme.accentBright : Theme.textSecondary
                            size: 16
                        }

                        Text {
                            text: modelData.text
                            color: root.activeTab === modelData.index ? Theme.textPrimary : Theme.textSecondary
                            font.family: Theme.fontFamilyText
                            font.pixelSize: Theme.fontBodyPx
                            font.weight: Theme.weightMedium
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        root.currentIndex = modelData.index
                        root.tabSelected(modelData.index)
                    }
                }
            }
        }
    }
}