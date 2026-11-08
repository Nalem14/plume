// « Mes commandes », as the custom prompts of other assistants: a name typed after « / » and the text it puts in the
// message box (« /compte-rendu » → « Fais le compte rendu de cette réunion : décisions, tâches, dates »). The cloud
// keeps them with « Personnaliser Ornis » (the same in Plume, Orneos OS and on every computer). Saved at once.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    readonly property var commands: chat.profile.commands || []
    property int editing: -2              // -2: the list; -1: a new one; n: the n-th
    title: app.t.commands_title
    width: Math.min(600, parent ? parent.width - 48 : 600)
    onOpened: { editing = -2; chat.loadProfile() }

    function startEdit(index) {
        editing = index
        const c = index >= 0 ? commands[index] : { name: "", text: "" }
        nameField.text = c.name || ""
        textField.text = c.text || ""
        nameField.forceActiveFocus()
    }
    function save() {
        const name = nameField.text.trim().toLowerCase().replace(/^\/+/, "").replace(/[^\p{L}\p{N}_-]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 30)
        const text = textField.text.trim()
        if (!name || !text) return
        const list = commands.map(c => ({ name: c.name, text: c.text })).filter((c, i) => i !== editing && c.name !== name)
        list.splice(editing >= 0 ? Math.min(editing, list.length) : list.length, 0, { name: name, text: text })
        chat.saveProfile({ commands: list })
        editing = -2
    }
    function remove(index) {
        chat.saveProfile({ commands: commands.filter((c, i) => i !== index).map(c => ({ name: c.name, text: c.text })) })
    }

    Text {
        Layout.fillWidth: true
        visible: dialog.editing === -2
        text: app.t.commands_lead
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }
    // the list
    ColumnLayout {
        visible: dialog.editing === -2
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: dialog.commands
            Rectangle {
                id: row
                required property var modelData
                required property int index
                Layout.fillWidth: true
                implicitHeight: rowLayout.implicitHeight + 16
                radius: 8
                color: "transparent"
                border.width: 1; border.color: dialog.c.line
                RowLayout {
                    id: rowLayout
                    anchors.fill: parent; anchors.margins: 8; anchors.leftMargin: 12
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            text: "/" + row.modelData.name
                            font.family: "JetBrains Mono"; font.pixelSize: 13; font.weight: Font.Medium
                            color: dialog.c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            text: String(row.modelData.text || "").replace(/\s+/g, " ")
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: dialog.c.muted
                        }
                    }
                    OButton { kind: "quiet"; iconName: "edit"; height_: 30; tip: app.t.edit; onClicked: dialog.startEdit(row.index) }
                    OButton { kind: "quiet"; iconName: "trash"; height_: 30; tip: app.t.delete; onClicked: dialog.remove(row.index) }
                }
            }
        }
        Text {
            visible: dialog.commands.length === 0
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: app.t.commands_empty
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.italic: true
            color: dialog.c.faint
        }
    }
    // one command
    ColumnLayout {
        visible: dialog.editing !== -2
        Layout.fillWidth: true
        spacing: 6
        Text { text: app.t.commands_name; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: dialog.c.text }
        OTextField { id: nameField; Layout.fillWidth: true; placeholderText: app.t.commands_name_ph; onAccepted: textField.forceActiveFocus() }
        Text { Layout.topMargin: 6; text: app.t.commands_text; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: dialog.c.text }
        OTextArea { id: textField; Layout.fillWidth: true; Layout.preferredHeight: 140; placeholderText: app.t.commands_text_ph }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { visible: dialog.editing === -2; text: app.t.close; onClicked: dialog.close() },
        OButton { visible: dialog.editing === -2 && dialog.commands.length < 30; kind: "primary"; iconName: "plus"; text: app.t.commands_add
                  onClicked: dialog.startEdit(-1) },
        OButton { visible: dialog.editing !== -2; text: app.t.cancel; onClicked: dialog.editing = -2 },
        OButton { visible: dialog.editing !== -2; kind: "primary"; text: app.t.ok
                  enabled: nameField.text.trim() !== "" && textField.text.trim() !== ""; onClicked: dialog.save() }
    ]
}
