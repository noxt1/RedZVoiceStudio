import QtQuick
import QtQuick.Effects
import RedZ 1.0

/// Мягкое свечение позади кнопки/карточки.
/// Кладётся первым ребёнком элемента и растягивается по нему:
///     Glow { anchors.fill: parent; glowColor: Theme.accent }
Item {
    id: root

    property color glowColor: Theme.accent
    property real intensity: 0.55
    property int spread: 9
    property int cornerRadius: 12

    // Источник — тонкое кольцо по контуру: после размытия даёт мягкое
    // свечение вокруг кнопки, не заливая её содержимое.
    Rectangle {
        id: src
        anchors.fill: parent
        anchors.margins: -2
        radius: root.cornerRadius + 2
        color: "transparent"
        border.color: root.glowColor
        border.width: 7
        visible: false
        layer.enabled: true
    }

    MultiEffect {
        anchors.fill: src
        source: src
        blurEnabled: true
        blur: 1.0
        blurMax: 48
        opacity: root.intensity
    }
}
