import QtQuick
import Auraloom 1.0

/// Карточка состояния движка в сайдбаре (низ): точка, статус, GPU,
/// VRAM и мини-график загрузки.
Item {
    id: root

    implicitWidth: 212
    implicitHeight: 108

    readonly property bool ready: appState.engineState === "READY"
    readonly property real load: appState.vramTotal > 0
                                  ? Math.min(1, appState.vramUsed / appState.vramTotal)
                                  : 0

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusInner
        color: "#0C1233"
        border.width: 1
        border.color: root.ready ? Theme.successDeep : Theme.border

        Column {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 6

            Row {
                spacing: 7

                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.ready ? Theme.success
                         : (appState.engineState === "LOADING" ? Theme.warning : Theme.textMuted)

                    SequentialAnimation on opacity {
                        running: appState.engineState === "LOADING"
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.3; duration: 600 }
                        NumberAnimation { to: 1.0; duration: 600 }
                    }
                }

                Text {
                    text: root.ready ? "Движок: готов"
                         : (appState.engineState === "LOADING" ? "Загрузка моделей…"
                            : (appState.engineState === "ERROR" && liveEngine.error !== ""
                               ? "Ошибка" : "Остановлен"))
                    color: Theme.textPrimary
                    font.family: Theme.fontFamilyText
                    font.pixelSize: 12
                    font.weight: Theme.weightMedium
                }
            }

            Text {
                width: parent.width
                text: appState.gpuName
                      ? appState.gpuName
                        + (appState.vramTotal > 0
                           ? " · " + (appState.vramUsed / 1024).toFixed(1) + " GB" : "")
                      : "GPU не определён"
                elide: Text.ElideRight
                color: Theme.textMuted
                font.family: Theme.fontFamilyMono
                font.pixelSize: 10
            }

            // мини-график загрузки VRAM
            Item {
                width: parent.width
                height: 26

                Row {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    spacing: 3

                    Repeater {
                        model: 16
                        delegate: Rectangle {
                            width: 5
                            radius: 2
                            height: {
                                var t = index / 15
                                var filled = t <= root.load
                                return filled ? 6 + 18 * t : 5
                            }
                            anchors.bottom: parent.bottom
                            gradient: (index / 15) <= root.load ? Theme.gradAccent : null
                            color: (index / 15) <= root.load ? "transparent" : Theme.surface2
                            Behavior on height { NumberAnimation { duration: 180 } }
                        }
                    }
                }
            }
        }
    }
}
