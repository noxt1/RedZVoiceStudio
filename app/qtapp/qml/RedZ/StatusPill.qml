import QtQuick
import RedZ 1.0

/// Статусная пилюля: точка + текст. Состояния: idle / loading / ready / error / warn.
Item {
    id: root

    property string text: ""
    property string pillState: "idle"
    property int pillHeight: 26

    readonly property color dotColor: {
        if (root.pillState === "ready") return Theme.success
        if (root.pillState === "loading") return Theme.warning
        if (root.pillState === "error") return Theme.danger
        if (root.pillState === "warn") return Theme.warning
        return Theme.textMuted
    }

    readonly property color bgColor: {
        if (root.pillState === "ready") return Theme.successDeep
        if (root.pillState === "loading") return Theme.warningDeep
        if (root.pillState === "error") return Theme.dangerDeep
        if (root.pillState === "warn") return Theme.warningDeep
        return Theme.surface1
    }

    implicitWidth: dot.implicitWidth + textItem.implicitWidth + Theme.spaceMD * 2 + Theme.spaceXS
    implicitHeight: root.pillHeight

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusPill
        color: root.bgColor
        opacity: 0.9
        border.color: root.dotColor
        border.width: 1
    }

    Rectangle {
        id: dot
        width: 8
        height: 8
        radius: 4
        color: root.dotColor
        anchors.left: parent.left
        anchors.leftMargin: Theme.spaceMD
        anchors.verticalCenter: parent.verticalCenter

        SequentialAnimation on opacity {
            running: root.pillState === "loading"
            loops: Animation.Infinite
            NumberAnimation { to: 0.25; duration: 500 }
            NumberAnimation { to: 1.0; duration: 500 }
        }
    }

    Text {
        id: textItem
        text: root.text
        color: Theme.textPrimary
        font.family: Theme.fontFamilyText
        font.pixelSize: Theme.fontSmallPx
        font.weight: Theme.weightMedium
        anchors.left: dot.right
        anchors.leftMargin: Theme.spaceXS
        anchors.verticalCenter: parent.verticalCenter
    }
}