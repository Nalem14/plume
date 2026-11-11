// Create or edit a group of bots: a room where several bots work with the person, each one as itself (its SOUL,
// memory and skills); the lead answers what names nobody, or every member answers (ornis_bots groups).
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ODialog {
    id: dlg
    property string groupId: ""
    readonly property bool creating: groupId === ""
    property var picked: []          // member ids, in the order chosen
    property string lead: ""
    property string reply: "lead"
    readonly property var everyone: bots.list.concat(bots.hidden)
    title: creating ? app.t.groups_new : app.t.groups_edit
    width: Math.min(520, Overlay.overlay ? Overlay.overlay.width - 48 : 520)

    function openNew(withBot) {
        groupId = ""
        titleField.text = ""; descField.text = ""; folderField.text = ""
        picked = withBot ? [withBot] : []
        lead = withBot || ""
        reply = "lead"
        open()
        titleField.forceActiveFocus()
    }
    function openEdit(id) {
        const g = bots.groupInfo(id)
        if (!g.id) return
        groupId = id
        titleField.text = g.title || ""
        descField.text = g.description || ""
        folderField.text = g.folder || ""
        picked = (g.members || []).slice()
        lead = g.lead || ""
        reply = g.reply || "lead"
        open()
    }
    function toggle(id) {
        const at = picked.indexOf(id)
        const next = picked.slice()
        if (at >= 0) next.splice(at, 1); else next.push(id)
        picked = next
        if (picked.indexOf(lead) < 0) lead = picked.length ? picked[0] : ""
    }

    Text {
        Layout.fillWidth: true
        text: app.t.groups_new_sub
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.muted
    }
    OTextField { id: titleField; Layout.fillWidth: true; placeholderText: app.t.groups_title_ph }
    OTextArea { id: descField; Layout.fillWidth: true; Layout.preferredHeight: 60; placeholderText: app.t.groups_desc_ph }

    RowLayout {                          // the shared folder: every member writes there (empty: the group's own)
        Layout.fillWidth: true
        spacing: 8
        OTextField { id: folderField; Layout.fillWidth: true; placeholderText: app.t.groups_folder_ph }
        OButton { kind: "quiet"; iconName: "folder"; iconSize: 15; height_: 34; tip: app.t.bots_folder_pick; onClicked: folderPick.open() }
        OButton { visible: folderField.text !== ""; kind: "quiet"; iconName: "close"; iconSize: 14; height_: 34
                  tip: app.t.bots_folder_clear; onClicked: folderField.text = "" }
    }
    FolderDialog {
        id: folderPick
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.bots_folder_pick
        onAccepted: folderField.text = app.localPath(selectedFolder)
    }
    Text {
        text: app.t.groups_members
        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; color: theme.c.muted
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: dlg.everyone
            AbstractButton {
                id: pick
                required property var modelData
                readonly property bool on: dlg.picked.indexOf(modelData.id) >= 0
                implicitHeight: 34
                implicitWidth: pickRow.implicitWidth + 20
                hoverEnabled: true
                onClicked: dlg.toggle(modelData.id)
                Accessible.role: Accessible.CheckBox
                Accessible.checked: on
                Accessible.name: modelData.title
                background: Rectangle {
                    radius: 17
                    color: pick.on ? theme.c.tint : pick.hovered ? theme.c.hover : "transparent"
                    border.width: 1
                    border.color: pick.on ? theme.c.accentLine : theme.c.line
                }
                contentItem: Item {
                    Row {
                        id: pickRow
                        anchors.centerIn: parent
                        spacing: 7
                        BotFace { anchors.verticalCenter: parent.verticalCenter; face: pick.modelData.face; size: 20 }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: pick.modelData.title
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.weight: pick.on ? Font.DemiBold : Font.Medium
                            color: pick.on ? theme.c.tintText : theme.c.text
                        }
                        Icon { visible: pick.on; anchors.verticalCenter: parent.verticalCenter; name: "check"; size: 13; color: theme.c.tintText }
                    }
                }
            }
        }
    }
    Text {
        visible: dlg.everyone.length < 2
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        text: app.t.groups_need_two
        font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.saffronInk
    }

    Text {
        visible: dlg.picked.length > 0
        text: app.t.groups_who_answers
        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; color: theme.c.muted
    }
    ColumnLayout {
        visible: dlg.picked.length > 0
        Layout.fillWidth: true
        spacing: 4
        Repeater {
            model: [["lead", app.t.groups_reply_lead, app.t.groups_reply_lead_sub], ["all", app.t.groups_reply_all, app.t.groups_reply_all_sub]]
            AbstractButton {
                id: replyOpt
                required property var modelData
                readonly property bool on: dlg.reply === modelData[0]
                Layout.fillWidth: true
                implicitHeight: replyCol.implicitHeight + 14
                hoverEnabled: true
                onClicked: dlg.reply = modelData[0]
                Accessible.role: Accessible.RadioButton
                Accessible.checked: on
                Accessible.name: modelData[1]
                background: Rectangle { radius: 8; color: replyOpt.on ? theme.c.tint : replyOpt.hovered ? theme.c.hover : "transparent"
                                        border.width: replyOpt.on ? 1 : 0; border.color: theme.c.accentLine }
                contentItem: RowLayout {
                    spacing: 10
                    Icon { Layout.leftMargin: 8; name: replyOpt.on ? "check" : "circle"; size: 15
                           color: replyOpt.on ? theme.c.tintText : theme.c.muted }
                    ColumnLayout {
                        id: replyCol
                        Layout.fillWidth: true
                        spacing: 1
                        Text { text: replyOpt.modelData[1]; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: theme.c.text }
                        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: replyOpt.modelData[2]
                               font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.muted }
                    }
                }
            }
        }
        RowLayout {
            visible: dlg.reply === "lead"
            Layout.fillWidth: true
            spacing: 8
            Text { text: app.t.groups_lead; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.text }
            OComboBox {
                id: leadBox
                Layout.fillWidth: true
                model: dlg.picked.map(id => { const b = dlg.everyone.find(x => x.id === id); return { text: b ? b.title : id, value: id } })
                currentIndex: Math.max(0, dlg.picked.indexOf(dlg.lead))
                onActivated: index => dlg.lead = dlg.picked[index]
            }
        }
    }

    footer: [
        OButton {
            visible: !dlg.creating
            kind: "quiet"; danger: true; text: app.t.delete
            onClicked: { const id = dlg.groupId; dlg.close(); bots.removeGroup(id) }
        },
        Item { Layout.fillWidth: true },
        OButton { kind: "quiet"; text: app.t.cancel; onClicked: dlg.close() },
        OButton {
            kind: "primary"
            text: dlg.creating ? app.t.bots_create : app.t.save
            enabled: titleField.text.trim() !== "" && dlg.picked.length >= 2
            onClicked: {
                if (dlg.creating) {
                    if (bots.createGroup(titleField.text, descField.text, dlg.picked, dlg.lead, dlg.reply, folderField.text)) {
                        dlg.close()
                        win.openGroup(bots.groupId)
                    }
                } else if (bots.updateGroup(dlg.groupId, { title: titleField.text, description: descField.text,
                                                         members: dlg.picked, lead: dlg.lead, reply: dlg.reply,
                                                         folder: folderField.text })) {
                    dlg.close()
                }
            }
        }
    ]
}
