import QtQuick
import RedZ 1.0

/// Переключатель (switch) — премиум-стиль, скруглённый трек.
Item {
    id: root

    property bool checked: false
    property color onColor: Theme.accent
    property color offColor: Theme.surface3
    property string label: ""

    signal toggled(bool checked)

    implicitWidth: root.label === "" ? 52 : labelText.implicitWidth + 60
    implicitHeight: 30

    Row {
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.spaceSM

        Rectangle {
            id: track
            width: 52
            height: 30
            radius: 15
            color: root.checked ? root.onColor : root.offColor
            border.color: root.checked ? root.onColor : Theme.borderStrong
            border.width: 1
            Behavior on color { ColorAnimation { duration: Theme.motionBase } }

            Rectangle {
                id: handle
                width: 24
                height: 24
                radius: 12
                color: Theme.textPrimary
                anchors.verticalCenter: parent.verticalCenter
                x: root.checked ? parent.width - width - 3 : 3
                Behavior on x { NumberAnimation { duration: Theme.motionBase; easing: Theme.eOutCubic } }
            }
        }

        Text {
            id: labelText
            text: root.label
            color: root.checked ? Theme.textPrimary : Theme.textSecondary
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontBodyPx
            verticalAlignment: Text.AlignVCenter
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: {
            root.checked = !root.checked
            root.toggled(root.checked)
        }
    }
}