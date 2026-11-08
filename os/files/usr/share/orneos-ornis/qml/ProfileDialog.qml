// « Personnaliser Ornis », as the other assistants have it: how Ornis calls you, what it should know about you, how it
// answers (the cloud keeps them: the same in the browser, Plume, Orneos OS and Search), and what Ornis remembers,
// each forgettable (its memories, the conversations kept). Saved at once; only a refusal comes back.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    readonly property var p: chat.profile
    readonly property bool ready: p.name !== undefined
    title: app.t.profile_title
    width: Math.min(600, parent ? parent.width - 48 : 600)
    property bool filled: false          // the fields are filled once per opening: a « Forget » keeps what is being typed
    onOpened: { filled = false; fill(); chat.loadProfile(); nameField.forceActiveFocus() }

    function fill() {
        if (!ready || filled) return
        filled = true
        enabled_.checked = p.enabled !== false
        nameField.text = p.name || ""
        aboutField.text = p.about || ""
        styleField.text = p.style || ""
    }
    Connections {
        target: chat
        function onProfileChanged() { if (dialog.opened) dialog.fill() }
    }

    component Label_: Text {
        Layout.fillWidth: true
        Layout.topMargin: 6
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
        color: dialog.c.text
    }
    component Lead: Text {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }
    // a memory or a conversation remembered, with « Forget »
    component Remembered: Rectangle {
        id: row
        property var item: ({})
        property string kind
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
                    Layout.fillWidth: true
                    text: row.item.title || "—"
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                    color: dialog.c.text
                }
                Text {
                    Layout.fillWidth: true
                    visible: !!row.item.text
                    text: String(row.item.text || "").replace(/^#+\s*/gm, "").replace(/\s+/g, " ")
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: dialog.c.muted
                }
            }
            OButton {
                text: app.t.profile_forget; height_: 30
                Accessible.name: app.t.profile_forget + " " + (row.item.title || "")
                onClicked: chat.forget(row.kind, String(row.item.id))
            }
        }
    }

    Lead { text: app.t.profile_lead }
    Lead { visible: !dialog.ready; text: dialog.p.failed ? app.t.profile_failed : app.t.profile_loading }

    ColumnLayout {
        Layout.fillWidth: true
        visible: dialog.ready
        spacing: 8
        OSwitch { id: enabled_; Layout.topMargin: 6; text: app.t.profile_enabled; checked: true }
        Label_ { text: app.t.profile_name }
        OTextField {
            id: nameField
            Layout.fillWidth: true
            maximumLength: 60
            placeholderText: app.t.profile_name_ph
            Accessible.name: app.t.profile_name
        }
        Label_ { text: app.t.profile_about }
        OTextArea {
            id: aboutField
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(84, Math.min(180, implicitHeight))
            placeholderText: app.t.profile_about_ph
            Accessible.name: app.t.profile_about
            onTextChanged: if (length > 1500) remove(1500, length)
        }
        Label_ { text: app.t.profile_style }
        OTextArea {
            id: styleField
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(84, Math.min(180, implicitHeight))
            placeholderText: app.t.profile_style_ph
            Accessible.name: app.t.profile_style
            onTextChanged: if (length > 1500) remove(1500, length)
        }

        Rectangle { Layout.fillWidth: true; Layout.topMargin: 12; implicitHeight: 1; color: dialog.c.line }
        Label_ { text: app.t.profile_memory; font.pixelSize: 16 }
        Lead { text: app.t.profile_memory_lead }
        Label_ { text: app.t.profile_memories; font.pixelSize: 13; color: dialog.c.muted }
        Lead { visible: (dialog.p.memories || []).length === 0; text: app.t.profile_none }
        Repeater {
            model: dialog.p.memories || []
            Remembered { required property var modelData; item: modelData; kind: "memory" }
        }
        Label_ { text: app.t.profile_conversations; font.pixelSize: 13; color: dialog.c.muted }
        Lead { visible: (dialog.p.remembered || []).length === 0; text: app.t.profile_none }
        Repeater {
            model: dialog.p.remembered || []
            Remembered { required property var modelData; item: modelData; kind: "conversation" }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; text: app.t.profile_save
            enabled: dialog.ready
            onClicked: {
                chat.saveProfile({ name: nameField.text, about: aboutField.text, style: styleField.text, enabled: enabled_.checked })
                dialog.close()
            }
        }
    ]
}
