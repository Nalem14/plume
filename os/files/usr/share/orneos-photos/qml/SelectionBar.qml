// While photos are chosen: how many, and what can be done with all of them at once (favourite, album, link,
// download, then remove from the album or person, delete). In the trash: restore or delete for good.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Surface {
    id: bar
    readonly property bool trash: photos.view === "trash"
    readonly property string kind: photos.view.split(":")[0]
    signal albumWanted(var item)
    implicitHeight: 52
    radius: 10

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14; anchors.rightMargin: 8
        spacing: 4
        Rectangle {
            implicitWidth: 22; implicitHeight: 22; radius: 11
            color: bar.c.action
            Icon { anchors.centerIn: parent; name: "check"; size: 14; color: bar.c.actionText }
        }
        Text {
            Layout.leftMargin: 6
            Layout.fillWidth: true
            text: app.plural("chosen", win.chosen.length)
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
            color: bar.c.text
            elide: Text.ElideRight
        }
        OButton { visible: !bar.trash; kind: "quiet"; implicitWidth: 36; iconName: "star"; tip: app.t.favorite + "  (.)"; onClicked: photos.toggleFavorite(win.chosen) }
        OButton { id: albumButton; visible: !bar.trash; kind: "quiet"; implicitWidth: 36; iconName: "album"; tip: app.t.add_to_album; onClicked: bar.albumWanted(albumButton) }
        OButton { visible: !bar.trash; kind: "quiet"; implicitWidth: 36; iconName: "people"; tip: app.t.share_with; onClicked: shareAlbum.ask(win.chosen.slice()) }
        OButton { visible: !bar.trash; kind: "quiet"; implicitWidth: 36; iconName: "link"; tip: app.t.share_link; onClicked: photos.shareLink(win.chosen) }
        OButton { visible: !bar.trash; kind: "quiet"; implicitWidth: 36; iconName: "download"; tip: app.t.download; onClicked: photos.download(win.chosen) }
        OButton {
            visible: bar.kind === "albums" && photos.heading.own === true
            kind: "quiet"; iconName: "close"; text: app.t.remove_from_album
            onClicked: { photos.removeFromAlbum(photos.heading.ref, win.chosen); win.clearChoice() }
        }
        OButton {
            visible: bar.kind === "recognize"
            kind: "quiet"; iconName: "close"; text: app.t.not_this_person
            onClicked: { photos.notThisPerson(photos.heading.ref, win.chosen); win.clearChoice() }
        }
        OButton {
            id: moreButton
            visible: !bar.trash
            kind: "quiet"; implicitWidth: 36; iconName: "more"; tip: app.t.more
            onClicked: moreMenu.open()
            OMenu {
                id: moreMenu
                y: -height - 8
                x: parent.width - width
                OMenuItem { text: app.t.rotate_left; iconName: "rotate"; onTriggered: photos.rotate(win.chosen, 270) }
                OMenuItem { text: app.t.rotate_right; iconName: "rotate"; onTriggered: photos.rotate(win.chosen, 90) }
                OMenuItem { text: app.t.change_date; iconName: "calendar"; onTriggered: dateDialog.openFor(win.chosen.slice(), "") }
                OMenuItem {
                    text: photos.view === "archive" ? app.t.unarchive_action : app.t.archive_action; iconName: "archive"
                    onTriggered: { photos.archive(win.chosen.slice(), photos.view !== "archive"); win.clearChoice() }
                }
            }
        }
        OButton {
            visible: !bar.trash
            kind: "quiet"; implicitWidth: 36; iconName: "trash"; tip: app.t.delete_action + "  (" + app.t.key_delete + ")"
            onClicked: win.remove(win.chosen.slice())
        }
        OButton {
            visible: bar.trash
            iconName: "restore"; text: app.t.restore
            onClicked: { photos.restore(win.chosen); win.clearChoice() }
        }
        OButton {
            visible: bar.trash
            kind: "quiet"; iconName: "trash"; text: app.t.delete_forever
            onClicked: {
                const paths = win.chosen.slice()
                purgeDialog.ask(app.plural("purge_title", paths.length), app.t.purge_text,
                                [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete_forever, kind: "danger" }],
                                () => { photos.purge(paths); win.clearChoice() })
            }
        }
        Rectangle { Layout.leftMargin: 4; Layout.rightMargin: 4; implicitWidth: 1; implicitHeight: 24; color: bar.c.hairline }
        OButton { kind: "quiet"; implicitWidth: 36; iconName: "close"; tip: app.t.clear_choice + "  (" + app.t.key_escape + ")"; onClicked: win.clearChoice() }
    }
    ChoiceDialog { id: purgeDialog }
}
