import QtQuick
import RedZ 1.0

/// Кнопка primary: акцентный градиент, hover/pressed/disabled состояния.
Item {
    id: root

    property string text: ""
    property string iconSource: ""
    property color baseColor: Theme.accent
    property color textColor: Theme.textOnAccent
    property bool flat: false
    property bool highlighted: false
    property bool glow: true
    property int controlHeight: 42

    signal clicked()

    implicitWidth: contentRow.implicitWidth + Theme.spaceLG * 2
    implicitHeight: root.controlHeight

    Glow {
        anchors.fill: bg
        glowColor: root.baseColor
        intensity: root.highlighted ? 0.7 : 0.4
        spread: 8
        cornerRadius: Theme.radiusControl
        visible: root.glow && root.enabled && !root.flat
    }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: Theme.radiusControl
        color: {
            if (!root.enabled) return Theme.surface2
            if (root.flat) return "transparent"
            return root.highlighted ? Theme.accentBright : root.baseColor
        }
        border.color: root.flat ? (root.highlighted ? Theme.accent : Theme.borderStrong) : "transparent"
        border.width: root.flat ? 1.2 : 0
        opacity: root.enabled ? 1.0 : 0.55
        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
        Behavior on opacity { NumberAnimation { duration: Theme.motionFast } }
    }

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: Theme.spaceXS

        Icon {
            source: root.iconSource
            color: !root.enabled ? Theme.textMuted
                 : (root.flat ? (root.highlighted ? Theme.accentBright : Theme.accent) : root.textColor)
            size: 18
            visible: root.iconSource !== ""
        }

        Text {
            text: root.text
            color: !root.enabled ? Theme.textMuted
                 : (root.flat ? (root.highlighted ? Theme.accentBright : Theme.accent) : root.textColor)
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontBodyPx
            font.weight: Theme.weightMedium
            verticalAlignment: Text.AlignVCenter
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onEntered: root.highlighted = true
        onExited: root.highlighted = false
        onPressed: bg.scale = 0.97
        onReleased: bg.scale = 1.0
        onClicked: if (root.enabled) root.clicked()
    }

    states: [
        State {
            name: "pressed"
            when: bg.scale < 1.0
            PropertyChanges { target: bg; scale: 0.97 }
        }
    ]
}