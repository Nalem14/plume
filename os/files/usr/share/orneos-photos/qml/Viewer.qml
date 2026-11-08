// One photo over the whole window, on a dark ground whatever the theme: the thumbnail first, then the large
// preview. ← / → move through the view, Échap closes, a double clic or the wheel zooms, I shows the details
// (date, camera, place, people, albums), « . » makes it a favourite, E opens the editor, F full screen,
// R / Maj+R turn it, Ctrl+C copies it, S plays the view as a slideshow.
// A video plays here from a copy kept on the computer.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: viewer
    readonly property var c: theme.c
    readonly property color ground: "#070B12"
    property bool opened: false
    property int fileid: 0
    property var photo: ({})
    property var info: ({})
    property bool infoOpen: app.prefs.info === true
    property bool full: false
    property string videoUri: ""
    property bool playing: false         // the slideshow
    readonly property string kind: photos.view.split(":")[0]
    readonly property bool canCover: (kind === "albums" && photos.heading.own === true) || kind === "recognize"
    readonly property int index: photos.indexOf(fileid)
    readonly property bool hasPrev: index > 0
    readonly property bool hasNext: index >= 0 && index < photos.order.length - 1
    signal editWanted(int fileid)
    signal albumWanted(var ids, var item)
    signal fullScreenWanted(bool on)

    function open(id) { opened = true; show(id); forceActiveFocus() }
    function show(id) {
        fileid = id
        photo = photos.photo(id)
        info = ({})
        videoUri = ""
        stage.zoom = 1
        if (!photo.fileid) { close(); return }
        photos.loadInfo(id)
    }
    function close() {
        playing = false
        if (full) toggleFull()
        opened = false
        videoUri = ""
        win.forceActiveFocus()
    }
    function step(delta) {
        const i = index + delta
        if (i >= 0 && i < photos.order.length) show(photos.order[i])
    }
    function toggleFull() { full = !full; fullScreenWanted(full) }
    function slideshow(on) {
        playing = on
        if (on && !full) toggleFull()
        else if (!on && full) toggleFull()
    }
    function turn(deg) { if (!photo.video && !photo.outside) photos.rotate([fileid], deg) }
    Timer {
        interval: 4500; repeat: true
        running: viewer.playing && viewer.opened && !viewer.photo.video
        onTriggered: viewer.show(photos.order[viewer.hasNext ? viewer.index + 1 : 0])
    }

    visible: opened
    z: 10

    Connections {
        target: photos
        function onInfoReady(id, data) { if (id === viewer.fileid) viewer.info = data }
        function onVideoReady(id, uri) { if (id === viewer.fileid) viewer.videoUri = uri }
        // a change elsewhere (a sync, a favourite): the shown photo follows, or the viewer moves on if it left
        function onViewChanged() {
            if (!viewer.opened) return
            const fresh = photos.photo(viewer.fileid)
            if (fresh.fileid) viewer.photo = fresh
            else if (photos.order.length) viewer.show(photos.order[Math.min(Math.max(0, viewer.index), photos.order.length - 1)])
            else viewer.close()
        }
    }

    Keys.onPressed: event => {
        if (viewer.playing && event.key !== Qt.Key_Left && event.key !== Qt.Key_Right) {
            viewer.slideshow(false); event.accepted = true; return
        }
        const ctrl = (event.modifiers & Qt.ControlModifier) !== 0
        if (event.key === Qt.Key_C && ctrl) { photos.copyImage(viewer.fileid); event.accepted = true; return }
        if (event.key === Qt.Key_R && !ctrl) { viewer.turn(event.modifiers & Qt.ShiftModifier ? 90 : 270); event.accepted = true; return }
        if (event.key === Qt.Key_S && !ctrl) { viewer.slideshow(true); event.accepted = true; return }
        if (event.key === Qt.Key_Escape) { if (stage.zoom > 1) stage.zoom = 1; else viewer.close(); event.accepted = true }
        else if (event.key === Qt.Key_Left) { viewer.step(-1); event.accepted = true }
        else if (event.key === Qt.Key_Right) { viewer.step(1); event.accepted = true }
        else if (event.key === Qt.Key_I) { viewer.infoOpen = !viewer.infoOpen; app.setPref("info", viewer.infoOpen); event.accepted = true }
        else if (event.key === Qt.Key_Period) { photos.toggleFavorite([viewer.fileid]); event.accepted = true }
        else if (event.key === Qt.Key_E && !viewer.photo.video && !viewer.photo.outside) { viewer.editWanted(viewer.fileid); event.accepted = true }
        else if (event.key === Qt.Key_F) { viewer.toggleFull(); event.accepted = true }
        else if (event.key === Qt.Key_Space && viewer.photo.video && player.item) { player.item.toggle(); event.accepted = true }
        else if ((event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) && !viewer.photo.outside) {
            win.remove([viewer.fileid]); event.accepted = true
        }
    }

    Rectangle { anchors.fill: parent; color: viewer.ground }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // the bar: back, the day and the name, then the actions
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                Layout.leftMargin: 10; Layout.rightMargin: 10
                visible: (!viewer.full || barHover.hovered) && !viewer.playing
                spacing: 4
                ViewerButton { iconName: "chevronLeft"; tip: app.t.back + "  (" + app.t.key_escape + ")"; onClicked: viewer.close() }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: viewer.info.when || viewer.photo.day || ""
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                        color: "white"; elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (viewer.info.place ? viewer.info.place.split(",")[0] + " · " : "") + (viewer.photo.name || "")
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: Qt.rgba(1, 1, 1, 0.65); elide: Text.ElideRight
                    }
                }
                ViewerButton {
                    visible: !viewer.photo.outside
                    iconName: "star"; on: viewer.photo.fav === true
                    tip: (viewer.photo.fav ? app.t.unfavorite : app.t.favorite) + "  (.)"
                    onClicked: photos.toggleFavorite([viewer.fileid])
                }
                ViewerButton {
                    visible: !viewer.photo.video && !viewer.photo.outside
                    iconName: "edit"; tip: app.t.edit + "  (E)"
                    onClicked: viewer.editWanted(viewer.fileid)
                }
                ViewerButton { id: albumBtn; visible: !viewer.photo.outside; iconName: "album"; tip: app.t.add_to_album; onClicked: viewer.albumWanted([viewer.fileid], albumBtn) }
                ViewerButton { visible: !viewer.photo.outside; iconName: "link"; tip: app.t.share_link; onClicked: photos.shareLink([viewer.fileid]) }
                ViewerButton { iconName: "info"; on: viewer.infoOpen; tip: app.t.details + "  (I)"; onClicked: { viewer.infoOpen = !viewer.infoOpen; app.setPref("info", viewer.infoOpen) } }
                ViewerButton {
                    id: moreBtn
                    iconName: "more"; tip: app.t.more
                    onClicked: moreMenu.open()
                    OMenu {
                        id: moreMenu
                        y: parent.height + 6
                        x: parent.width - width
                        OMenuItem { text: app.t.slideshow + "  (S)"; iconName: "play"; onTriggered: viewer.slideshow(true) }
                        OMenuItem { text: app.t.copy_image + "  (Ctrl+C)"; iconName: "copy"; onTriggered: photos.copyImage(viewer.fileid) }
                        OMenuItem { text: app.t.download; iconName: "download"; onTriggered: photos.download([viewer.fileid]) }
                        OMenuItem { visible: !viewer.photo.outside && !viewer.photo.video; text: app.t.rotate_left + "  (R)"; iconName: "rotate"; onTriggered: viewer.turn(270) }
                        OMenuItem { visible: !viewer.photo.outside && !viewer.photo.video; text: app.t.rotate_right + "  (Maj+R)"; iconName: "rotate"; onTriggered: viewer.turn(90) }
                        OMenuItem { visible: !viewer.photo.outside; text: app.t.change_date; iconName: "calendar"; onTriggered: dateDialog.openFor([viewer.fileid], viewer.info.taken || "") }
                        OMenuItem { visible: viewer.canCover; text: app.t.set_cover; iconName: "image"; onTriggered: photos.setCover(viewer.fileid) }
                        OMenuItem {
                            visible: !viewer.photo.outside
                            text: viewer.photo.archived ? app.t.unarchive_action : app.t.archive_action; iconName: "archive"
                            onTriggered: photos.archive([viewer.fileid], !viewer.photo.archived)
                        }
                        OMenuItem { text: viewer.full ? app.t.exit_full_screen : app.t.full_screen; iconName: "expand"; onTriggered: viewer.toggleFull() }
                        OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/f/" + viewer.fileid) }
                        OMenuItem {
                            visible: !viewer.photo.outside
                            text: app.t.delete_action; iconName: "trash"; danger: true
                            onTriggered: win.remove([viewer.fileid])
                        }
                    }
                }
            }
            HoverHandler { id: barHover }

            // the photo
            Item {
                id: stage
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                property real zoom: 1
                property real ox: 0
                property real oy: 0
                onZoomChanged: if (zoom <= 1) { ox = 0; oy = 0 }
                // a rotation on its way is shown at once: the picture turned, fitted on its new sides
                readonly property bool sideways: (viewer.photo.turn || 0) % 180 !== 0
                readonly property real fit: Math.min(width / Math.max(1, (sideways ? viewer.photo.h : viewer.photo.w) || 1),
                                                     height / Math.max(1, (sideways ? viewer.photo.w : viewer.photo.h) || 1))
                readonly property real pw: (viewer.photo.w || width) * fit
                readonly property real ph: (viewer.photo.h || height) * fit

                Item {
                    id: picture
                    width: stage.pw; height: stage.ph
                    x: (stage.width - width) / 2 + stage.ox
                    y: (stage.height - height) / 2 + stage.oy
                    scale: stage.zoom
                    rotation: viewer.photo.turn || 0
                    Behavior on rotation { RotationAnimation { duration: 180; direction: RotationAnimation.Shortest } }
                    Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                    visible: viewer.videoUri === ""
                    Thumb {
                        id: low
                        anchors.fill: parent
                        address: viewer.fileid ? "t/512/" + viewer.fileid + "/" + (viewer.photo.etag || "") : ""
                        sourceSize: Qt.size(512, 512)
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                    }
                    Thumb {
                        id: high
                        anchors.fill: parent
                        address: viewer.fileid ? "p/2048/" + viewer.fileid + "/" + (viewer.photo.etag || "") : ""
                        sourceSize: Qt.size(2048, 2048)
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        opacity: status === Image.Ready ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 180 } }
                    }
                    // a video: its poster, and play
                    Rectangle {
                        visible: viewer.photo.video === true
                        anchors.centerIn: parent
                        width: 76; height: 76; radius: 38
                        color: Qt.rgba(0, 0, 0, 0.5)
                        border.width: 2; border.color: "white"
                        Icon { anchors.centerIn: parent; anchors.horizontalCenterOffset: 3; name: "play"; size: 30; color: "white" }
                        TapHandler { onTapped: photos.loadVideo(viewer.fileid) }
                        Accessible.role: Accessible.Button
                        Accessible.name: app.t.play
                    }
                }
                Loader {
                    id: player
                    anchors.fill: parent
                    active: viewer.videoUri !== ""
                    source: "VideoPlayer.qml"
                    onLoaded: item.play(viewer.videoUri)
                    onStatusChanged: if (status === Loader.Error) { photos.openExternal(viewer.videoUri); viewer.videoUri = "" }
                }

                DragHandler {
                    target: null
                    enabled: stage.zoom > 1
                    property real sx: 0
                    property real sy: 0
                    onActiveChanged: if (active) { sx = stage.ox; sy = stage.oy }
                    onTranslationChanged: { stage.ox = sx + translation.x; stage.oy = sy + translation.y }
                }
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    onTapped: if (viewer.playing) viewer.slideshow(false)
                    onDoubleTapped: stage.zoom = stage.zoom > 1 ? 1 : 2.5
                }
                WheelHandler {
                    onWheel: event => {
                        if (viewer.photo.video) return
                        const z = stage.zoom * (event.angleDelta.y > 0 ? 1.15 : 1 / 1.15)
                        stage.zoom = Math.max(1, Math.min(6, z))
                    }
                }
                PinchHandler {
                    target: null
                    property real start: 1
                    onActiveChanged: if (active) start = stage.zoom
                    onActiveScaleChanged: stage.zoom = Math.max(1, Math.min(6, start * activeScale))
                }

                // previous and next, on the sides
                ViewerButton {
                    anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter
                    visible: viewer.hasPrev && stage.zoom === 1 && !viewer.playing
                    large: true; iconName: "chevronLeft"; tip: app.t.previous + "  (←)"
                    onClicked: viewer.step(-1)
                }
                ViewerButton {
                    anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                    visible: viewer.hasNext && stage.zoom === 1 && !viewer.playing
                    large: true; iconName: "chevronRight"; tip: app.t.next + "  (→)"
                    onClicked: viewer.step(1)
                }
                Rectangle {
                    visible: viewer.photo.pending === true
                    anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 18
                    height: 26; radius: 13; width: pendRow.implicitWidth + 20
                    color: Qt.rgba(0, 0, 0, 0.55)
                    Row {
                        id: pendRow
                        anchors.centerIn: parent
                        spacing: 6
                        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5; color: viewer.c.saffron }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: app.t.pending_one; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: "white" }
                    }
                }
            }
        }

        // the details
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 320
            visible: viewer.infoOpen
            color: theme.dark ? viewer.c.card : "#0F1828"
            Flickable {
                anchors.fill: parent
                anchors.margins: 18
                contentHeight: details.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ColumnLayout {
                    id: details
                    width: parent.width
                    spacing: 14
                    Text {
                        text: app.t.details
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                        color: "#7EB8CC"
                    }
                    InfoLine {
                        icon: "calendar"; main: viewer.info.when || viewer.photo.day || ""
                        sub: viewer.photo.outside ? "" : app.t.date_edit
                        link: !viewer.photo.outside
                        onLinkActivated: dateDialog.openFor([viewer.fileid], viewer.info.taken || "")
                    }
                    // a description, written into the photo (the web, the phone and other apps read it)
                    TextArea {
                        id: describe
                        visible: !viewer.photo.outside || text !== ""
                        readOnly: viewer.photo.outside === true
                        Layout.fillWidth: true
                        property string saved: viewer.info.description || ""
                        text: saved
                        placeholderText: app.t.description_placeholder
                        placeholderTextColor: Qt.rgba(1, 1, 1, 0.4)
                        wrapMode: TextEdit.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: "white"
                        selectionColor: "#7EB8CC"
                        background: Rectangle {
                            radius: 8
                            color: describe.activeFocus ? Qt.rgba(1, 1, 1, 0.10) : describe.hovered ? Qt.rgba(1, 1, 1, 0.06) : "transparent"
                            border.width: describe.activeFocus ? 1 : 0; border.color: "#7EB8CC"
                        }
                        Accessible.name: app.t.description
                        function commit() {
                            if (text.trim() !== saved.trim()) {
                                photos.setDescription(viewer.fileid, text)
                                viewer.info = Object.assign({}, viewer.info, { description: text.trim() })
                            }
                        }
                        onActiveFocusChanged: if (!activeFocus) commit()
                        Keys.onPressed: event => {
                            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                commit(); viewer.forceActiveFocus(); event.accepted = true
                            } else if (event.key === Qt.Key_Escape) {
                                text = saved; viewer.forceActiveFocus(); event.accepted = true
                            }
                        }
                    }
                    InfoLine { icon: "image"; main: viewer.info.name || viewer.photo.name || ""; sub: viewer.info.dims || ""; selectable: true }
                    InfoLine { visible: (viewer.info.camera || "") !== ""; icon: "image"; main: viewer.info.camera || ""; sub: [viewer.info.lens || "", viewer.info.exposure || ""].filter(x => x).join("\n") }
                    InfoLine {
                        visible: (viewer.info.place || "") !== "" || viewer.info.hasGps === true
                        icon: "location"
                        main: viewer.info.place || (viewer.info.lat || 0).toFixed(4) + ", " + (viewer.info.lon || 0).toFixed(4)
                        sub: viewer.info.hasGps ? app.t.open_map : ""
                        link: viewer.info.hasGps === true
                        onLinkActivated: app.openMap(viewer.info.lat, viewer.info.lon)
                    }
                    // the map of where it was taken: a click shows the places there
                    Loader {
                        Layout.fillWidth: true
                        active: viewer.info.hasGps === true
                        visible: active
                        source: "MiniMap.qml"
                        onLoaded: {
                            item.ground = Qt.binding(() => theme.dark ? viewer.c.card : "#0F1828")
                            item.lat = Qt.binding(() => viewer.info.lat || 0)
                            item.lon = Qt.binding(() => viewer.info.lon || 0)
                            item.opened.connect(() => {
                                app.setPref("map_view", { lat: viewer.info.lat, lon: viewer.info.lon, zoom: 13 })
                                app.setPref("places_mode", "map")
                                if (map.item) map.item.goTo(viewer.info.lat, viewer.info.lon, 13)
                                viewer.close()
                                win.openView("places")
                            })
                        }
                    }
                    InfoLine { visible: (viewer.info.owner || "") !== ""; icon: "user"; main: app.t.shared_by.replace("%1", viewer.info.owner || ""); sub: "" }
                    ColumnLayout {
                        visible: (viewer.info.people || []).length > 0
                        Layout.fillWidth: true
                        spacing: 6
                        Text { text: app.t.view_people; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: Qt.rgba(1, 1, 1, 0.6) }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            Repeater {
                                model: viewer.info.people || []
                                InfoChip {
                                    id: personChip
                                    required property var modelData
                                    text: modelData.name && !/^\d+$/.test(modelData.name) ? modelData.name : app.t.person_unnamed
                                    glyph: "user"
                                    onClicked: { viewer.close(); win.openView("recognize:" + modelData.id) }
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: { chipMenu.y = personChip.height + 4; chipMenu.open() } }
                                    OMenu {
                                        id: chipMenu
                                        OMenuItem { text: app.t.open; iconName: "user"; onTriggered: personChip.clicked() }
                                        OMenuItem {
                                            visible: !viewer.photo.outside
                                            text: app.t.not_this_person; iconName: "close"
                                            onTriggered: {
                                                photos.notThisPerson(personChip.modelData.id, [viewer.fileid])
                                                viewer.info = Object.assign({}, viewer.info,
                                                    { people: (viewer.info.people || []).filter(p => p.id !== personChip.modelData.id) })
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        visible: (viewer.info.albums || []).length > 0
                        Layout.fillWidth: true
                        spacing: 6
                        Text { text: app.t.albums; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: Qt.rgba(1, 1, 1, 0.6) }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            Repeater {
                                model: viewer.info.albums || []
                                InfoChip {
                                    required property var modelData
                                    text: modelData.name; glyph: "album"
                                    onClicked: { viewer.close(); win.openView("albums:" + modelData.id) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    component ViewerButton: AbstractButton {
        id: vb
        property string iconName
        property string tip
        property bool on: false
        property bool large: false
        implicitWidth: large ? 44 : 38; implicitHeight: large ? 44 : 38
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: tip
        ToolTip.visible: hovered && tip !== ""
        ToolTip.delay: 500
        ToolTip.text: tip
        background: Rectangle {
            radius: vb.large ? 22 : 8
            color: vb.large ? Qt.rgba(0, 0, 0, vb.hovered ? 0.6 : 0.4) : vb.hovered ? Qt.rgba(1, 1, 1, 0.12) : "transparent"
            border.width: vb.visualFocus ? 2 : 0; border.color: theme.c.saffron
        }
        contentItem: Item {
            Icon { anchors.centerIn: parent; name: vb.iconName; size: vb.large ? 22 : 19; color: vb.on ? "#F0A202" : "white"; hovered: vb.hovered }
        }
    }
    component InfoLine: RowLayout {
        id: line
        property string icon
        property string main
        property string sub
        property bool link: false
        property bool selectable: false
        signal linkActivated()
        Layout.fillWidth: true
        spacing: 12
        Icon { Layout.alignment: Qt.AlignTop; Layout.topMargin: 1; name: line.icon; size: 17; color: Qt.rgba(1, 1, 1, 0.55) }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            TextEdit {
                Layout.fillWidth: true
                text: line.main
                readOnly: true; selectByMouse: true
                wrapMode: TextEdit.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: "white"
                selectionColor: "#7EB8CC"
            }
            Text {
                visible: line.sub !== ""
                Layout.fillWidth: true
                text: line.sub
                wrapMode: Text.Wrap
                font.family: line.link ? "Schibsted Grotesk" : "JetBrains Mono"; font.pixelSize: 12
                font.underline: line.link && subHover.hovered
                color: line.link ? "#7EB8CC" : Qt.rgba(1, 1, 1, 0.65)
                HoverHandler { id: subHover; enabled: line.link; cursorShape: Qt.PointingHandCursor }
                TapHandler { enabled: line.link; onTapped: line.linkActivated() }
            }
        }
    }
    component InfoChip: AbstractButton {
        id: chip
        property string glyph
        implicitHeight: 28
        implicitWidth: chipRow.implicitWidth + 20
        hoverEnabled: true
        background: Rectangle { radius: 14; color: chip.hovered ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.08) }
        contentItem: Item {
            Row {
                id: chipRow
                anchors.centerIn: parent
                spacing: 6
                Icon { anchors.verticalCenter: parent.verticalCenter; name: chip.glyph; size: 13; color: "#7EB8CC" }
                Text { anchors.verticalCenter: parent.verticalCenter; text: chip.text; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: "white" }
            }
        }
    }
}
