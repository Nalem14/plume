// A name to give: a new album (with the photos chosen, if any), an album renamed, a person named.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string mode            // "album-new" | "album-rename" | "person" | "share" (a new album to share photos)
    property string ref
    property var ids: []
    width: Math.min(440, parent ? parent.width - 48 : 440)
    tint: theme.c.famMedia
    property string initial
    title: mode === "album-new" ? app.t.album_new : mode === "album-rename" ? app.t.album_rename
         : mode === "share" ? app.t.share_album_title
         : initial !== "" ? app.t.person_rename : app.t.person_name

    function ask(m, r, label, list) {
        mode = m; ref = r; ids = list || []; initial = label
        name.text = label
        open()
        name.forceActiveFocus()
        name.selectAll()
    }
    function accept() {
        const text = name.text.trim()
        if (!text) return
        if (mode === "album-new") {
            const album = photos.createAlbum(text, ids)
            if (album && !ids.length) win.openView("albums:" + album)
            win.clearChoice()
        } else if (mode === "share") {
            photos.shareWith(ids, text)
            win.clearChoice()
        } else if (mode === "album-rename") photos.renameAlbum(ref, text)
        else photos.renamePerson(ref, text)
        close()
    }

    Text {
        visible: (dialog.mode === "album-new" || dialog.mode === "share") && dialog.ids.length > 0
        Layout.fillWidth: true
        text: app.plural(dialog.mode === "share" ? "share_album_lead" : "album_new_with", dialog.ids.length)
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
        wrapMode: Text.WordWrap
    }
    OTextField {
        id: name
        Layout.fillWidth: true
        placeholderText: dialog.mode === "person" ? app.t.person_name_placeholder : app.t.album_name_placeholder
        onAccepted: dialog.accept()
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: dialog.mode === "album-new" ? app.t.create : dialog.mode === "share" ? app.t.share_next : app.t.save; onClicked: dialog.accept() }
    ]
}
