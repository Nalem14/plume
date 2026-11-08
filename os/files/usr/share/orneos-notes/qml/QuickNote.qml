// Quick Note (Meta+N, like macOS): a small window above the others, a new note ready to type in, saved as it
// is typed. Closed empty, it leaves nothing behind.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"

Window {
    id: quick
    readonly property var c: theme.c
    property string key: ""
    width: 460; height: 400
    minimumWidth: 340; minimumHeight: 240
    flags: Qt.Window | Qt.WindowStaysOnTopHint
    title: app.t.quick_note
    color: c.bg

    function start() {
        if (!visible || key === "" || !notes.detail(key).key) {
            key = notes.createQuick("")
            text.key = key
            text.load("")
        }
        show()
        raise()
        requestActivate()
        text.area.forceActiveFocus()
    }
    onClosing: {
        text.flush()
        notes.discard(key)
        key = ""
        win.quickClosed()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 44
            color: quick.c.chrome
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: quick.c.line }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14; anchors.rightMargin: 8
                spacing: 6
                Rectangle {
                    implicitWidth: 24; implicitHeight: 24; radius: 6
                    color: "#F0A202"
                    Icon { anchors.centerIn: parent; name: "note"; size: 14; color: "#1C1400" }
                }
                Text {
                    Layout.fillWidth: true
                    text: app.t.quick_note + (app.prefs.quick_folder ? " · " + app.prefs.quick_folder : "")
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                    color: quick.c.text
                }
                OButton { kind: "quiet"; implicitWidth: 32; height_: 30; iconName: "checklist"; tip: app.t.checklist; onClicked: text.toggleChecklist() }
                OButton {
                    kind: "quiet"; height_: 30; iconName: "openExternal"; text: app.t.open_in_notes
                    onClicked: { text.flush(); const k = quick.key; quick.key = ""; quick.close(); win.openNote(k); win.bringUp() }
                }
            }
        }
        NoteText {
            id: text
            Layout.fillWidth: true
            Layout.fillHeight: true
            helper: quickHelper
            maxWidth: 2000
            textSize: Math.max(14, (app.prefs.text_size || 16) - 1)
        }
    }
    Shortcut { sequence: "Escape"; onActivated: quick.close() }
}
