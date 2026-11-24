import QtQuick
import Auraloom 1.0

/// Всплывающее уведомление.
Item {
    id: root

    property string text: ""
    property string kind: "info"

    width: toastBg.implicitWidth + Theme.spaceXL
    height: toastBg.implicitHeight
    opacity: 0
    visible: opacity > 0.01

    function show(msg: string, messageKind: string) {
        root.text = msg
        root.kind = messageKind || "info"
        root.opacity = 1.0
        hideTimer.restart()
    }

    Rectangle {
        id: toastBg
        anchors.centerIn: parent
        implicitWidth: toastText.implicitWidth + Theme.spaceXL
        implicitHeight: 44
        radius: Theme.radiusPill
        color: Theme.surface2
        border.color: {
            if (root.kind === "ok") return Theme.success
            if (root.kind === "warn") return Theme.warning
            if (root.kind === "err") return Theme.danger
            return Theme.borderStrong
        }
        border.width: 1.5
        opacity: 0.97

        Text {
            id: toastText
            anchors.centerIn: parent
            text: root.text
            color: Theme.textPrimary
            font.family: Theme.fontFamilyText
            font.pixelSize: Theme.fontSmallPx
        }
    }

    Behavior on opacity {
        NumberAnimation { duration: Theme.motionBase; easing: Theme.eOutCubic }
    }

    Timer {
        id: hideTimer
        interval: 3200
        onTriggered: root.opacity = 0.0
    }
}