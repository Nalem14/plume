// The settings of Meet (Ctrl+,): how a call starts, the keys of the composer, notifications and the dock.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.settings
    tint: theme.c.famCommunicate
    readonly property var c: theme.c

    component Option: RowLayout {
        property string key
        property alias text: label.text
        property alias lead: leadText.text
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        spacing: 12
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text { id: label; Layout.fillWidth: true; font.pixelSize: 14; color: dialog.c.text; wrapMode: Text.Wrap }
            Text { id: leadText; Layout.fillWidth: true; visible: text !== ""; font.pixelSize: 12; color: dialog.c.muted; wrapMode: Text.Wrap }
        }
        OSwitch { checked: !!app.prefs[parent.key]; onToggled: app.setPref(parent.key, checked) }
    }

    Text { Layout.leftMargin: 22; Layout.topMargin: 6; text: app.t.settings_calls; font.pixelSize: 12; font.weight: Font.DemiBold; color: dialog.c.muted }
    Option { key: "join_audio"; text: app.t.join_with_mic }
    Option { key: "join_video"; text: app.t.join_with_camera }
    Option { key: "sounds"; text: app.t.ring_sounds }
    Text { Layout.leftMargin: 22; Layout.topMargin: 10; text: app.t.settings_chat; font.pixelSize: 12; font.weight: Font.DemiBold; color: dialog.c.muted }
    Option { key: "enter_sends"; text: app.t.enter_sends; lead: app.t.enter_sends_lead }
    Option { key: "notify"; text: app.t.notify_messages; lead: app.t.notify_messages_lead }
    Option { key: "badge"; text: app.t.dock_badge }
    footer: [OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }]
}
