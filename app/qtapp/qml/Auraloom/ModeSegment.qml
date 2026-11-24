import QtQuick
import Auraloom 1.0

/// Режим работы моделей: Fast / Balanced / Quality / Manual.
///
/// `value` — код режима (fast/balanced/quality/manual), берётся из
/// `appState.mode`; клик вызывает `appState.setMode(code)`.
Item {
    id: root

    property string value: appState.mode
    property bool vertical: false
    property bool compact: false

    implicitHeight: vertical ? layout.height : 44
    implicitWidth: vertical ? 260 : layout.width

    readonly property var modes: [
        { "code": "fast",     "label": "Быстро",   "icon": "icons/bolt.svg" },
        { "code": "balanced", "label": "Баланс",   "icon": "icons/compare.svg" },
        { "code": "quality",  "label": "Качество", "icon": "icons/sparkles.svg" },
        { "code": "manual",   "label": "Вручную",  "icon": "icons/layers.svg" }
    ]

    Grid {
        id: layout
        width: root.vertical ? root.width : implicitWidth
        columns: root.vertical ? 1 : 4
        rowSpacing: 6
        columnSpacing: 6

        Repeater {
            model: root.modes
            delegate: Item {
                width: root.vertical ? root.width
                                     : (root.compact ? 60 : 72)
                height: root.vertical ? 34 : 44

                readonly property bool active: root.value === modelData.code

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusControl
                    gradient: active ? Theme.gradAccent : null
                    color: active ? "transparent" : "#10163A"
                    border.width: 1
                    border.color: active ? Theme.accent : Theme.border
                    opacity: active ? 1.0 : (hover.containsMouse ? 0.85 : 0.65)
                }

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        source: modelData.icon
                        color: active ? "#FFFFFF" : Theme.textSecondary
                        size: 15
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        visible: root.vertical || !root.compact
                        color: active ? "#FFFFFF" : Theme.textSecondary
                        font.family: Theme.fontFamilyText
                        font.pixelSize: 11
                        font.weight: active ? Theme.weightSemiBold : Theme.weightRegular
                    }
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: appState.setMode(modelData.code)
                }
            }
        }
    }
}
