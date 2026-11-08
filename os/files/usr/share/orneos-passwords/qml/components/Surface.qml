// A card set on the page (docs/REFONTE-ORNIS.md): the surfaces that matter, the letter being read, the day,
// a group of tasks, sit a little above the page on one soft shadow (token elev), with a hairline of light
// on their edge in dark. Never glass in a window: the translucent stays on the desktop.
import QtQuick
import QtQuick.Effects

Item {
    id: surface
    readonly property var c: theme.c
    property real radius: 12
    property color color: c.card
    property bool raised: true
    property alias gradient: card.gradient
    default property alias content: inner.data

    RectangularShadow {
        visible: surface.raised
        anchors.fill: card
        radius: card.radius
        blur: 26; spread: -8; offset.y: 10
        color: surface.c.elev
    }
    RectangularShadow {
        visible: surface.raised
        anchors.fill: card
        radius: card.radius
        blur: 3; offset.y: 1
        color: Qt.alpha(surface.c.elev, 0.45)
    }
    Rectangle {
        id: card
        anchors.fill: parent
        radius: surface.radius
        color: surface.color
        border.width: theme.dark ? 1 : 0
        border.color: surface.c.elevEdge
    }
    Item {
        id: inner
        anchors.fill: parent
    }
}
