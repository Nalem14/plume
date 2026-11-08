// The side column: the app's kicker, the search (a name opens it, a sentence goes to Ornis), the library,
// favourites, videos, memories, people and places as cards, the albums (photos dragged onto one join it),
// those shared with the account, the trash, and at the foot the account and the settings (AccountBar).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: side
    readonly property var c: theme.c
    readonly property var counts: photos.counts
    signal settingsRequested()
    signal importRequested()
    signal newAlbum()
    color: c.chrome

    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    function setSearch(text) { search.text = text }

    component Section_: RowLayout {
        id: section
        property string text
        property bool adds: false
        signal add()
        Layout.fillWidth: true
        Layout.topMargin: 14
        Layout.bottomMargin: 4
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: 10
            text: section.text
            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
            color: side.c.muted
        }
        OButton {
            visible: section.adds
            kind: "quiet"; implicitWidth: 28; height_: 28; iconSize: 16
            iconName: "plus"; tip: app.t.album_new
            onClicked: section.add()
        }
    }

    component Row_: AbstractButton {
        id: row
        property string target
        property string iconName
        property int count: 0
        property var album: null
        property bool pending: false
        readonly property bool active: photos.view === target
        Layout.fillWidth: true
        implicitHeight: 34
        hoverEnabled: true
        Accessible.name: text
        onClicked: { search.text = ""; win.openView(target) }
        background: Rectangle {
            radius: 7
            color: row.active ? side.c.card : (row.hovered || drop.containsDrag ? side.c.hover : "transparent")
            border.width: drop.containsDrag ? 1 : 0
            border.color: side.c.accent
            Band {
                visible: row.active
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                radius: 1.5
                color: side.c.famMedia
            }
        }
        contentItem: RowLayout {
            spacing: 9
            Item {
                Layout.leftMargin: 6
                implicitWidth: 22; implicitHeight: 22
                Rectangle {
                    anchors.fill: parent
                    visible: row.album !== null && row.album.cover > 0
                    radius: 5; clip: true
                    color: side.c.line
                    Thumb {
                        anchors.fill: parent
                        address: row.album && row.album.cover ? "t/256/" + row.album.cover + "/" + row.album.etag : ""
                        sourceSize: Qt.size(64, 64)
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }
                }
                Icon {
                    anchors.centerIn: parent
                    visible: row.album === null || !row.album.cover
                    name: row.iconName; size: 18; color: row.active ? side.c.famMedia : side.c.muted
                }
            }
            Text {
                Layout.fillWidth: true
                text: row.text
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                font.weight: row.active ? Font.DemiBold : Font.Normal
                color: side.c.text
            }
            Rectangle {
                visible: row.pending
                implicitWidth: 6; implicitHeight: 6; radius: 3
                color: side.c.saffron
                ToolTip.visible: pendingHover.hovered
                ToolTip.text: app.t.pending_one
                HoverHandler { id: pendingHover }
            }
            Text {
                Layout.rightMargin: 10
                text: row.count || ""
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: side.c.muted
            }
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            enabled: row.album !== null && row.album.owner === (app.profile.user || "")
            onTapped: albumRowMenu.openFor(row.album, row)
        }
        // photos dragged from the grid onto an album join it
        DropArea {
            id: drop
            anchors.fill: parent
            enabled: row.album !== null
            keys: ["application/x-orneos-photos"]
            onDropped: drag => {
                const ids = JSON.parse(drag.getDataAsString("application/x-orneos-photos") || "[]")
                photos.addToAlbum(row.album.id, ids)
                drag.accept(Qt.CopyAction)
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 12
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 8
            spacing: 10
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                text: app.t.app_name
                elide: Text.ElideRight
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: side.c.famMedia
            }
            OButton {
                kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "import"; tip: app.t.import_action + "  (Ctrl+I)"
                onClicked: side.importRequested()
            }
        }

        OTextField {
            id: search
            Layout.fillWidth: true
            Layout.bottomMargin: 12
            iconName: ornis.busy ? "ornis" : "search"
            placeholderText: app.t.search_placeholder
            Accessible.description: app.t.search_hint
            onAccepted: win.runSearch(text)
            onCleared: win.runSearch("")
            ToolTip.visible: activeFocus && text === ""
            ToolTip.delay: 600
            ToolTip.text: app.t.search_hint
        }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentHeight: lower.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: lower
                width: parent.width
                spacing: 2

                GridLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 4
                    columns: 2
                    rowSpacing: 8; columnSpacing: 8
                    Repeater {
                        model: [
                            { view: "library", icon: "image", text: app.t.view_library, count: side.counts.library, tint: side.c.famMedia },
                            { view: "favorites", icon: "star", text: app.t.view_favorites, count: side.counts.favorites, tint: side.c.saffronInk },
                            { view: "videos", icon: "video", text: app.t.view_videos, count: side.counts.videos, tint: side.c.famCommunicate },
                            { view: "memories", icon: "history", text: app.t.view_memories, count: side.counts.memories, tint: side.c.famSpace },
                            { view: "people", icon: "people", text: app.t.view_people, count: side.counts.people, tint: side.c.famDocs },
                            { view: "places", icon: "location", text: app.t.view_places, count: side.counts.places, tint: side.c.famOrganize }
                        ]
                        SmartCard {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            tint: modelData.tint; iconName: modelData.icon; text: modelData.text
                            count: modelData.count === undefined ? "" : String(modelData.count)
                            selected: photos.view === modelData.view
                            onClicked: { search.text = ""; win.openView(modelData.view) }
                        }
                    }
                }

                Section_ { text: app.t.albums; adds: true; onAdd: side.newAlbum() }
                Row_ {
                    visible: (photos.lists.albums || []).length === 0
                    target: "albums"; iconName: "album"; text: app.t.albums_all
                }
                Repeater {
                    model: photos.lists.albums || []
                    Row_ {
                        required property var modelData
                        target: "albums:" + modelData.id
                        iconName: "album"
                        text: modelData.name
                        count: modelData.count
                        album: modelData
                        pending: modelData.pending
                    }
                }
                Section_ { text: app.t.shared_albums; visible: (photos.lists.shared || []).length > 0 }
                Repeater {
                    model: photos.lists.shared || []
                    Row_ {
                        required property var modelData
                        target: "albums:" + modelData.id
                        iconName: "people"
                        text: modelData.name
                        count: modelData.count
                        album: modelData
                    }
                }

                Rectangle { Layout.fillWidth: true; Layout.topMargin: 14; Layout.bottomMargin: 6; implicitHeight: 1; color: side.c.hairline }
                Row_ { target: "archive"; iconName: "archive"; text: app.t.view_archive; count: side.counts.archive || 0 }
                Row_ { target: "trash"; iconName: "trash"; text: app.t.view_trash; count: side.counts.trash || 0 }
            }
        }

        // many photos on their way to an album: counted up until the cloud has them all
        Repeater {
            model: photos.online ? photos.tasks : []
            Rectangle {
                required property var modelData
                Layout.fillWidth: true
                Layout.topMargin: 6
                implicitHeight: 44; radius: 7
                color: side.c.card
                border.width: 1; border.color: side.c.line
                ColumnLayout {
                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                    anchors.topMargin: 7; anchors.bottomMargin: 8
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        Icon { name: "album"; size: 14; color: side.c.famMedia }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.text
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: side.c.text
                        }
                        Text {
                            text: modelData.done + " / " + modelData.total
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: side.c.muted
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 4; radius: 2
                        color: side.c.hairline
                        Rectangle {
                            height: parent.height; radius: 2
                            width: parent.width * Math.max(0.03, modelData.done / Math.max(1, modelData.total))
                            color: side.c.famMedia
                            Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                        }
                    }
                }
            }
        }

        // offline, with changes waiting: said here, nowhere else
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            visible: !photos.online || photos.uploads > 0
            spacing: 8
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 30; radius: 7
                color: side.c.saffronTint
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                    spacing: 7
                    Icon { name: photos.online ? "export" : "offline"; size: 14; color: side.c.saffronInk }
                    Text {
                        Layout.fillWidth: true
                        text: !photos.online ? (photos.pending ? app.plural("offline_pending", photos.pending) : app.t.offline)
                                             : app.plural("uploading", photos.uploads)
                        elide: Text.ElideRight
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: side.c.saffronInk
                    }
                }
            }
        }

        // the foot of the column, over what scrolls above it
        Item {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
            implicitHeight: account.implicitHeight
            z: 2
            Rectangle { anchors.fill: parent; anchors.topMargin: -6; anchors.leftMargin: -10; anchors.rightMargin: -10; color: side.c.chrome }
            AccountBar {
                id: account
                anchors.fill: parent
                name: app.profile.name || ""
                email: app.profile.email || ""
                initials: app.profile.initials || ""
                onSettingsRequested: side.settingsRequested()
                OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/memories/") }
                OMenuItem { text: app.t.import_action; iconName: "import"; onTriggered: side.importRequested() }
                OMenuItem { text: app.t.reconnect; iconName: "refresh"; onTriggered: app.openConnect() }
            }
        }
    }

    OMenu {
        id: albumRowMenu
        property var album: null
        readonly property bool mine: !!album && !(photos.lists.shared || []).some(a => a.id === album.id)
        function openFor(a, item) {
            album = a
            const p = item.mapToItem(side, item.width - 40, item.height)
            x = p.x; y = p.y
            open()
        }
        OMenuItem { visible: albumRowMenu.mine; text: app.t.album_share; iconName: "share"; onTriggered: shareDialog.openFor(albumRowMenu.album.id) }
        OMenuItem { visible: albumRowMenu.mine; text: app.t.album_rename; iconName: "edit"; onTriggered: nameDialog.ask("album-rename", albumRowMenu.album.id, albumRowMenu.album.name, []) }
        OMenuItem { visible: !albumRowMenu.mine; text: app.t.leave_album; iconName: "close"; danger: true; onTriggered: photos.leaveAlbum(albumRowMenu.album.id) }
        OMenuItem {
            visible: albumRowMenu.mine
            text: app.t.album_delete; iconName: "trash"; danger: true
            onTriggered: {
                const a = albumRowMenu.album
                albumDelete.ask(app.t.album_delete_title.replace("%1", a.name), app.t.album_delete_text,
                                [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.album_delete, kind: "danger" }],
                                () => photos.deleteAlbum(a.id))
            }
        }
    }
}
