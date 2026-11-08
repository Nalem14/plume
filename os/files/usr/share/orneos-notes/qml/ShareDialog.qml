// « Partager avec… »: a note shared with people of the cloud, as in the cloud's Notes (an account finds it in
// its own Notes; a group or a team, in its Files; an e-mail address gets a link). Read only, or editable too.
// A note shared with the account: who shared it, and « Ne plus recevoir cette note ».
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string key
    property string label
    property var found: []
    property var people: []
    property bool searching: false
    property var from: ({})
    property bool leaving: false
    readonly property bool received: (from.owner || "") !== ""
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: received ? label : app.t.share_title.replace("%1", label)

    function openFor(k) {
        key = k
        label = notes.detail(k).title || app.t.untitled
        people = notes.shares(k)
        from = notes.sharedWithMe(k)
        leaving = false
        found = []
        search.text = ""
        notes.loadShares(k)
        open()
        if (!received) search.forceActiveFocus()
    }
    function kindOf(type) {
        return type === 1 ? app.t.share_kind_group : type === 4 ? app.t.share_kind_email : type === 7 ? app.t.share_kind_team : ""
    }
    Connections {
        target: notes
        function onRecipientsReady(rows) { dialog.found = rows; dialog.searching = false }
        function onSharesChanged(k) { if (k === dialog.key) dialog.people = notes.shares(k) }
    }
    Timer { id: debounce; interval: 350; onTriggered: { dialog.searching = true; notes.findRecipients(dialog.key, search.text) } }

    Text {
        visible: dialog.received
        Layout.fillWidth: true
        text: app.t.shared_by.replace("%1", dialog.from.owner || "") + "\n" + (dialog.from.editable ? app.t.shared_by_edit : app.t.shared_by_read)
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.text
    }
    OButton {
        visible: dialog.received
        kind: dialog.leaving ? "danger" : "secondary"
        text: dialog.leaving ? app.t.share_leave_confirm : app.t.share_leave
        enabled: notes.online
        onClicked: {
            if (!dialog.leaving) { dialog.leaving = true; return }
            notes.leaveShare(dialog.key)
            dialog.close()
        }
    }
    Text {
        visible: !dialog.received
        Layout.fillWidth: true
        text: app.t.share_lead
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    Text {
        visible: !notes.online
        Layout.fillWidth: true
        text: app.t.error_offline_action
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.saffronInk
    }
    OTextField {
        id: search
        visible: !dialog.received
        Layout.fillWidth: true
        iconName: "search"
        placeholderText: app.t.share_search
        enabled: notes.online
        onTextChanged: { if (text.trim().length >= 2) debounce.restart(); else { debounce.stop(); dialog.found = []; dialog.searching = false } }
    }
    OSwitch { id: canEdit; visible: !dialog.received; text: app.t.share_allow_edit }
    OrnisThinking { visible: dialog.searching; text: app.t.share_searching }
    Repeater {
        model: dialog.found
        AbstractButton {
            id: person
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 44
            hoverEnabled: true
            onClicked: {
                notes.shareWith(dialog.key, modelData.type, modelData.with, modelData.name, canEdit.checked)
                search.text = ""
                dialog.found = []
            }
            background: Rectangle { radius: 8; color: person.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Rectangle {
                    Layout.leftMargin: 8
                    implicitWidth: 30; implicitHeight: 30; radius: 15
                    color: dialog.c.tint
                    Text {
                        visible: person.modelData.type === 0
                        anchors.centerIn: parent
                        text: (person.modelData.name || "?").charAt(0).toUpperCase()
                        font.family: "Schibsted Grotesk"; font.weight: Font.DemiBold; color: dialog.c.tintText
                    }
                    Icon {
                        visible: person.modelData.type !== 0
                        anchors.centerIn: parent
                        name: person.modelData.type === 4 ? "mail" : "people"; size: 16; color: dialog.c.tintText
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; text: person.modelData.name; font.family: "Schibsted Grotesk"; font.pixelSize: 15; color: dialog.c.text }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: dialog.kindOf(person.modelData.type) || person.modelData.sub || person.modelData.with
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: dialog.c.muted
                    }
                }
                Text { Layout.rightMargin: 10; text: app.t.share_add; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: dialog.c.accent }
            }
        }
    }

    Text {
        visible: dialog.people.length > 0
        Layout.topMargin: 4
        text: app.t.shared_with
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dialog.c.muted
    }
    Repeater {
        model: dialog.people
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 10
            Icon { name: modelData.type === 0 ? "user" : modelData.type === 4 ? "mail" : "people"; size: 18; color: dialog.c.muted }
            Text {
                Layout.fillWidth: true
                text: modelData.name + (dialog.kindOf(modelData.type) ? "  ·  " + dialog.kindOf(modelData.type) : "")
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 15; color: dialog.c.text
            }
            Rectangle {                      // on its way to the cloud
                visible: !!modelData.pending
                implicitWidth: 7; implicitHeight: 7; radius: 3.5
                color: dialog.c.saffron
            }
            OSwitch {
                text: app.t.share_can_edit
                checked: modelData.editable
                enabled: notes.online && !modelData.pending
                onToggled: notes.setShareEditable(dialog.key, modelData.id, checked)
            }
            OButton {
                kind: "quiet"; implicitWidth: 32; iconName: "close"; tip: app.t.share_stop
                enabled: notes.online && !modelData.pending
                onClicked: notes.unshare(dialog.key, modelData.id)
            }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
