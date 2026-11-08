// Geometric bot avatar: shape × colour with two “eyes”, deterministic from the bot's face dict.
import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property var face: ({ shape: "hexagon", color: "#7C5CFF" })
    property int size: 28
    property bool busy: false
    width: size; height: size

    readonly property color fill: (face && face.color) ? face.color : "#7C5CFF"
    readonly property string shapeName: (face && face.shape) || "hexagon"

    Item {
        id: body
        anchors.fill: parent
        opacity: root.busy ? 0.85 : 1
        Shape {
            width: 1; height: 1
            scale: root.size
            transformOrigin: Item.TopLeft
            antialiasing: true
            ShapePath {
                fillColor: root.fill
                strokeWidth: -1
                PathSvg {
                    path: {
                        switch (root.shapeName) {
                        case "hexagon": return "M.25 .02 H.75 L.98 .5 .75 .98 H.25 L.02 .5 Z"
                        case "triangle": return "M.5 .02 L.98 .94 H.02 Z"
                        case "circle": return "M.02 .5 A.48 .48 0 1 0 .98 .5 A.48 .48 0 1 0 .02 .5 Z"
                        case "teardrop": return "M.5 .02 C.9 .38 1.13 .9 .5 .98 C-.13 .9 .1 .38 .5 .02 Z"
                        case "cloud": return "M.2 .85 C-.1 .8 0 .35 .22 .38 C.18 -.08 .8 -.08 .82 .38 C1.1 .35 1.1 .85 .8 .85 Z"
                        case "blob": return "M.48 .03 C.8 -.03 1.1 .4 .9 .7 C.8 1.05 .3 1.05 .08 .75 C-.12 .4 .2 .12 .48 .03 Z"
                        case "pill": return "M.32 .18 H.68 A.3 .3 0 0 1 .98 .48 V.52 A.3 .3 0 0 1 .68 .82 H.32 A.3 .3 0 0 1 .02 .52 V.48 A.3 .3 0 0 1 .32 .18 Z"
                        default: return "M.14 .02 H.86 Q.98 .02 .98 .14 V.86 Q.98 .98 .86 .98 H.14 Q.02 .98 .02 .86 V.14 Q.02 .02 .14 .02 Z"
                        }
                    }
                }
            }
        }

        Rectangle {  // left eye
            width: Math.max(3, root.size * 0.14); height: Math.max(2, root.size * 0.08)
            radius: height / 2; color: "#fff"
            anchors { verticalCenter: parent.verticalCenter; horizontalCenter: parent.horizontalCenter
                      horizontalCenterOffset: -root.size * 0.16; verticalCenterOffset: root.size * (root.shapeName === "triangle" ? 0.12 : -0.02) }
        }
        Rectangle {  // right eye
            width: Math.max(3, root.size * 0.14); height: Math.max(2, root.size * 0.08)
            radius: height / 2; color: "#fff"
            anchors { verticalCenter: parent.verticalCenter; horizontalCenter: parent.horizontalCenter
                      horizontalCenterOffset: root.size * 0.16; verticalCenterOffset: root.size * (root.shapeName === "triangle" ? 0.12 : -0.02) }
        }
        SequentialAnimation on opacity {
            running: root.busy && Qt.styleHints.reduceMotion !== true
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.45; duration: 650; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.45; to: 1; duration: 650; easing.type: Easing.InOutSine }
        }
    }
}
