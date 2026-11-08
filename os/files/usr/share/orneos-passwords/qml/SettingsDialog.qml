// Settings: the lock, the clipboard, import and export, the account. Short: the defaults are the right ones.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.settings
    width: Math.min(560, parent ? parent.width - 48 : 560)
    signal importRequested()

    component Heading: Text {
        Layout.fillWidth: true
        Layout.topMargin: 8
        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.6
        color: theme.c.muted
    }
    component Hint: Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.muted
    }
    component Line: RowLayout {
        property string label
        default property alias control: holder.data
        Layout.fillWidth: true
        spacing: 12
        Text { Layout.fillWidth: true; text: parent.label; wrapMode: Text.WordWrap; font.family: "Schibsted Grotesk"; font.pixelSize: 15; color: theme.c.text }
        Item { id: holder; implicitWidth: childrenRect.width; implicitHeight: childrenRect.height }
    }

    Heading { text: app.t.settings_lock }
    Line {
        label: app.t.lock_after
        OComboBox {
            width: 210
            enabled: lock.available
            model: [{ text: app.t.lock_5, value: 5 }, { text: app.t.lock_10, value: 10 }, { text: app.t.lock_30, value: 30 },
                    { text: app.t.lock_60, value: 60 }, { text: app.t.lock_screen_only, value: 0 }]
            Component.onCompleted: select(app.prefs.lock_minutes)
            onActivated: app.setPref("lock_minutes", currentValue)
        }
    }
    Hint { text: lock.available ? (lock.fingerprintKind === "hello" ? app.t.lock_hint_hello : lock.fingerprint ? app.t.lock_hint_finger : app.t.lock_hint) : app.t.lock_unavailable }

    Heading { text: app.t.settings_clipboard }
    Line {
        label: app.t.clipboard_clear
        OComboBox {
            width: 210
            model: [{ text: "30 s", value: 30 }, { text: "1 min", value: 60 }, { text: "2 min", value: 120 }, { text: "5 min", value: 300 }]
            Component.onCompleted: select(app.prefs.clipboard_seconds)
            onActivated: app.setPref("clipboard_seconds", currentValue)
        }
    }
    Hint { text: app.t.clipboard_hint }

    Heading { visible: wifi.available; text: app.t.settings_show }
    OSwitch {
        visible: wifi.available
        text: app.t.show_wifi
        checked: app.prefs.show_wifi
        onToggled: app.setPref("show_wifi", checked)
    }

    Heading { text: app.t.settings_data }
    RowLayout {
        spacing: 8
        OButton { iconName: "import"; text: app.t.import_title; onClicked: { dialog.close(); dialog.importRequested() } }
        OButton { iconName: "export"; text: app.t.export_title; onClicked: exportQuestion.ask(app.t.export_title, app.t.export_warning, [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.export_go, kind: "primary" }], () => saveFile.open()) }
    }
    Hint { text: app.t.vault_hint }

    Heading { text: app.t.settings_account }
    RowLayout {
        spacing: 8
        OButton { iconName: "cloud"; text: app.t.open_cloud; onClicked: app.openCloud("/apps/passwords/") }
        OButton { iconName: "refresh"; text: app.t.reconnect; onClicked: app.openConnect() }
    }
    Hint {
        text: (vault.syncedAt ? app.t.synced_at.replace("%1", app.ago(vault.syncedAt)) : "")
              + (vault.unreadable ? "  ·  " + app.plural("unreadable", vault.unreadable) : "")
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]

    ChoiceDialog { id: exportQuestion }
    FileDialog {
        id: saveFile
        fileMode: FileDialog.SaveFile
        nameFilters: ["CSV (*.csv)"]
        defaultSuffix: "csv"
        currentFile: "file://" + vault.exportName()
        onAccepted: app.toast(vault.exportCsv(selectedFile.toString()) ? app.t.export_done : app.t.export_failed)
    }
}
