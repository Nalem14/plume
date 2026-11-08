// SPDX-License-Identifier: GPL-2.0-or-later
// The AI icon, everywhere: the two stars of Ornis (docs/ORNIS-MASCOT.md), drawn from the site's sprite.
import QtQuick
import QtQuick.Shapes
import "ornis.js" as Ornis

Item {
    id: stars
    property color color: "black"
    implicitWidth: 16
    implicitHeight: 16
    Shape {
        width: 24; height: 24
        anchors.centerIn: parent
        scale: Math.min(stars.width, stars.height) / 24
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: stars.color
            strokeColor: stars.color
            strokeWidth: 0.9
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M10.2 4.7C12.63 11.27 12.63 11.27 19.2 13.7C12.63 16.13 12.63 16.13 10.2 22.7C7.77 16.13 7.77 16.13 1.2 13.7C7.77 11.27 7.77 11.27 10.2 4.7Z" }
        }
        ShapePath {
            fillColor: Ornis.t.brand.safran
            strokeColor: Ornis.t.brand.safran
            strokeWidth: 0.7
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: "M18.6 1.5C19.6 4.2 19.6 4.2 22.3 5.2C19.6 6.2 19.6 6.2 18.6 8.9C17.6 6.2 17.6 6.2 14.9 5.2C17.6 4.2 17.6 4.2 18.6 1.5ZM20.7 11.2a.9 .9 0 1 0 1.8 0a.9 .9 0 1 0-1.8 0Z" }
        }
    }
}
