// The side column: the app's kicker (and Ornis, to ask the notes), the search, « Toutes les notes » and
// « Partagées » as cards, the folders (a tree: a folder drags into another), the #tags found in the notes
// (renamed, merged or taken off by a right click), « Récemment supprimées », and at the foot the account and the
// settings (AccountBar, the same place in every app).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: side
    readonly property var c: theme.c
    readonly property var counts: notes.counts
    signal toList()
    signal settingsRequested()
    color: c.chrome

    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    function setSearch(text) { search.text = text }
    property bool allTags: false
    readonly property var tagRows: allTags ? notes.allTags : notes.allTags.slice(0, 24)

    component Row_: AbstractButton {
        id: row
        property string target
        property string iconName
        property int count: 0
        property int depth: 0
        property bool hasChildren: false
        property bool isOpen: false
        property var folder: null
        readonly property bool active: notes.folder === target && notes.query === ""
        Layout.fillWidth: true
        implicitHeight: 34
        hoverEnabled: true
        Accessible.name: text
        onClicked: { search.text = ""; notes.setFolder(target) }
        background: Rectangle {
            radius: 7
            color: row.active ? side.c.card : (row.hovered || drop.containsDrag ? side.c.hover : "transparent")
            border.width: drop.containsDrag ? 1 : 0
            border.color: side.c.accent
            Band {
                visible: row.active
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                radius: 1.5
                color: side.c.famDocs
            }
        }
        contentItem: RowLayout {
            spacing: 8
            Item {
                Layout.leftMargin: 4 + row.depth * 16
                implicitWidth: 14; implicitHeight: 14
                Icon {
                    anchors.centerIn: parent
                    visible: row.hasChildren
                    name: row.isOpen ? "collapse" : "expand"; size: 13; color: side.c.muted
                }
                TapHandler { enabled: row.hasChildren; onTapped: notes.toggleFolder(row.folder.path) }
            }
            Icon { name: row.iconName; size: 18; color: row.active ? side.c.famDocs : side.c.muted }
            Text {
                Layout.fillWidth: true
                text: row.text
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                font.weight: row.active ? Font.DemiBold : Font.Normal
                color: side.c.text
            }
            Text {
                Layout.rightMargin: 10
                text: row.count || ""
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: side.c.muted
            }
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            enabled: row.folder !== null
            onTapped: folderMenu.openFor(row.folder, row)
        }
        // notes dragged from the list onto a folder move there; a folder dragged onto another goes inside it
        // (onto « Notes »: back to the top)
        DropArea {
            id: drop
            anchors.fill: parent
            enabled: row.folder !== null
            keys: ["orneos/notes", "orneos/folder"]
            onEntered: drag => { if (drag.keys.indexOf("orneos/folder") >= 0 && !row.canTake(drag.source.folderPath)) drag.accepted = false }
            onDropped: drag => {
                // after the drag (dragguard.py): rebuilt during it, the dragged row would be gone under Qt (macOS)
                if (drag.keys.indexOf("orneos/folder") >= 0) notes.afterDrag("moveFolder", [drag.source.folderPath, row.folder.path])
                else notes.afterDrag("moveTo", [drag.source.keys, row.folder.path])
                drag.accept()
            }
        }
        function canTake(path) {
            const here = row.folder ? row.folder.path : ""
            return !!path && here !== path && !here.startsWith(path + "/") && (path.indexOf("/") >= 0 ? path.slice(0, path.lastIndexOf("/")) : "") !== here
        }
        readonly property string folderPath: row.folder ? row.folder.path : ""
        DragHandler { id: folderDrag; target: null; enabled: row.folder !== null && row.folder.path !== "" }
        Drag.active: folderDrag.active
        Drag.dragType: Drag.Automatic
        Drag.supportedActions: Qt.MoveAction
        Drag.mimeData: ({ "orneos/folder": row.folderPath })
        Drag.keys: ["orneos/folder"]
        Drag.source: row
        Drag.onDragStarted: notes.dragStarted()
        Drag.onDragFinished: notes.dragEnded()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 12
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 8
            spacing: 10
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                text: app.t.app_name
                elide: Text.ElideRight
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: side.c.famDocs
            }
            OButton {
                kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "ornis"; tip: app.t.ornis_ask
                onClicked: win.askNotes("")
            }
        }

        OTextField {
            id: search
            Layout.fillWidth: true
            Layout.bottomMargin: 12
            iconName: "search"
            placeholderText: app.t.search
            onTextChanged: notes.setQuery(text)
            Keys.onDownPressed: side.toList()
            Keys.onReturnPressed: side.toList()
        }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentHeight: lower.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: lower
                width: parent.width
                spacing: 2

                GridLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 4
                    columns: 2
                    rowSpacing: 8; columnSpacing: 8
                    SmartCard {
                        Layout.fillWidth: true
                        tint: side.c.famDocs; iconName: "note"; text: app.t.all_notes; count: side.counts.all || 0
                        selected: notes.folder === "all" && notes.query === ""
                        onClicked: { search.text = ""; notes.setFolder("all") }
                    }
                    SmartCard {
                        Layout.fillWidth: true
                        tint: side.c.famCommunicate; iconName: "people"; text: app.t.shared_notes; count: side.counts.shared || 0
                        selected: notes.folder === "shared" && notes.query === ""
                        onClicked: { search.text = ""; notes.setFolder("shared") }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    Layout.bottomMargin: 4
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: 10
                        text: app.t.folders
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                        color: side.c.muted
                    }
                    OButton {
                        kind: "quiet"; implicitWidth: 28; height_: 28; iconSize: 16
                        iconName: "folderPlus"; tip: app.t.folder_new
                        onClicked: folderDialog.ask("", "", "")
                    }
                }
                Repeater {
                    model: notes.folders
                    Row_ {
                        required property var modelData
                        target: "folder:" + modelData.path
                        iconName: "folder"
                        text: modelData.name
                        depth: modelData.depth
                        hasChildren: modelData.children
                        isOpen: modelData.open
                        folder: modelData
                        count: modelData.count
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    Layout.bottomMargin: 6
                    visible: notes.tags.length > 0
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: 10
                        text: app.t.tags
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                        color: side.c.muted
                    }
                }
                Flow {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    spacing: 6
                    visible: notes.tags.length > 0
                    Repeater {
                        model: side.tagRows
                        AbstractButton {
                            id: chip
                            required property var modelData
                            readonly property bool active: notes.folder === "tag:" + modelData.tag && notes.query === ""
                            implicitHeight: 26
                            implicitWidth: chipText.implicitWidth + 18
                            hoverEnabled: true
                            onClicked: { search.text = ""; notes.setFolder(active ? "all" : "tag:" + modelData.tag) }
                            TapHandler { acceptedButtons: Qt.RightButton; onTapped: tagMenu.openFor(chip.modelData.tag, chip) }
                            background: Rectangle {
                                radius: 13
                                color: chip.active ? side.c.action : chip.hovered ? side.c.hover : side.c.card
                                border.width: chip.active ? 0 : 1; border.color: side.c.line
                            }
                            contentItem: Text {
                                id: chipText
                                text: "#" + chip.modelData.tag
                                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                color: chip.active ? side.c.actionText : side.c.text
                            }
                        }
                    }
                }

                OButton {
                    visible: notes.allTags.length > 24
                    Layout.leftMargin: 2; Layout.topMargin: 4
                    kind: "quiet"; height_: 28
                    text: side.allTags ? app.t.tags_fewer : app.t.tags_all.replace("%1", notes.allTags.length)
                    onClicked: side.allTags = !side.allTags
                }
                Rectangle { Layout.fillWidth: true; Layout.topMargin: 14; Layout.bottomMargin: 6; implicitHeight: 1; color: side.c.hairline }
                Row_ { target: "trash"; iconName: "trash"; text: app.t.trash; count: side.counts.trash || 0 }
            }
        }

        AccountBar {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
            name: app.profile.name || ""
            email: app.profile.email || ""
            initials: app.profile.initials || ""
            onSettingsRequested: side.settingsRequested()
            OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/notes/") }
            OMenuItem { text: app.t.open_tasks; iconName: "bell"; onTriggered: app.openTasks() }
            OMenuItem { text: app.t.reconnect; iconName: "refresh"; onTriggered: app.openConnect() }
        }
    }

    OMenu {
        id: folderMenu
        property var folder: null
        function openFor(f, item) {
            folder = f
            const p = item.mapToItem(side, item.width - 40, item.height)
            x = p.x; y = p.y
            open()
        }
        OMenuItem { text: app.t.folder_new_inside; iconName: "folderPlus"; onTriggered: folderDialog.ask("", "", folderMenu.folder.path) }
        OMenuItem { visible: folderMenu.folder && folderMenu.folder.path !== ""; text: app.t.folder_rename; iconName: "edit"; onTriggered: folderDialog.ask(folderMenu.folder.path, folderMenu.folder.name, "") }
        OMenuItem {
            visible: folderMenu.folder && folderMenu.folder.path !== ""
            text: app.t.folder_delete; iconName: "trash"
            onTriggered: {
                const f = folderMenu.folder
                if (!f.count) { notes.deleteFolder(f.path, false); return }
                deleteFolder.ask(app.t.folder_delete_title.replace("%1", f.name), app.plural("folder_delete_text", f.count),
                                 [{ id: "cancel", text: app.t.cancel }, { id: "keep", text: app.t.folder_keep_notes },
                                  { id: "yes", text: app.t.folder_delete_with, kind: "danger" }],
                                 choice => notes.deleteFolder(f.path, choice === "yes"))
            }
        }
    }
    ChoiceDialog { id: deleteFolder }

    OMenu {
        id: tagMenu
        property string tag
        function openFor(t, item) {
            tag = t
            const p = item.mapToItem(side, 0, item.height)
            x = Math.min(p.x, side.width - implicitWidth - 8); y = p.y
            open()
        }
        OMenuItem { text: app.t.tag_rename; iconName: "edit"; onTriggered: tagDialog.ask(tagMenu.tag) }
        OMenuItem {
            text: app.t.tag_remove; iconName: "trash"; danger: true
            onTriggered: {
                const t = tagMenu.tag
                const count = (notes.allTags.find(x => x.tag === t) || {}).count || 0
                deleteFolder.ask(app.t.tag_remove_title.replace("%1", "#" + t), app.plural("tag_remove_text", count),
                                 [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.tag_remove, kind: "danger" }],
                                 () => notes.deleteTag(t))
            }
        }
    }
    ODialog {
        id: tagDialog
        property string tag
        width: Math.min(420, parent ? parent.width - 48 : 420)
        title: app.t.tag_rename_title.replace("%1", "#" + tag)
        function ask(t) { tag = t; tagName.text = t; open(); tagName.forceActiveFocus(); tagName.selectAll() }
        function accept() { if (tagName.text.trim()) notes.renameTag(tag, tagName.text); close() }
        OTextField { id: tagName; Layout.fillWidth: true; iconName: "hash"; onAccepted: tagDialog.accept() }
        Text {
            Layout.fillWidth: true
            text: app.t.tag_rename_lead
            wrapMode: Text.WordWrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: side.c.muted
        }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: tagDialog.close() },
            OButton { kind: "primary"; text: app.t.save; onClicked: tagDialog.accept() }
        ]
    }

    ODialog {
        id: folderDialog
        property string path
        property string parentPath
        width: Math.min(420, parent ? parent.width - 48 : 420)
        title: path ? app.t.folder_rename : (parentPath ? app.t.folder_new_in.replace("%1", parentPath.split("/").pop()) : app.t.folder_new)
        function ask(p, label, parentOf) {
            path = p
            parentPath = parentOf
            name.text = label
            open()
            name.forceActiveFocus()
            name.selectAll()
        }
        function accept() {
            if (!name.text.trim()) return
            if (path) notes.renameFolder(path, name.text)
            else notes.createFolder(parentPath, name.text)
            close()
        }
        OTextField {
            id: name
            Layout.fillWidth: true
            placeholderText: app.t.folder_name
            onAccepted: folderDialog.accept()
        }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: folderDialog.close() },
            OButton { kind: "primary"; text: folderDialog.path ? app.t.save : app.t.create; onClicked: folderDialog.accept() }
        ]
    }
}
