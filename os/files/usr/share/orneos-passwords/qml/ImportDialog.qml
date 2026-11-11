// Coming from another password manager: its CSV export, read here, then added (offline too). The file holds
// passwords in clear: the dialog says to delete it afterwards.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property var preview: ({})
    property bool reading: false
    title: app.t.import_title
    width: Math.min(540, parent ? parent.width - 48 : 540)

    function start() {
        preview = ({})
        reading = false
        open()
    }
    Connections {
        target: vault
        function onImportReady(result) { dialog.preview = result; dialog.reading = false }
    }

    Text {
        Layout.fillWidth: true
        text: app.t.import_lead
        wrapMode: Text.WordWrap
        lineHeight: 1.3
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: ["Chrome", "Edge", "Firefox", "Safari", "Bitwarden", "1Password", "KeePassXC", "Proton Pass", "Dashlane", "LastPass"]
            Rectangle {
                required property string modelData
                implicitWidth: name.implicitWidth + 16; implicitHeight: 26; radius: 13
                color: theme.c.tint
                Text { id: name; anchors.centerIn: parent; text: parent.modelData; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.tintText }
            }
        }
    }
    OButton {
        visible: dialog.preview.count === undefined && !dialog.reading
        kind: "primary"; iconName: "import"
        text: app.t.import_pick
        onClicked: openFile.open()
    }
    OrnisThinking { visible: dialog.reading; text: app.t.import_reading }

    Banner {
        visible: dialog.preview.error !== undefined
        tone: "danger"; iconName: "warning"
        title: app.t.import_failed
        text: app.t["import_error_" + (dialog.preview.error || "columns")] || ""
    }
    Banner {
        visible: dialog.preview.count !== undefined && dialog.preview.error === undefined
        tone: "tint"; iconName: "check"
        title: app.plural("import_found", dialog.preview.count || 0)
        text: [dialog.preview.codes ? app.t.import_codes.replace("%1", dialog.preview.codes) : "",
               dialog.preview.duplicates ? app.plural("import_duplicates", dialog.preview.duplicates) : "",
               dialog.preview.skipped ? app.plural("import_skipped", dialog.preview.skipped) : ""].filter(x => x).join(" ")
    }
    Text {
        visible: dialog.preview.count !== undefined
        Layout.fillWidth: true
        text: app.t.import_delete_file
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.saffronInk
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            visible: (dialog.preview.count || 0) > 0
            kind: "primary"; iconName: "import"
            text: app.t.import_go.replace("%1", dialog.preview.count || 0)
            onClicked: {
                const n = vault.confirmImport()
                dialog.close()
                app.toast(app.plural("import_done", n))
            }
        }
    ]

    FileDialog {
        id: openFile
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        nameFilters: ["CSV (*.csv *.CSV)", "* (*)"]
        onAccepted: { dialog.reading = true; vault.readImport(selectedFile.toString()) }
    }
}
