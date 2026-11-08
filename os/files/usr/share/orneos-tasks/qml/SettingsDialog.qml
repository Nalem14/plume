// Réglages (Ctrl+,): the default list, the mails tagged « À faire », reminders and the dock's count.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

ODialog {
    id: dialog
    readonly property var c: theme.c
    width: Math.min(540, parent ? parent.width - 48 : 540)
    title: app.t.settings

    component Label_: Text {
        Layout.fillWidth: true
        Layout.topMargin: 6
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dialog.c.muted
    }
    component Lead: Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }

    Label_ { text: app.t.default_list_label }
    OComboBox {
        Layout.fillWidth: true
        model: tasks.writableLists.map(l => ({ text: l.name, value: l.href, color: Colors.display(l.color, theme.dark) }))
        Component.onCompleted: select(tasks.defaultList)
        onActivated: app.setPref("default_list", currentValue)
    }
    Lead { text: app.t.default_list_lead }

    OSwitch { Layout.topMargin: 8; text: app.t.mail_todos; checked: app.prefs.mail_todos !== false; onToggled: app.setPref("mail_todos", checked) }
    Lead { text: app.t.mail_todos_lead }

    OSwitch { Layout.topMargin: 8; text: app.t.notify; checked: app.prefs.notify !== false; onToggled: app.setPref("notify", checked) }
    Lead { text: app.t.notify_lead }
    OSwitch { text: app.t.badge; checked: app.prefs.badge !== false; onToggled: { app.setPref("badge", checked); tasks.refresh() } }

    // the cards of the side column: shown or not, and their order
    Label_ { text: app.t.tiles_label; Layout.topMargin: 12 }
    Lead { text: app.t.tiles_lead }
    Repeater {
        model: tasks.tiles
        RowLayout {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: 4
            OSwitch {
                Layout.fillWidth: true
                text: app.t["view_" + modelData.view]
                checked: modelData.shown
                onToggled: tasks.setTileShown(modelData.view, checked)
            }
            OButton { kind: "quiet"; implicitWidth: 30; height_: 28; iconName: "chevronLeft"; iconSize: 14; rotation: 90; tip: app.t.list_up
                      enabled: index > 0; onClicked: tasks.moveTile(modelData.view, -1) }
            OButton { kind: "quiet"; implicitWidth: 30; height_: 28; iconName: "chevronRight"; iconSize: 14; rotation: 90; tip: app.t.list_down
                      enabled: index < tasks.tiles.length - 1; onClicked: tasks.moveTile(modelData.view, 1) }
        }
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
        OButton { kind: "quiet"; iconName: "cloud"; text: app.t.open_cloud; onClicked: app.openCloud("/apps/tasks/") },
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
