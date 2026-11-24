import QtQuick
import Auraloom 1.0

/// Пошаговый прогресс (как в референсе):
/// Idle VAD → Idle Text → Idle Translate → Idle Voice → Ready Playback
Item {
    id: root

    property var steps: [
        { "label": "Idle", "sub": "VAD" },
        { "label": "Idle", "sub": "Text" },
        { "label": "Idle", "sub": "Translate" },
        { "label": "Idle", "sub": "Voice" },
        { "label": "Ready", "sub": "Playback" }
    ]
    property int activeStep: -1   // индекс текущего активного шага (-1 = все idle)
    property int spacing: 24

    implicitWidth: root.steps.length * 56 + (root.steps.length - 1) * root.spacing
    implicitHeight: 72

    Row {
        spacing: root.spacing
        anchors.centerIn: parent

        Repeater {
            model: root.steps
            delegate: Column {
                anchors.verticalCenter: parent.bottom

                Rectangle {
                    id: dot
                    width: 10
                    height: 10
                    radius: 5
                    color: {
                        if (root.activeStep >= index) return Theme.accent
                        return Theme.surface3
                    }
                    border.color: Theme.border
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 200 } }
                }

                Text {
                    text: modelData.label
                    color: root.activeStep >= index ? Theme.textPrimary : Theme.textMuted
                    font.family: Theme.fontFamilyText
                    font.pixelSize: 11
                    font.weight: Theme.weightMedium
                    horizontalAlignment: Text.AlignHCenter
                    anchors.top: dot.bottom
                    anchors.topMargin: 4
                }

                Text {
                    text: modelData.sub
                    color: Theme.textMuted
                    font.family: Theme.fontFamilyText
                    font.pixelSize: 9
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}