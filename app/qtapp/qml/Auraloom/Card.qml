import QtQuick
import Auraloom 1.0

/// Карточка: стеклянная поверхность на неоновом фоне, как на референсе.
/// Дети кладутся внутрь с отступом `padding`.
Item {
    id: root

    default property alias content: holder.data

    property int padding: 20
    property int cornerRadius: Theme.radiusCard
    property color topColor: Theme.cardTop
    property color bottomColor: Theme.cardBottom
    property color borderColor: Theme.border
    property real borderWidth: 1

    Rectangle {
        anchors.fill: parent
        radius: root.cornerRadius
        gradient: Gradient {
            GradientStop { position: 0.0; color: root.topColor }
            GradientStop { position: 1.0; color: root.bottomColor }
        }
        border.color: root.borderColor
        border.width: root.borderWidth
    }

    Item {
        id: holder
        anchors.fill: parent
        anchors.margins: root.padding
    }
}
