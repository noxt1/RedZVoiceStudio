import QtQuick
import QtQuick.Effects

/// Иконка из SVG-набора RedZ.
/// SVG нарисован белым; перекрашивается через MultiEffect.colorization.
Item {
    id: root

    property string source: ""
    property color color: "white"
    property real size: 24

    implicitWidth: size
    implicitHeight: size

    Image {
        id: img
        anchors.fill: parent
        // пути вида "icons/mic.svg" заданы от корня qml/, а сам компонент
        // лежит в qml/RedZ/ — поэтому относительный путь поднимаем на уровень выше
        source: (root.source === "" || root.source.charAt(0) === "/" || root.source.indexOf(":") >= 0)
                ? root.source
                : Qt.resolvedUrl("../" + root.source)
        sourceSize.width: root.size
        sourceSize.height: root.size
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: true
    }

    MultiEffect {
        anchors.fill: img
        source: img
        colorization: 1.0
        colorizationColor: root.color
    }
}