// Orneos line icons, the AI symbol and the Ornis mascot (docs/ORNIS-MASCOT.md).
// "ornis" (or "sparkle") is the AI symbol, two stars: every way into the AI. While `hovered` (its button
// passes it; a pointer over the icon itself also counts), the mascot takes its place.
// "ornis-mascot" is the mascot itself: the author of answers; `thinking` shows its working pose.
import QtQuick
import QtQuick.Shapes
import "icons.js" as Icons

Item {
    id: icon
    readonly property bool isAi: name === "ornis" || name === "sparkle"
    readonly property bool isMascot: name === "ornis-mascot"
    property bool thinking: false
    property bool hovered: false
    property string name
    property real size: 20
    property color color: theme.c.text

    readonly property bool bird: isMascot || (isAi && (hovered || pointer.hovered))
    readonly property bool motion: Qt.styleHints.reduceMotion !== true
    // The AI symbol from design/ornis-ai/ai.svg (24 grid): the large star, then the small star and the dot, in saffron.
    readonly property string bigStar: "M10.2 4.7C12.63 11.27 12.63 11.27 19.2 13.7C12.63 16.13 12.63 16.13 10.2 22.7C7.77 16.13 7.77 16.13 1.2 13.7C7.77 11.27 7.77 11.27 10.2 4.7Z"
    readonly property string smallStar: "M18.6 1.5C19.6 4.2 19.6 4.2 22.3 5.2C19.6 6.2 19.6 6.2 18.6 8.9C17.6 6.2 17.6 6.2 14.9 5.2C17.6 4.2 17.6 4.2 18.6 1.5ZM20.7 11.2a.9 .9 0 1 0 1.8 0a.9 .9 0 1 0-1.8 0Z"

    implicitWidth: size
    implicitHeight: size

    HoverHandler { id: pointer; enabled: icon.isAi }

    Image {
        anchors.fill: parent
        visible: icon.isAi || icon.isMascot
        source: visible ? (icon.thinking ? "../../../orneos/mascot/thinking-v1.png" : "../../../orneos/mascot/icon-v1.png") : ""
        fillMode: Image.PreserveAspectFit
        smooth: true
        opacity: icon.bird ? 1 : 0
        scale: icon.bird ? (icon.isAi ? 1.15 : 1) : 0.6
        rotation: icon.bird ? 0 : -12
        Behavior on opacity { enabled: icon.motion && icon.isAi; NumberAnimation { duration: 150 } }
        Behavior on scale { enabled: icon.motion && icon.isAi; NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
        Behavior on rotation { enabled: icon.motion && icon.isAi; NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
    }

    Shape {
        anchors.fill: parent
        visible: icon.isAi
        preferredRendererType: Shape.CurveRenderer
        opacity: icon.bird ? 0 : 1
        scale: icon.bird ? 0.6 : 1
        rotation: icon.bird ? 20 : 0
        Behavior on opacity { enabled: icon.motion; NumberAnimation { duration: 150 } }
        Behavior on scale { enabled: icon.motion; NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
        Behavior on rotation { enabled: icon.motion; NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
        ShapePath {
            fillColor: icon.color; strokeColor: icon.color; strokeWidth: 0.9
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(icon.size / 24, icon.size / 24)
            PathSvg { path: icon.bigStar }
        }
        ShapePath {
            fillColor: theme.c.saffron; strokeColor: theme.c.saffron; strokeWidth: 0.7
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(icon.size / 24, icon.size / 24)
            PathSvg { path: icon.smallStar }
        }
    }

    Shape {
        anchors.fill: parent
        visible: !icon.isAi && !icon.isMascot
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: icon.color
            strokeWidth: Math.max(1.25, 1.5 * icon.size / 24) * 24 / icon.size
            fillColor: "transparent"
            capStyle: ShapePath.SquareCap
            joinStyle: ShapePath.MiterJoin
            scale: Qt.size(icon.size / 24, icon.size / 24)
            PathSvg { path: icon.isAi || icon.isMascot ? "" : (Icons.paths[icon.name] || "") }
        }
    }
}
