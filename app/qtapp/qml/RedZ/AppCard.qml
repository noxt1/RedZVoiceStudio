import QtQuick
import RedZ 1.0

/// Карточка — базовый контейнер с эффектом hover.
Item {
    id: root

    // свойства взаимодействия с родителем (width/height по детям)
    property alias contentItem: container.children
    property bool hovered: false
    readonly property real shadowBlur: 12
    readonly property real shadowOpacity: 0.5
    readonly property real radius: Theme.radiusCard

    implicitWidth: container.implicitWidth
    implicitHeight: container.implicitHeight

    // Фоновый контейнер карточки
    Rectangle {
        id: cardRect
        anchors.centerIn: parent
        width: container.implicitWidth + Theme.spaceMD * 2
        height: container.implicitHeight + Theme.spaceMD * 2
        radius: root.radius
        color: Theme.surface0
        border.color: root.hovered ? Theme.borderFocus : Theme.border
        border.width: root.hovered ? 1 : 0
        opacity: 0.85
        visible: !root.hovered

        Behavior on border.width { NumberAnimation { duration: Theme.motionFast; easing: Theme.eOutCubic } }
    }

    // Основной контейнер с контентом (сдвинут вниз для hover-эффекта)
    Item {
        id: container
        anchors.centerIn: parent
        anchors.topMargin: -Theme.spaceMD
        anchors.leftMargin: -Theme.spaceMD
        width: implicitWidth
        height: implicitHeight
        scale: root.hovered ? 1.02 : 1.0
        y: root.hovered ? -Theme.spaceXS : 0
        Behavior on scale { NumberAnimation { duration: Theme.motionFast; easing: Theme.eOutCubic } }
        Behavior on y { NumberAnimation { duration: Theme.motionFast; easing: Theme.eOutCubic } }

        Rectangle {
            anchors.fill: parent
            radius: root.radius
            color: Theme.surface0
            border.color: Theme.border
            border.width: 1
            opacity: 0.95
        }

        // Дети будут расположены здесь (внутренние пространство)
        // этот Rectangle — фоновая поверхность; мы можем сделать это просто Item с отступами через Layout.
        // Лучше: сделать в качестве контейнера для Children; мы уже использовали Item для container,
        // и children будут размещены внутри него.
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onEntered: root.hovered = true
        onExited: root.hovered = false
        onClicked: root.clicked()
    }

    signal clicked()
}