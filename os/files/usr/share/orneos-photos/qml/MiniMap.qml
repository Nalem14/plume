// Where the photo was taken, in the viewer's details: a small map with a pin. A click opens the places on the
// app's map, there.
import QtQuick
import QtLocation
import QtPositioning
import "components"

Item {
    id: mini
    property real lat
    property real lon
    property color ground                  // the panel behind: the map's corners are cut in it
    signal opened()
    implicitHeight: 150

    OsmPlugin { id: osm }
    Rectangle {
        anchors.fill: parent
        radius: 10
        color: Qt.rgba(1, 1, 1, 0.08)
        clip: true
        Map {
            id: map
            anchors.fill: parent
            plugin: osm
            zoomLevel: 13
            center: QtPositioning.coordinate(mini.lat, mini.lon)
            copyrightsVisible: false
            Component.onCompleted: {
                const types = map.supportedMapTypes
                map.activeMapType = types.find(t => t.style === MapType.CustomMap) || types[types.length - 1]
            }
            MapQuickItem {
                coordinate: QtPositioning.coordinate(mini.lat, mini.lon)
                anchorPoint: Qt.point(9, 9)
                sourceItem: Rectangle {
                    width: 18; height: 18; radius: 9
                    color: theme.c.famMedia
                    border.width: 3; border.color: "white"
                }
            }
        }
        Corners { anchors.fill: parent; radius: 10; color: mini.ground }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: mini.opened() }
    }
}
