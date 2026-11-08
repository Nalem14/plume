// The places on a map: the photos taken with a position, grouped by Memories on a grid that follows the zoom,
// each group drawn as its newest photo with its count. A group opens its photos (the « map:<bounds> » view);
// the wheel, a pinch, a drag or the buttons move the map. OpenStreetMap's tiles stay in the cache (shown again
// offline); the plugin asks nothing else (no providers repository).
import QtQuick
import QtQuick.Controls
import QtLocation
import QtPositioning
import "components"

Item {
    id: pane
    readonly property var c: theme.c
    property var clusters: []
    property string asked: ""
    property int grid: 0                 // the zoom Memories grouped the clusters shown with
    property bool loaded: false

    function cellOf(z) { return 180 / Math.pow(2, z) }
    // the part of the map shown, snapped on Memories' grid and one cell beyond the edges: a little panning
    // asks nothing new
    function request() {
        if (!visible || width < 10) return
        const map = view.map
        const z = Math.max(1, Math.min(18, Math.round(map.zoomLevel)))
        const g = cellOf(z)
        const r = map.visibleRegion.boundingGeoRectangle()
        if (!r.isValid) return
        let minLon = r.topLeft.longitude, maxLon = r.bottomRight.longitude
        if (minLon > maxLon || z <= 2) { minLon = -180; maxLon = 180 }      // across the date line, or the world
        const b = [Math.max(-90, (Math.floor(r.bottomRight.latitude / g) - 1) * g),
                   Math.min(90, (Math.ceil(r.topLeft.latitude / g) + 1) * g),
                   Math.max(-180, (Math.floor(minLon / g) - 1) * g),
                   Math.min(180, (Math.ceil(maxLon / g) + 1) * g)]
        const bounds = b.map(v => v.toFixed(6)).join(",")
        asked = bounds + "|" + z
        photos.loadMap(bounds, z)
    }
    // the square of the grid a cluster stands for: its photos open as a view
    function open(cluster) {
        const g = cellOf(grid)
        const lat = Math.floor(cluster.lat / g) * g, lon = Math.floor(cluster.lon / g) * g
        win.openView("map:" + [lat, lat + g, lon, lon + g].map(v => v.toFixed(6)).join(","))
    }
    function goTo(lat, lon, zoom) {
        view.map.center = QtPositioning.coordinate(lat, lon)
        view.map.zoomLevel = zoom
    }
    function remember() {
        const at = view.map.center
        app.setPref("map_view", { lat: at.latitude, lon: at.longitude, zoom: view.map.zoomLevel })
    }

    onVisibleChanged: if (visible) settle.restart()
    Component.onCompleted: {
        const at = app.prefs.map_view || {}
        if (at.zoom) {
            view.map.center = QtPositioning.coordinate(at.lat, at.lon)
            view.map.zoomLevel = at.zoom
        } else {
            photos.loadMapStart()
        }
        settle.restart()
    }

    Connections {
        target: photos
        function onMapReady(bounds, zoom, rows) {
            if (bounds + "|" + zoom !== pane.asked) return
            pane.grid = zoom
            pane.clusters = rows
            pane.loaded = true
        }
        function onMapStartReady(lat, lon) {
            if ((app.prefs.map_view || {}).zoom) return
            view.map.center = QtPositioning.coordinate(lat, lon)
            view.map.zoomLevel = 6
        }
    }
    // asked once the map stops moving
    Timer { id: settle; interval: 250; onTriggered: { pane.request(); pane.remember() } }

    OsmPlugin { id: osm }

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: Qt.tint(pane.c.line, Qt.alpha(pane.c.famMedia, 0.10))
        clip: true

        MapView {
            id: view
            anchors.fill: parent
            map.plugin: osm
            map.zoomLevel: 4
            map.center: QtPositioning.coordinate(46.6, 2.4)
            map.copyrightsVisible: true
            Component.onCompleted: {
                const types = view.map.supportedMapTypes
                const custom = types.find(t => t.style === MapType.CustomMap)
                view.map.activeMapType = custom || types[types.length - 1]
            }
            Connections {
                target: view.map
                function onCenterChanged() { settle.restart() }
                function onZoomLevelChanged() { settle.restart() }
            }

            MapItemView {
                parent: view.map
                model: pane.clusters
                delegate: MapQuickItem {
                    id: spot
                    required property var modelData
                    readonly property int side: 44 + Math.min(22, Math.round(Math.log(modelData.count) * 4))
                    coordinate: QtPositioning.coordinate(modelData.lat, modelData.lon)
                    anchorPoint: Qt.point(side / 2, side / 2)
                    z: modelData.count
                    sourceItem: Item {
                        width: spot.side; height: spot.side
                        Accessible.role: Accessible.Button
                        Accessible.name: app.plural("count_photos", spot.modelData.count)
                        Rectangle {
                            anchors.fill: parent
                            radius: 12
                            color: "white"
                            scale: tap.pressed ? 0.94 : hover.hovered ? 1.06 : 1
                            Behavior on scale { NumberAnimation { duration: 110 } }
                            Rectangle {
                                anchors.fill: parent; anchors.margins: 3
                                radius: 9; clip: true
                                color: pane.c.line
                                Thumb {
                                    anchors.fill: parent
                                    address: spot.modelData.cover ? "t/256/" + spot.modelData.cover + "/" + spot.modelData.etag : ""
                                    sourceSize: Qt.size(128, 128)
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                }
                                Corners { anchors.fill: parent; radius: 9; color: "white" }
                            }
                        }
                        Rectangle {
                            visible: spot.modelData.count > 1
                            anchors.right: parent.right; anchors.top: parent.top
                            anchors.rightMargin: -7; anchors.topMargin: -7
                            height: 20; radius: 10
                            width: Math.max(20, countText.implicitWidth + 12)
                            color: pane.c.famMedia
                            border.width: 1.5; border.color: "white"
                            Text {
                                id: countText
                                anchors.centerIn: parent
                                text: spot.modelData.count > 999 ? Math.round(spot.modelData.count / 1000) + " k" : spot.modelData.count
                                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.DemiBold
                                color: "white"
                            }
                        }
                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { id: tap; onTapped: pane.open(spot.modelData) }
                    }
                }
            }
        }

        Corners { anchors.fill: parent; radius: 12; color: pane.c.bg }

        // nothing with a position in this part of the map
        Rectangle {
            visible: pane.loaded && pane.clusters.length === 0
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top; anchors.topMargin: 16
            width: Math.min(parent.width - 32, emptyText.implicitWidth + 28); height: 36; radius: 18
            color: pane.c.overlay
            border.width: 1; border.color: pane.c.overlayLine
            Text {
                id: emptyText
                anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter
                text: app.t.map_empty
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: pane.c.text
            }
        }

        Column {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
            spacing: 6
            OButton {
                implicitWidth: 34; iconName: "zoomIn"; tip: app.t.zoom_in
                enabled: view.map.zoomLevel < view.map.maximumZoomLevel
                onClicked: view.map.zoomLevel = Math.min(view.map.maximumZoomLevel, Math.round(view.map.zoomLevel) + 1)
            }
            OButton {
                implicitWidth: 34; iconName: "zoomOut"; tip: app.t.zoom_out
                enabled: view.map.zoomLevel > 1
                onClicked: view.map.zoomLevel = Math.max(1, Math.round(view.map.zoomLevel) - 1)
            }
        }
    }
}
