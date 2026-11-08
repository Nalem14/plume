// Sharing an entry with other Orneos accounts (a partner, a colleague of the same team): they find it in their
// own Mots de passe, and see each change. Read only, or they may change it too.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string entryId
    property var d: ({})
    property var found: []
    property bool searching: false
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: app.t.share_title.replace("%1", d.label || "")

    function openFor(id) {
        entryId = id
        d = vault.detail(id)
        found = []
        search.text = ""
        open()
        search.forceActiveFocus()
    }
    Connections {
        target: vault
        function onRecipientsReady(rows) { dialog.found = rows; dialog.searching = false }
        function onChanged() { if (dialog.opened) dialog.d = vault.detail(dialog.entryId) }
        function onDone(what, ok, message) {
            if (what === "recipients") dialog.searching = false
        }
    }
    Timer { id: debounce; interval: 350; onTriggered: { dialog.searching = true; vault.findRecipients(search.text) } }

    Text {
        Layout.fillWidth: true
        text: app.t.share_lead
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    Text {
        visible: !vault.online
        Layout.fillWidth: true
        text: app.t.error_offline_action
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.saffronInk
    }
    OTextField {
        id: search
        Layout.fillWidth: true
        iconName: "search"
        placeholderText: app.t.share_search
        enabled: vault.online
        onTextChanged: { if (text.trim().length >= 2) debounce.restart(); else dialog.found = [] }
    }
    OSwitch { id: canEdit; text: app.t.share_allow_edit }
    OrnisThinking { visible: dialog.searching; text: app.t.share_searching }
    Repeater {
        model: dialog.found
        AbstractButton {
            id: person
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 44
            hoverEnabled: true
            // shown under « Partagé avec » at once; the cloud follows (a refusal comes back in a dialog)
            onClicked: { vault.share(dialog.entryId, modelData.id, modelData.name || modelData.id, canEdit.checked); search.text = ""; dialog.found = [] }
            background: Rectangle { radius: 8; color: person.hovered ? theme.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Rectangle {
                    Layout.leftMargin: 8
                    implicitWidth: 30; implicitHeight: 30; radius: 15
                    color: theme.c.tint
                    Text { anchors.centerIn: parent; text: (person.modelData.name || "?").charAt(0).toUpperCase(); font.family: "Schibsted Grotesk"; font.weight: Font.DemiBold; color: theme.c.tintText }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; text: person.modelData.name; font.family: "Schibsted Grotesk"; font.pixelSize: 15; color: theme.c.text }
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; text: person.modelData.id; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.muted }
                }
                Text { Layout.rightMargin: 10; text: app.t.share_add; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: theme.c.accent }
            }
        }
    }

    Text {
        visible: (dialog.d.shares || []).length > 0
        Layout.topMargin: 8
        text: app.t.shared_with
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: theme.c.muted
    }
    Repeater {
        model: dialog.d.shares || []
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 10
            Icon { name: "user"; size: 18; color: theme.c.muted }
            Text { Layout.fillWidth: true; text: modelData.name; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 15; color: theme.c.text }
            Rectangle {                      // on its way to the cloud
                visible: !!modelData.pending
                implicitWidth: 7; implicitHeight: 7; radius: 3.5
                color: theme.c.saffron
            }
            OSwitch {
                text: app.t.share_can_edit
                checked: modelData.editable
                enabled: vault.online && !modelData.pending
                onToggled: vault.setShareEditable(modelData.id, checked)
            }
            OButton { kind: "quiet"; implicitWidth: 32; iconName: "close"; tip: app.t.share_stop; enabled: vault.online && !modelData.pending; onClicked: vault.unshare(modelData.id) }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
