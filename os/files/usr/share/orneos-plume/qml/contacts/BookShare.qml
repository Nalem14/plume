// Sharing one of my address books with an account or a group of the cloud (as the cloud's Contacts app does):
// who has it, read only or able to edit, and a field to find someone. The cloud does the sharing.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ODialog {
    id: dialog
    property var book: ({})
    property var shares: []
    property var found: []
    property bool loading: false
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: plume.t.book_share_title.replace("%1", book.name || "")

    function openFor(b) {
        book = b
        shares = []
        found = []
        field.text = ""
        loading = true
        people.loadShares(b.id)
        open()
        field.forceActiveFocus()
    }

    Connections {
        target: people
        function onSharesRead(bookId, list) {
            if (bookId === dialog.book.id) {
                dialog.shares = list
                dialog.loading = false
            }
        }
        function onBooksDone(what, ok) {
            if (!ok && dialog.opened && (what === "share" || what === "unshare"))
                people.loadShares(dialog.book.id)       // refused: what the cloud has, again
        }
        function onSharees(text, list) {
            if (text === field.text.trim())
                dialog.found = list.filter(p => !dialog.shares.some(s => s.principal === p.principal))
        }
    }
    Timer { id: typing; interval: 300; onTriggered: people.findSharees(field.text) }

    OTextField {
        id: field
        Layout.fillWidth: true
        iconName: "search"
        placeholderText: plume.t.book_share_ph
        onTextChanged: { dialog.found = []; typing.restart() }
    }
    Repeater {
        model: dialog.found
        AbstractButton {
            id: candidate
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 44
            hoverEnabled: true
            Accessible.name: modelData.name
            onClicked: {
                people.shareBook(dialog.book.id, modelData.principal, true)
                field.text = ""
                dialog.loading = true
            }
            background: Rectangle { radius: 7; color: candidate.hovered ? theme.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 8; name: candidate.modelData.group ? "people" : "user"; size: 18; color: theme.c.muted }
                Text {
                    Layout.fillWidth: true
                    text: candidate.modelData.name + (candidate.modelData.group ? " · " + plume.t.book_share_group : "")
                          + (candidate.modelData.detail ? " · " + candidate.modelData.detail : "")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: theme.c.text
                }
                Icon { Layout.rightMargin: 8; name: "plus"; size: 16; color: theme.c.accent }
            }
        }
    }

    Text {
        Layout.topMargin: 8
        text: plume.t.book_shared_with
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: theme.c.muted
    }
    Text {
        visible: !dialog.loading && dialog.shares.length === 0
        text: plume.t.book_share_none
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    Skeleton { visible: dialog.loading; Layout.fillWidth: true; Layout.preferredHeight: 40; rows: 1; tone: theme.c.line }
    Repeater {
        model: dialog.loading ? [] : dialog.shares
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 10
            Icon { name: modelData.group ? "people" : "user"; size: 18; color: theme.c.muted }
            Text {
                Layout.fillWidth: true
                text: modelData.name
                textFormat: Text.PlainText
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: theme.c.text
            }
            OComboBox {
                Layout.preferredWidth: 160
                model: [{ text: plume.t.book_share_ro, value: "ro" }, { text: plume.t.book_share_rw, value: "rw" }]
                Component.onCompleted: select(modelData.readOnly ? "ro" : "rw")
                onActivated: { dialog.loading = true; people.shareBook(dialog.book.id, modelData.principal, currentValue === "ro") }
            }
            OButton {
                kind: "quiet"; iconName: "close"; implicitWidth: 34; tip: plume.t.book_share_remove
                onClicked: { dialog.loading = true; people.unshareBook(dialog.book.id, modelData.principal) }
            }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: plume.t.close || "OK"; onClicked: dialog.close() }
    ]
}
