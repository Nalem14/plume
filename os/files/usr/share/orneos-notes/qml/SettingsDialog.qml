// Réglages (Ctrl+,): the list's order and groups, the text size, where Quick Notes go.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: app.t.settings

    component Label_: Text {
        Layout.fillWidth: true
        Layout.topMargin: 6
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dialog.c.muted
    }

    Label_ { text: app.t.sort_by }
    OComboBox {
        id: sort
        Layout.fillWidth: true
        model: [{ text: app.t.sort_modified, value: "modified" }, { text: app.t.sort_created, value: "created" }, { text: app.t.sort_title, value: "title" }]
        Component.onCompleted: select(app.prefs.sort)
        onActivated: app.setPref("sort", currentValue)
    }
    OSwitch { text: app.t.group_dates; checked: !!app.prefs.group_dates; onToggled: app.setPref("group_dates", checked) }

    Label_ { text: app.t.text_size }
    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        Text { text: "A"; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: dialog.c.muted }
        Slider {
            id: size
            Layout.fillWidth: true
            from: 14; to: 22; stepSize: 1; snapMode: Slider.SnapAlways
            value: app.prefs.text_size || 16
            onMoved: app.setPref("text_size", Math.round(value))
        }
        Text { text: "A"; font.family: "Schibsted Grotesk"; font.pixelSize: 21; color: dialog.c.muted }
    }

    Label_ { text: app.t.quick_folder }
    OComboBox {
        Layout.fillWidth: true
        model: notes.allFolders.map(f => ({ text: f.name, value: f.path }))
        Component.onCompleted: select(app.prefs.quick_folder || "")
        onActivated: app.setPref("quick_folder", currentValue)
    }
    Text {
        Layout.fillWidth: true
        text: app.t.quick_lead
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }
    Text {
        Layout.fillWidth: true
        Layout.topMargin: 8
        text: app.t.settings_cloud
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.faint
    }
    footer: [
        OButton { kind: "quiet"; iconName: "cloud"; text: app.t.open_cloud; onClicked: app.openCloud("/apps/notes/") },
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
