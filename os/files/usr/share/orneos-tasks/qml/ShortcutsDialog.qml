// Ctrl+/: the keyboard shortcuts of Tâches (in Plume, Ctrl+1… change module: the views keep their cards).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property bool viewKeys: true
    width: Math.min(560, parent ? parent.width - 48 : 560)
    title: app.t.shortcuts_title

    // « Ctrl+Maj+N » in the words of the system (⌘ on a Mac, where Qt's Ctrl is the Command key)
    function k(text) {
        return text.replace(/Ctrl/g, Qt.platform.os === "osx" ? "⌘" : "Ctrl").replace(/Shift/g, app.t.key_shift)
                   .replace("Enter", app.t.key_enter).replace("Space", app.t.key_space).replace("Delete", app.t.key_delete)
                   .replace("Escape", app.t.key_escape)
    }
    readonly property var groups: [
        { title: app.t.sc_general, keys: [
            ["Ctrl+N", app.t.sc_new], ["Ctrl+Shift+N", app.t.sc_new_list], ["Ctrl+F", app.t.sc_search],
            ["Ctrl+,", app.t.sc_settings]].concat(viewKeys ? [["Ctrl+1 … 4", app.t.sc_views]] : []).concat([
            ["Ctrl+Shift+F", app.t.sc_flag], ["Ctrl+T", app.t.sc_today], ["F5", app.t.sc_refresh],
            ["Ctrl+/", app.t.sc_help], ["Ctrl+W", app.t.sc_close]]) },
        { title: app.t.sc_in_list, keys: [
            ["↑ ↓", ""], ["Space", app.t.sc_done], ["Enter", app.t.sc_rename], ["Delete", app.t.sc_delete],
            ["Tab · Shift+Tab", app.t.sc_indent], ["Alt+↑ · Alt+↓", app.t.sc_move], ["Ctrl+I", app.t.sc_details],
            ["Ctrl+A", app.t.sc_all], ["Escape", app.t.sc_escape]].filter(k => k[1] !== "") }
    ]

    Repeater {
        model: dialog.groups
        ColumnLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 4
            Text {
                Layout.topMargin: 4
                text: modelData.title
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                color: dialog.c.muted
            }
            Repeater {
                model: modelData.keys
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 12
                    Text {
                        Layout.fillWidth: true
                        text: modelData[1]
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: dialog.c.text
                    }
                    Rectangle {
                        implicitWidth: keyText.implicitWidth + 16; implicitHeight: 24; radius: 6
                        color: dialog.c.field; border.width: 1; border.color: dialog.c.line
                        Text {
                            id: keyText
                            anchors.centerIn: parent
                            text: dialog.k(parent.parent.modelData[0])
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: dialog.c.text
                        }
                    }
                }
            }
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.close; onClicked: dialog.close() }
    ]
}
