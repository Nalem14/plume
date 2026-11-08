// « Envoyer plus tard »: the message and when the cloud sends it (Talk's scheduled messages: sent even when
// this computer is off). The same card changes a message already scheduled.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string editing: ""          // the id of a scheduled message being changed
    title: editing ? app.t.edit_scheduled : app.t.send_later
    tint: c.famCommunicate

    function start(text) {
        editing = ""
        field.text = text || ""
        when.reset(0)
        silent.checked = false
        open()
        field.forceActiveFocus()
    }
    function change(message) {
        editing = message.id
        field.text = message.text
        when.reset(message.at)
        silent.checked = !!message.silent
        open()
    }

    OTextArea {
        id: field
        Layout.fillWidth: true
        Layout.preferredHeight: 110
        placeholderText: app.t.write
        wrapMode: TextEdit.Wrap
    }
    Text { text: app.t.send_at; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text }
    WhenPicker { id: when; Layout.fillWidth: true }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: [{ text: app.t.in_one_hour, at: () => Math.round(Date.now() / 1000) + 3600 },
                    { text: app.t.tomorrow_morning, at: () => { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); return Math.round(d / 1000) } },
                    { text: app.t.monday_morning, at: () => { const d = new Date(); d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7)); d.setHours(9, 0, 0, 0); return Math.round(d / 1000) } }]
            OButton {
                required property var modelData
                kind: "secondary"; height_: 30
                text: modelData.text
                onClicked: when.reset(modelData.at())
            }
        }
    }
    OSwitch { id: silent; text: app.t.silent_send }
    Text {
        Layout.fillWidth: true
        text: app.t.send_later_help
        wrapMode: Text.WordWrap
        font.pixelSize: 12; color: dialog.c.muted
    }
    footer: [
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; iconName: "clock"
            text: dialog.editing ? app.t.save : app.t.schedule_send
            enabled: field.text.trim() !== "" && when.value > Date.now() / 1000
            onClicked: {
                if (dialog.editing) meet.editScheduled(dialog.editing, field.text.trim(), when.value)
                else meet.scheduleMessage(field.text.trim(), when.value, silent.checked)
                dialog.close()
            }
        }
    ]
}
