// Rounds a picture without a shader (they cannot draw without a GPU, and `clip` cuts square): the area outside
// the rounded rectangle (a circle when the radius is half the side) painted in the colour behind it.
import QtQuick
import QtQuick.Shapes

Shape {
    id: corners
    property real radius: 12
    property color color: theme.c.bg
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
        fillRule: ShapePath.OddEvenFill
        fillColor: corners.color
        strokeWidth: -1
        PathRectangle { x: -1; y: -1; width: corners.width + 2; height: corners.height + 2 }
        PathRectangle { x: 0; y: 0; width: corners.width; height: corners.height; radius: corners.radius }
    }
}
