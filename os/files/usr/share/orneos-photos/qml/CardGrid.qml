// The views made of cards: the years and months of the library (a year opens its months, a month its photos),
// the memories (with the themes Recognize found), people (round faces on raised cards), places, the albums,
// and the trash. Years, months, memories, albums and places carry their title on the picture, over a shade.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "components"

GridView {
    id: grid
    readonly property var c: theme.c
    readonly property string kind: photos.view === "library" ? photos.mode : photos.view
    readonly property bool wide: kind === "years" || kind === "memories"
    readonly property bool overlay: wide || kind === "months" || kind === "albums" || kind === "places"
    readonly property int columns: Math.max(1, Math.floor((width + 14) / (kind === "people" ? 190 : wide ? 380 : kind === "trash" ? 180 : 260)))
    signal yearPicked(var card)
    signal monthPicked(var card)

    function showMonthOf(year) {
        const cards = photos.cards
        for (let i = 0; i < cards.length; ++i)
            if (cards[i].year === year) { positionViewAtIndex(i, GridView.Beginning); return }
    }
    function open(card) {
        if (kind === "years") yearPicked(card)
        else if (kind === "months") monthPicked(card)
        else if (kind === "memories") win.openView("memory:" + card.key)
        else if (kind === "people") win.openView("recognize:" + card.id)
        else if (kind === "places") win.openView("places:" + card.id)
        else if (kind === "albums") win.openView("albums:" + card.id)
    }
    function cover(card) {
        // a place or a theme without a cover chosen yet: the picture Memories makes for it
        if ((kind === "places") && !card.cover)
            return "c/places/0//" + encodeURIComponent(card.id)
        if (!card.fileid && !card.cover) return ""
        if (kind === "people")
            return "c/recognize/" + card.cover + "/" + card.etag + "/" + encodeURIComponent((app.profile.user || "") + "/" + card.id)
        if (kind === "albums")
            return "c/albums/" + card.cover + "/" + card.etag + "/" + encodeURIComponent(card.id)
        if (kind === "trash")
            return "t/256/" + card.fileid + "/" + card.etag
        const size = wide ? "p/1024/" : "t/512/"
        return "" + size + (card.fileid || card.cover) + "/" + card.etag
    }

    model: photos.cards
    clip: true
    cellWidth: Math.floor(width / columns)
    cellHeight: kind === "people" ? 250 : wide ? Math.round(cellWidth * 0.62) : overlay ? Math.round(cellWidth * 0.8)
              : kind === "trash" ? cellWidth + 34 : cellWidth + 44
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    // years and months: Ctrl+wheel and a pinch go on to the photos (PhotosView.zoomBy)
    WheelHandler {
        enabled: grid.kind === "years" || grid.kind === "months"
        acceptedModifiers: Qt.ControlModifier
        property real turned: 0
        onWheel: event => {
            turned += event.angleDelta.y
            if (Math.abs(turned) < 120) return
            win.zoomBy(turned > 0 ? 1 : -1)
            turned = 0
        }
    }
    PinchHandler {
        enabled: grid.kind === "years" || grid.kind === "months"
        target: null
        onActiveChanged: if (!active && Math.abs(activeScale - 1) > 0.2) win.zoomBy(activeScale > 1 ? 1 : -1)
    }

    // the memories: the themes found in the photos (Beach, Cat…), above the cards
    header: Item {
        width: grid.width
        height: grid.kind === "memories" && (photos.lists.tags || []).length ? themes.implicitHeight + 18 : 0
        visible: height > 0
        Flow {
            id: themes
            width: parent.width
            spacing: 6
            Text {
                height: 28; verticalAlignment: Text.AlignVCenter
                text: app.t.themes
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                color: grid.c.muted
                rightPadding: 6
            }
            Repeater {
                model: photos.lists.tags || []
                AbstractButton {
                    id: chip
                    required property var modelData
                    implicitHeight: 28
                    implicitWidth: chipText.implicitWidth + 22
                    hoverEnabled: true
                    onClicked: win.openView("tags:" + modelData.id)
                    background: Rectangle {
                        radius: 14
                        color: chip.hovered ? grid.c.hover : grid.c.card
                        border.width: 1; border.color: grid.c.line
                    }
                    contentItem: Text {
                        id: chipText
                        text: chip.modelData.name + "  " + chip.modelData.count
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: grid.c.text
                    }
                }
            }
        }
    }

    delegate: Item {
        id: cell
        required property var modelData
        required property int index
        readonly property bool chosen: grid.kind === "trash" && win.chosen.indexOf(modelData.path) >= 0
        width: grid.cellWidth
        height: grid.cellHeight

        AbstractButton {
            id: card
            anchors.fill: parent
            anchors.margins: 7
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.name: (cell.modelData.title || cell.modelData.name || String(cell.modelData.year || "")) + ", "
                             + app.plural("count_photos", cell.modelData.count || 0)
            onClicked: {
                if (grid.kind !== "trash") { grid.open(cell.modelData); return }
                const next = win.chosen.slice()
                const at = next.indexOf(cell.modelData.path)
                if (at >= 0) next.splice(at, 1); else next.push(cell.modelData.path)
                win.chosen = next
            }
            padding: grid.kind === "people" ? 14 : 0
            property real lift: hovered && grid.kind === "people" ? -3 : 0
            Behavior on lift { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
            // people: a card raised from the page, lifted a little more under the pointer
            background: Surface {
                visible: grid.kind === "people"
                radius: 16
                transform: Translate { y: card.lift }
            }
            contentItem: ColumnLayout {
                spacing: grid.kind === "people" ? 10 : 8
                transform: Translate { y: card.lift }
                // the picture: a round face for people, else a rounded card
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: grid.overlay
                    Layout.preferredHeight: grid.kind === "people" ? 132 : grid.overlay ? -1 : card.width
                    // the shadow under a picture card
                    RectangularShadow {
                        visible: grid.overlay
                        anchors.fill: frame
                        radius: frame.radius
                        blur: card.hovered ? 30 : 22; spread: -8; offset.y: card.hovered ? 12 : 9
                        color: grid.c.elev
                        Behavior on blur { NumberAnimation { duration: 200 } }
                    }
                    // a person: the face in a ring, of the family when named
                    Rectangle {
                        visible: grid.kind === "people"
                        z: 2                        // over the frame's square corners
                        anchors.centerIn: frame
                        width: frame.width + 12; height: width; radius: width / 2
                        color: "transparent"
                        border.width: 2
                        border.color: cell.modelData.name ? grid.c.famMedia : grid.c.line
                    }
                    Rectangle {
                        id: frame
                        anchors.centerIn: parent
                        width: grid.kind === "people" ? 116 : parent.width
                        height: grid.kind === "people" ? width : parent.height
                        radius: grid.kind === "people" ? width / 2 : 14
                        color: Qt.tint(grid.c.line, Qt.alpha(grid.c.famMedia, 0.10))
                        clip: true
                        border.width: card.visualFocus || cell.chosen ? 3 : 0
                        border.color: cell.chosen ? grid.c.action : grid.c.saffron
                        Thumb {
                            anchors.fill: parent
                            anchors.margins: cell.chosen ? 5 : 0
                            address: grid.cover(cell.modelData)
                            sourceSize: Qt.size(grid.wide ? 1024 : 512, grid.wide ? 1024 : 512)
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            opacity: status === Image.Ready ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 160 } }
                            scale: card.hovered && grid.kind !== "trash" ? 1.03 : 1
                            Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                        }
                        Icon {
                            anchors.centerIn: parent
                            visible: grid.cover(cell.modelData) === ""
                            name: grid.kind === "people" ? "user" : grid.kind === "albums" ? "album" : "image"
                            size: 34; color: grid.c.muted
                        }
                        // the card's round corners (a circle for a face), then its focus or choice ring over them
                        Corners { anchors.fill: parent; radius: frame.radius; color: grid.kind === "people" ? grid.c.card : grid.c.bg }
                        Rectangle {
                            anchors.fill: parent
                            radius: frame.radius; color: "transparent"
                            border.width: frame.border.width; border.color: frame.border.color
                        }
                        // the title on the picture
                        Rectangle {
                            visible: grid.overlay
                            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                            height: parent.height * 0.55
                            gradient: Gradient {
                                GradientStop { position: 0; color: "transparent" }
                                GradientStop { position: 1; color: Qt.rgba(0.04, 0.08, 0.14, 0.78) }
                            }
                        }
                        ColumnLayout {
                            visible: grid.overlay
                            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                            anchors.margins: grid.wide ? 18 : 14
                            spacing: 2
                            Text {
                                visible: text !== ""
                                Layout.fillWidth: true
                                text: grid.kind === "memories" ? cell.modelData.sub || ""
                                    : grid.kind === "albums" && cell.modelData.owner && cell.modelData.owner !== (app.profile.user || "")
                                      ? app.t.kicker_shared_album.replace("%1", cell.modelData.ownerName || cell.modelData.owner)
                                    : grid.kind === "places" ? app.t.kicker_place
                                    : grid.kind === "albums" ? app.t.kicker_album : ""
                                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                                color: Qt.rgba(1, 1, 1, 0.85)
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: grid.kind === "years" ? String(cell.modelData.year)
                                    : grid.kind === "albums" || grid.kind === "places" ? cell.modelData.name || "" : cell.modelData.title || ""
                                font.family: "Schibsted Grotesk"; font.weight: Font.Bold
                                font.pixelSize: grid.kind === "years" ? 40 : grid.wide ? 24 : 20
                                font.letterSpacing: -0.6
                                color: "white"
                                elide: Text.ElideRight
                            }
                            Text {
                                text: app.plural("count_photos", cell.modelData.count || 0)
                                font.family: "JetBrains Mono"; font.pixelSize: 12
                                color: Qt.rgba(1, 1, 1, 0.85)
                            }
                        }
                        Rectangle {
                            visible: cell.modelData.pending === true
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 10
                            width: 8; height: 8; radius: 4; color: grid.c.saffron
                            border.width: 1; border.color: "white"
                        }
                    }
                }
                // under the picture: the name and the count (months, people, places, albums, trash)
                ColumnLayout {
                    visible: !grid.overlay
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: grid.kind === "people" ? Text.AlignHCenter : Text.AlignLeft
                        text: grid.kind === "people" ? (cell.modelData.name || app.t.person_unnamed)
                            : grid.kind === "months" ? cell.modelData.title || "" : cell.modelData.name || ""
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        font.italic: grid.kind === "people" && !cell.modelData.name
                        color: grid.kind === "people" && !cell.modelData.name ? grid.c.muted : grid.c.text
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: grid.kind === "people" ? Text.AlignHCenter : Text.AlignLeft
                        text: grid.kind === "trash" ? app.ago(cell.modelData.deleted) : app.plural("count_photos", cell.modelData.count || 0)
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: grid.c.muted
                        elide: Text.ElideRight
                    }
                }
            }
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            enabled: grid.kind === "people" || (grid.kind === "albums" && cell.modelData.owner === (app.profile.user || ""))
            onTapped: cardMenu.openFor(cell.modelData, cell)
        }
        DropArea {
            anchors.fill: parent
            enabled: grid.kind === "albums"
            keys: ["application/x-orneos-photos"]
            onDropped: drag => {
                photos.addToAlbum(cell.modelData.id, JSON.parse(drag.getDataAsString("application/x-orneos-photos") || "[]"))
                drag.accept(Qt.CopyAction)
            }
        }
    }

    // the albums: « Nouvel album » after the last one
    footer: Item {
        width: grid.width
        height: grid.kind === "albums" ? 64 : grid.kind === "trash" && photos.cards.length ? 52 : 12
        OButton {
            visible: grid.kind === "albums"
            anchors.left: parent.left; anchors.leftMargin: 7; anchors.verticalCenter: parent.verticalCenter
            iconName: "plus"; text: app.t.album_new
            onClicked: nameDialog.ask("album-new", "", "", [])
        }
        Text {
            visible: grid.kind === "trash" && photos.cards.length > 0
            anchors.left: parent.left; anchors.leftMargin: 7; anchors.verticalCenter: parent.verticalCenter
            text: app.t.trash_hint
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: grid.c.muted
        }
    }

    EmptyState {
        anchors.fill: parent
        visible: grid.count === 0 && grid.kind !== "years" && grid.kind !== "months"
        iconName: grid.kind === "people" ? "people" : grid.kind === "places" ? "location" : grid.kind === "trash" ? "trash"
                : grid.kind === "albums" ? "album" : "history"
        title: app.t["empty_" + grid.kind + "_title"] || ""
        lead: app.t["empty_" + grid.kind + "_lead"] || ""
        actionText: grid.kind === "albums" ? app.t.album_new : ""
        actionIcon: "plus"
        onActivated: nameDialog.ask("album-new", "", "", [])
    }

    OMenu {
        id: cardMenu
        property var card: null
        readonly property bool mine: !!card && !(photos.lists.shared || []).some(a => a.id === card.id)
        function openFor(item, cellItem) {
            card = item
            const p = cellItem.mapToItem(grid, cellItem.width / 2, cellItem.height / 2)
            x = Math.min(p.x, grid.width - width - 8); y = Math.min(p.y, grid.height - 200)
            open()
        }
        OMenuItem { visible: grid.kind === "albums" && !cardMenu.mine; text: app.t.leave_album; iconName: "close"; danger: true; onTriggered: photos.leaveAlbum(cardMenu.card.id) }
        OMenuItem { visible: grid.kind === "albums" && cardMenu.mine; text: app.t.album_share; iconName: "share"; onTriggered: shareDialog.openFor(cardMenu.card.id) }
        OMenuItem { visible: grid.kind === "albums" && cardMenu.mine; text: app.t.album_rename; iconName: "edit"; onTriggered: nameDialog.ask("album-rename", cardMenu.card.id, cardMenu.card.name, []) }
        OMenuItem {
            visible: grid.kind === "albums" && cardMenu.mine; text: app.t.album_delete; iconName: "trash"; danger: true
            onTriggered: {
                const a = cardMenu.card
                albumDelete.ask(app.t.album_delete_title.replace("%1", a.name), app.t.album_delete_text,
                                [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.album_delete, kind: "danger" }],
                                () => photos.deleteAlbum(a.id))
            }
        }
        OMenuItem {
            visible: grid.kind === "people"
            text: cardMenu.card && cardMenu.card.name ? app.t.person_rename : app.t.person_name; iconName: "edit"
            onTriggered: nameDialog.ask("person", cardMenu.card.id, cardMenu.card.name || "", [])
        }
        OMenuItem {
            visible: grid.kind === "people" && photos.cards.length > 1
            text: app.t.person_merge; iconName: "people"
            onTriggered: mergeDialog.openFor(cardMenu.card.id)
        }
    }
}
