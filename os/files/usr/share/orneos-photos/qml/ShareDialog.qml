// Sharing an album: with accounts or groups of the cloud (they see it in their Photos, and can add to it),
// and a public link (copied). Shown at once; the cloud follows, and a refusal puts things back.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string album
    property var people: []
    property var found: []
    readonly property var link: people.find(p => p.type === 3) || null
    width: Math.min(520, parent ? parent.width - 48 : 520)
    tint: theme.c.famMedia
    title: app.t.album_share_title.replace("%1", (photos.lists.albums || []).find(a => a.id === album)?.name || "")

    function openFor(id) {
        album = id; people = []; found = []; who.text = ""
        photos.loadCollaborators(id)
        open()
        who.forceActiveFocus()
    }
    function apply(list) { people = list; photos.setCollaborators(album, list) }

    Connections {
        target: photos
        function onCollaboratorsReady(id, list) { if (id === dialog.album) dialog.people = list }
        function onPeopleFound(list) { dialog.found = list.filter(p => !dialog.people.some(q => q.id === p.id && q.type === p.type)) }
    }

    OTextField {
        id: who
        Layout.fillWidth: true
        iconName: "user"
        placeholderText: app.t.share_with_placeholder
        onTextChanged: searchLater.restart()
        Timer { id: searchLater; interval: 250; onTriggered: photos.searchPeople(who.text) }
    }
    Repeater {
        model: who.text !== "" ? dialog.found : []
        AbstractButton {
            id: hit
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 40
            hoverEnabled: true
            onClicked: { dialog.apply(dialog.people.concat([modelData])); who.text = "" }
            background: Rectangle { radius: 8; color: hit.hovered ? theme.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 8; name: hit.modelData.type === 1 ? "people" : "user"; size: 18; color: theme.c.muted }
                Text { Layout.fillWidth: true; text: hit.modelData.label; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: theme.c.text; elide: Text.ElideRight }
                Icon { Layout.rightMargin: 8; name: "plus"; size: 16; color: theme.c.action }
            }
        }
    }
    Text {
        visible: dialog.people.filter(p => p.type !== 3).length > 0
        Layout.topMargin: 4
        text: app.t.shared_with
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
        color: theme.c.muted
    }
    Repeater {
        model: dialog.people.filter(p => p.type !== 3)
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 10
            Rectangle {
                implicitWidth: 30; implicitHeight: 30; radius: 15
                color: theme.c.tint
                Icon { anchors.centerIn: parent; name: modelData.type === 1 ? "people" : "user"; size: 16; color: theme.c.tintText }
            }
            Text { Layout.fillWidth: true; text: modelData.label || modelData.id; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: theme.c.text; elide: Text.ElideRight }
            OButton {
                kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "close"; tip: app.t.share_stop
                onClicked: dialog.apply(dialog.people.filter(p => !(p.id === modelData.id && p.type === modelData.type)))
            }
        }
    }
    Rectangle { Layout.fillWidth: true; Layout.topMargin: 4; implicitHeight: 1; color: theme.c.hairline }
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { name: "link"; size: 18; color: theme.c.muted }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text { text: app.t.public_link; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: theme.c.text }
            Text {
                Layout.fillWidth: true
                text: dialog.link ? (dialog.link.url || app.t.share_making) : app.t.public_link_off
                font.family: dialog.link && dialog.link.url ? "JetBrains Mono" : "Schibsted Grotesk"; font.pixelSize: 12
                color: theme.c.muted; elide: Text.ElideMiddle
            }
        }
        OButton {
            visible: dialog.link !== null && (dialog.link.url || "") !== ""
            kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "copy"; tip: app.t.copy_link
            onClicked: { app.copyText(dialog.link.url); toast.show(app.t.share_copied) }
        }
        OSwitch {
            checked: dialog.link !== null
            Accessible.name: app.t.public_link
            onToggled: dialog.apply(checked ? dialog.people.concat([{ id: "", label: app.t.public_link, type: 3 }])
                                            : dialog.people.filter(p => p.type !== 3))
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
