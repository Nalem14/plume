// Files of the Drive for Ornis to read: folders to walk into, the files Ornis can read (images, PDF, text, Office)
// to tick, then "Attach". Nothing is copied: the message points at the files where they are.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: picker
    signal picked(var rows)
    signal folderPicked(string path)     // folderMode: « Choisir ce dossier » (a project's folder)
    property bool folderMode: false
    property string path: "/"
    property var rows: []
    property var chosen: ({})            // path → row
    property string problem: ""
    property bool loading: false
    readonly property int count: Object.keys(chosen).length
    title: folderMode ? app.t.project_drive_pick : app.t.drive_title
    width: Math.min(560, parent ? parent.width - 48 : 560)

    function openAt(where) { chosen = ({}); go(where); open() }
    function go(where) { path = where || "/"; rows = []; problem = ""; loading = true; chat.browse(path) }
    function toggle(row) {
        const next = Object.assign({}, chosen)
        if (next[row.path]) delete next[row.path]
        else next[row.path] = row
        chosen = next
    }

    Connections {
        target: chat
        function onFolderListed(where, entries, why) {
            if (where !== picker.path) return
            picker.rows = entries
            picker.problem = why
            picker.loading = false
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 6
        OButton {
            visible: picker.path !== "/"
            kind: "quiet"; iconName: "chevronLeft"; iconSize: 16; height_: 30; tip: app.t.drive_up
            onClicked: picker.go(picker.path.replace(/\/[^\/]+\/?$/, "") || "/")
        }
        Icon { visible: picker.path === "/"; name: "cloud"; size: 18; color: picker.c.muted }
        Text {
            Layout.fillWidth: true
            text: picker.path === "/" ? app.t.drive_home : picker.path.split("/").filter(p => p).join(" › ")
            elide: Text.ElideLeft
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
            color: picker.c.text
        }
    }

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.preferredHeight: 340
        clip: true
        model: picker.rows
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: AbstractButton {
            id: row
            required property var modelData
            readonly property bool ticked: !!picker.chosen[modelData.path]
            width: list.width
            height: 40
            hoverEnabled: true
            enabled: modelData.folder || !picker.folderMode
            onClicked: modelData.folder ? picker.go(modelData.path) : picker.toggle(modelData)
            Accessible.name: modelData.name
            background: Rectangle {
                radius: 8
                color: row.ticked ? picker.c.tint : row.hovered || row.visualFocus ? picker.c.hover : "transparent"
            }
            contentItem: RowLayout {
                spacing: 10
                Item { width: 2 }
                Icon {
                    name: row.modelData.folder ? "folder" : row.modelData.kind === "image" ? "image"
                        : /\.pdf$/i.test(row.modelData.name) ? "pdf" : row.modelData.kind === "text" ? "note" : "clip"
                    size: 18
                    color: row.modelData.folder ? picker.c.accent : picker.c.muted
                }
                Text {
                    Layout.fillWidth: true
                    text: row.modelData.name
                    elide: Text.ElideMiddle
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: picker.c.text
                }
                Icon {
                    name: row.modelData.folder ? "chevronRight" : "check"
                    visible: row.modelData.folder || row.ticked
                    size: 16
                    color: row.ticked ? picker.c.accent : picker.c.faint
                }
                Item { width: 4 }
            }
        }
        Text {
            anchors.centerIn: parent
            width: parent.width - 40
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            visible: !picker.loading && picker.rows.length === 0
            text: picker.problem === "offline" ? app.t.offline : picker.problem ? app.t.attach_failed : app.t.drive_empty
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: picker.c.muted
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: picker.close() },
        OButton {
            visible: picker.folderMode
            kind: "primary"
            text: app.t.project_drive_choose
            onClicked: { picker.folderPicked(picker.path); picker.close() }
        },
        OButton {
            visible: !picker.folderMode
            kind: "primary"
            enabled: picker.count > 0
            text: picker.count > 0 ? app.t.attach + " (" + picker.count + ")" : app.t.attach
            onClicked: { picker.picked(Object.keys(picker.chosen).map(k => picker.chosen[k])); picker.close() }
        }
    ]
}
