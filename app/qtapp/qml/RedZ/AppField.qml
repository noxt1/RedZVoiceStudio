import QtQuick
import RedZ 1.0

/// Текстовое поле с меткой и фокусной рамкой.
Item {
    id: root

    property string label: ""
    property string placeholderText: ""
    property string text: ""
    property bool readOnly: false
    property int fieldHeight: 38

    signal textEdited(string text)
    signal accepted()

    implicitWidth: 240
    implicitHeight: root.label === "" ? root.fieldHeight : root.fieldHeight + 26

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

        Rectangle {
            id: field
            width: parent.width
            height: root.fieldHeight
            radius: Theme.radiusControl
            color: Theme.surface1
            border.color: input.activeFocus ? Theme.borderFocus : Theme.border
            border.width: input.activeFocus ? 1.5 : 1
            Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }

            TextInput {
                id: input
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: Theme.spaceMD
                anchors.right: parent.right
                anchors.rightMargin: Theme.spaceMD
                text: root.text
                color: Theme.textPrimary
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontBodyPx
                readOnly: root.readOnly
                selectByMouse: true
                clip: true
                onTextChanged: root.textEdited(input.text)
                onAccepted: root.accepted()
                Keys.onEscapePressed: input.focus = false
            }

            // подсказка (своя, TextInput её не умеет)
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: Theme.spaceMD
                anchors.right: parent.right
                anchors.rightMargin: Theme.spaceMD
                text: root.placeholderText
                color: Theme.textMuted
                font.family: Theme.fontFamilyText
                font.pixelSize: Theme.fontBodyPx
                visible: input.text === "" && root.placeholderText !== ""
                elide: Text.ElideRight
            }
        }
    }

    function setFocus() { input.forceActiveFocus() }
}