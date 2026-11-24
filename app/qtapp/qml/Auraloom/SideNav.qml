import QtQuick
import QtQuick.Controls
import Auraloom 1.0

/// Навигационная панель (Sidebar) с прокруткой и активной подсветкой.
Item {
    id: root

    property var items: []  // [{icon, label, badge?, index}]
    property int currentIndex: -1
    signal itemActivated(int index)

    implicitWidth: 220
    implicitHeight: parent ? parent.height : 600

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: flick.width
        contentHeight: column.height + Theme.spaceLG * 2
        clip: true

        Column {
            id: column
            x: Theme.spaceLG
            y: Theme.spaceLG
            width: flick.width - Theme.spaceLG * 2
            spacing: Theme.spaceMD

            Repeater {
                model: root.items
                delegate: SideNavEntry {
                    label: modelData.label
                    iconSource: modelData.icon
                    badge: modelData.badge !== undefined ? modelData.badge : 0
                    active: root.currentIndex === index
                    onClicked: root.itemActivated(index)
                }
            }
        }

        ScrollBar.vertical: ScrollBar { width: 8; active: true }
    }
}