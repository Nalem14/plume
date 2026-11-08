// The head of the view (Hero, in the media family's colour): what the view is, its figures, then its own
// actions — years, months or every photo, cities or the map for the places and the size of the thumbnails for the library; share, rename and
// delete for an album; name and merge for a person; titles by Ornis for the memories. A search shows what
// Ornis understood, as chips.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: head
    readonly property var c: theme.c
    readonly property var h: photos.heading
    readonly property string kind: h.kind || photos.view
    signal shareAlbum()
    signal renameAlbum()
    signal deleteAlbum()
    signal renamePerson()
    signal mergePerson()
    signal importRequested()
    spacing: 10

    component Segment: AbstractButton {
        id: seg
        property bool on
        implicitHeight: 30
        implicitWidth: label.implicitWidth + 24
        hoverEnabled: true
        Accessible.name: text
        background: Rectangle {
            radius: 6
            color: seg.on ? head.c.card : seg.hovered ? Qt.alpha(head.c.card, 0.6) : "transparent"
            border.width: seg.on ? 1 : 0; border.color: head.c.line
            Rectangle { anchors.fill: parent; anchors.margins: -3; radius: 8; color: "transparent"; border.width: 2; border.color: head.c.saffron; visible: seg.visualFocus }
        }
        contentItem: Text {
            id: label
            text: seg.text
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: seg.on ? Font.DemiBold : Font.Normal
            color: seg.on ? head.c.text : head.c.muted
        }
    }

    Hero {
        Layout.fillWidth: true
        tint: c.famMedia
        kicker: head.kind === "albums" ? (h.own === false ? app.t.kicker_shared_album.replace("%1", h.owner || "") : app.t.kicker_album)
              : head.kind === "recognize" ? app.t.kicker_person
              : head.kind === "places" ? app.t.kicker_place
              : head.kind === "map" ? app.t.kicker_map
              : head.kind === "tags" ? app.t.kicker_theme
              : head.kind === "memory" ? app.t.kicker_memory
              : head.kind === "search" ? (photos.search.ornis ? app.t.kicker_search_ornis : app.t.kicker_search)
              : h.title === app.t.app_name ? ""          // « Photothèque » once, not as kicker and title
              : app.t.app_name
        title: h.title || ""
        meta: h.meta || ""
        offline: !photos.online
        offlineText: photos.pending ? app.plural("offline_pending", photos.pending) : app.t.offline
        leading: HeadArt { covers: win.width >= 1100 ? head.h.covers || [] : [] }
        // the view's first picture, fading into the card behind the actions
        backdrop: Item {
            anchors.fill: parent
            visible: (head.h.covers || []).length > 0 && !(head.h.covers[0].round)
            Thumb {
                id: wash
                anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
                width: parent.width * 0.46
                address: parent.visible ? head.h.covers[0].address : ""
                sourceSize: Qt.size(512, 512)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                opacity: status === Image.Ready ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 260 } }
            }
            Rectangle {
                anchors.fill: wash
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: head.c.card }
                    GradientStop { position: 0.45; color: Qt.alpha(head.c.card, 0.82) }
                    GradientStop { position: 1; color: Qt.alpha(head.c.card, 0.55) }
                }
            }
            Corners { anchors.fill: parent; radius: 12; color: head.c.bg }
        }

        // the library: by years, by months, every photo
        Rectangle {
            visible: photos.view === "library"
            implicitWidth: modes.implicitWidth + 6; implicitHeight: 36; radius: 8
            color: Qt.alpha(head.c.text, theme.dark ? 0.08 : 0.05)
            Row {
                id: modes
                anchors.centerIn: parent
                spacing: 2
                Segment { text: app.t.mode_years; on: photos.mode === "years"; onClicked: photos.setMode("years") }
                Segment { text: app.t.mode_months; on: photos.mode === "months"; onClicked: photos.setMode("months") }
                Segment { text: app.t.mode_all; on: photos.mode === "all"; onClicked: photos.setMode("all") }
            }
        }
        // the places: as cities, or on the map
        Rectangle {
            visible: photos.view === "places"
            implicitWidth: placeModes.implicitWidth + 6; implicitHeight: 36; radius: 8
            color: Qt.alpha(head.c.text, theme.dark ? 0.08 : 0.05)
            Row {
                id: placeModes
                anchors.centerIn: parent
                spacing: 2
                Segment { text: app.t.places_cities; on: !win.onMap; onClicked: app.setPref("places_mode", "cities") }
                Segment { text: app.t.places_map; on: win.onMap; onClicked: app.setPref("places_mode", "map") }
            }
        }
        // the albums: newest, by name, the fullest first
        Rectangle {
            visible: photos.view === "albums"
            implicitWidth: sorts.implicitWidth + 6; implicitHeight: 36; radius: 8
            color: Qt.alpha(head.c.text, theme.dark ? 0.08 : 0.05)
            Accessible.name: app.t.sort_albums
            Row {
                id: sorts
                anchors.centerIn: parent
                spacing: 2
                readonly property string order: app.prefs.album_sort || "recent"
                Segment { text: app.t.sort_recent; on: sorts.order === "recent"; onClicked: photos.setAlbumSort("recent") }
                Segment { text: app.t.sort_name; on: sorts.order === "name"; onClicked: photos.setAlbumSort("name") }
                Segment { text: app.t.sort_size; on: sorts.order === "size"; onClicked: photos.setAlbumSort("size") }
            }
        }
        // the people: the small unnamed groups wait behind this
        OButton {
            visible: photos.view === "people" && ((h.hidden || 0) > 0 || h.allPeople === true)
            kind: "quiet"; iconName: "people"
            text: h.allPeople ? app.t.people_show_less : app.plural("people_show_all", h.hidden || 0)
            onClicked: photos.setShowAllPeople(!h.allPeople)
        }
        // an album someone shares with me
        OButton {
            visible: head.kind === "albums" && h.own === false
            kind: "quiet"; iconName: "close"; text: app.t.leave_album
            onClicked: photos.leaveAlbum(h.ref)
        }
        OButton {
            visible: grid.visible && win.width >= 1100
            kind: "quiet"; implicitWidth: 34; iconName: "zoomOut"; tip: app.t.zoom_out + "  (Ctrl+−)"
            enabled: photos.zoom > 0
            onClicked: photos.setZoom(photos.zoom - 1)
        }
        OButton {
            visible: grid.visible && win.width >= 1100
            kind: "quiet"; implicitWidth: 34; iconName: "zoomIn"; tip: app.t.zoom_in + "  (Ctrl++)"
            enabled: photos.zoom < 2
            onClicked: photos.setZoom(photos.zoom + 1)
        }
        OButton {
            visible: photos.view === "library"
            kind: "primary"; iconName: "import"; text: app.t.import_action
            onClicked: head.importRequested()
        }
        // an album of one's own
        OButton {
            visible: head.kind === "albums" && h.own === true
            iconName: "share"; text: app.t.album_share
            onClicked: head.shareAlbum()
        }
        OButton {
            visible: head.kind === "albums" && h.own === true
            kind: "quiet"; implicitWidth: 34; iconName: "more"; tip: app.t.more
            onClicked: albumMore.open()
            OMenu {
                id: albumMore
                y: parent.height + 6
                x: parent.width - width
                OMenuItem { text: app.t.album_rename; iconName: "edit"; onTriggered: head.renameAlbum() }
                OMenuItem { text: app.t.album_delete; iconName: "trash"; danger: true; onTriggered: head.deleteAlbum() }
            }
        }
        // a person
        OButton {
            visible: head.kind === "recognize"
            iconName: "edit"; text: h.named ? app.t.person_rename : app.t.person_name
            onClicked: head.renamePerson()
        }
        OButton {
            visible: head.kind === "recognize" && (photos.lists.people || []).length > 1
            kind: "quiet"; iconName: "people"; text: app.t.person_merge
            onClicked: head.mergePerson()
        }
        // the memories: Ornis gives them titles
        OButton {
            visible: photos.view === "memories" && (photos.lists.memories || []).some(m => m.kind === "event")
            kind: "accent"; iconName: "ornis"; text: ornis.titling ? app.t.ornis_titling : app.t.ornis_titles
            enabled: !ornis.titling
            onClicked: ornis.titleMemories()
        }
        OButton {
            visible: head.kind === "search"
            kind: "quiet"; implicitWidth: 34; iconName: "close"; tip: app.t.search_close
            onClicked: { sidebar.setSearch(""); win.openView("library") }
        }
    }

    // what the search kept: a person, a place, a theme, dates…
    Flow {
        Layout.fillWidth: true
        visible: head.kind === "search" && (photos.search.chips || []).length > 0
        spacing: 6
        Text {
            height: 26; verticalAlignment: Text.AlignVCenter
            text: photos.search.ornis ? app.t.search_understood : app.t.search_filters
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: head.c.muted
        }
        Repeater {
            model: photos.search.chips || []
            Rectangle {
                required property var modelData
                height: 26; radius: 13
                width: chipRow.implicitWidth + 20
                color: head.c.card
                border.width: 1; border.color: head.c.line
                Row {
                    id: chipRow
                    anchors.centerIn: parent
                    spacing: 6
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        size: 14; color: head.c.famMedia
                        name: ({ people: "user", places: "location", tags: "tag", albums: "album", favorites: "star", videos: "video", dates: "calendar" })[modelData.kind] || "search"
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.text
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: head.c.text
                    }
                }
            }
        }
    }
}
