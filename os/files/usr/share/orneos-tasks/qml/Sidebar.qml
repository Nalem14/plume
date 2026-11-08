// The side column: the app's kicker, the search, the smart lists as cards (SmartCard: a line glyph in the
// list's colour, the count in the data face; « Aujourd'hui » carries the ring of the day), then « Mes listes »
// and the tags, and at the foot the account and the settings (AccountBar, the same place in every app).
// Tasks dragged onto a list move there; a list dragged among the others changes their order (in the cloud too).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

Rectangle {
    id: side
    readonly property var c: theme.c
    readonly property var counts: tasks.counts
    signal toList()
    signal newList()
    signal editList(var list)
    signal shareList(var list)
    signal newSmart()
    signal editSmart(var rule)
    color: c.chrome

    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    function setSearch(text) { search.text = text }

    signal settingsRequested()

    component Tile: SmartCard {
        id: tile
        property string view
        readonly property bool active: tasks.view === view && tasks.query === ""
        Layout.fillWidth: true
        selected: active
        onClicked: { search.text = ""; tasks.setView(view) }
        DropArea {
            anchors.fill: parent
            keys: ["orneos/tasks"]
            onDropped: drag => {
                const keys = String(drag.getDataAsString("orneos/tasks")).split(",")
                // after the drag (dragguard.py): rebuilt during it, the dragged row would be gone under Qt (macOS)
                if (tile.view === "flagged") tasks.afterDrag("flagMany", [keys, true])
                else if (tile.view === "today") tasks.afterDrag("setDue", [keys, "today"])
                else if (tile.view === "completed") tasks.afterDrag("setDoneMany", [keys, true])
                else if (tile.view === "scheduled") tasks.afterDrag("scheduleUndated", [keys])
                drag.accept()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 12
        spacing: 0

        Text {
            Layout.fillWidth: true
            Layout.leftMargin: 4; Layout.bottomMargin: 12; Layout.topMargin: 4
            text: app.t.app_name
            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
            color: side.c.famOrganize
        }

        OTextField {
            id: search
            Layout.fillWidth: true
            Layout.bottomMargin: 14
            iconName: "search"
            placeholderText: app.t.search
            onTextChanged: tasks.setQuery(text)
            Keys.onDownPressed: side.toList()
            Keys.onReturnPressed: side.toList()
        }

        // the cards, in the order chosen in the settings (some may be hidden)
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 8; columnSpacing: 8
            visible: tasks.tiles.some(t => t.shown)
            Repeater {
                model: tasks.tiles.filter(t => t.shown)
                Tile {
                    required property var modelData
                    readonly property var look: ({ today: ["today", side.c.famOrganize], scheduled: ["calendar", side.c.danger],
                                                   all: ["inbox", side.c.famTools], flagged: ["flag", side.c.saffron],
                                                   completed: ["done", side.c.ok], mail: ["mail", side.c.famCommunicate] })[modelData.view]
                    readonly property int done: side.counts.done_today || 0
                    readonly property int total: done + (side.counts.today || 0)
                    view: modelData.view
                    iconName: look[0]; tint: look[1]
                    text: app.t["view_" + modelData.view]
                    count: side.counts[modelData.view] || 0
                    segments: modelData.view === "today" && total > 0
                              ? Array.from({ length: total }, (_, i) => ({ from: i / total, to: (i + 1) / total,
                                                                           color: i < done ? side.c.famOrganize : side.c.accentLine }))
                              : null
                }
            }
        }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 18
            contentHeight: lower.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: lower
                width: parent.width
                spacing: 2

                // one's own smart lists
                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10; Layout.bottomMargin: 4
                    visible: tasks.smartLists.length > 0
                    text: app.t.smart_header
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                    font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                    color: side.c.muted
                }
                Repeater {
                    model: tasks.smartLists
                    AbstractButton {
                        id: smartRow
                        required property var modelData
                        readonly property bool active: tasks.view === "smart:" + modelData.id && tasks.query === ""
                        Layout.fillWidth: true
                        implicitHeight: 38
                        hoverEnabled: true
                        Accessible.name: modelData.name
                        onClicked: { search.text = ""; tasks.setView("smart:" + modelData.id) }
                        background: Rectangle {
                            radius: 8
                            color: smartRow.active ? side.c.card : smartRow.hovered ? side.c.hover : "transparent"
                            Band {
                                visible: smartRow.active
                                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                                radius: 1.5
                                color: Colors.display(smartRow.modelData.color || "#5B6B82", theme.dark)
                            }
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Icon { Layout.leftMargin: 9; name: "sort"; size: 14; color: Colors.display(smartRow.modelData.color || "#5B6B82", theme.dark) }
                            Text {
                                Layout.fillWidth: true
                                text: smartRow.modelData.name
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                font.weight: smartRow.active ? Font.DemiBold : Font.Normal
                                color: side.c.text
                            }
                            Text {
                                Layout.rightMargin: 10
                                text: side.counts["smart:" + smartRow.modelData.id] || ""
                                font.family: "JetBrains Mono"; font.pixelSize: 12
                                color: side.c.muted
                            }
                        }
                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: side.editSmart(smartRow.modelData) }
                    }
                }
                Item { visible: tasks.smartLists.length > 0; implicitHeight: 12 }

                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10; Layout.bottomMargin: 4
                    text: app.t.my_lists
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                    font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                    color: side.c.muted
                }
                Repeater {
                    id: listRows
                    model: tasks.lists
                    AbstractButton {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool active: tasks.view === "list:" + modelData.href && tasks.query === ""
                        Layout.fillWidth: true
                        implicitHeight: 38
                        hoverEnabled: true
                        Accessible.name: modelData.name
                        onClicked: { search.text = ""; tasks.setView("list:" + modelData.href) }
                        background: Rectangle {
                            radius: 8
                            color: row.active ? side.c.card : (row.hovered || drop.containsDrag ? side.c.hover : "transparent")
                            border.width: drop.containsDrag ? 1 : 0; border.color: row.modelData.color
                            // a list dragged here lands just above this one
                            Rectangle {
                                visible: listDrop.containsDrag
                                anchors.top: parent.top; anchors.topMargin: -2
                                x: 8; width: parent.width - 16; height: 2; radius: 1
                                color: side.c.accent
                            }
                            Band {
                                visible: row.active
                                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                                radius: 1.5
                                color: Colors.display(row.modelData.color, theme.dark)
                            }
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Rectangle {
                                Layout.leftMargin: 10
                                implicitWidth: 11; implicitHeight: 11; radius: 3
                                color: row.modelData.color
                            }
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.name
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                font.weight: row.active ? Font.DemiBold : Font.Normal
                                color: side.c.text
                            }
                            Icon { visible: !!row.modelData.shared; name: "people"; size: 14; color: side.c.muted }
                            Rectangle {
                                visible: row.modelData.pending
                                implicitWidth: 6; implicitHeight: 6; radius: 3; color: side.c.saffron
                            }
                            Icon { visible: row.modelData.readonly; name: "lock"; size: 13; color: side.c.muted }
                            Text {
                                Layout.rightMargin: 10
                                text: side.counts["list:" + row.modelData.href] || ""
                                font.family: "JetBrains Mono"; font.pixelSize: 12
                                color: side.c.muted
                            }
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: listMenu.openFor(row.modelData, row)
                        }
                        DropArea {
                            id: drop
                            anchors.fill: parent
                            keys: ["orneos/tasks"]
                            enabled: !row.modelData.readonly
                            onDropped: drag => { tasks.afterDrag("move", [String(drag.getDataAsString("orneos/tasks")).split(","), row.modelData.href]); drag.accept() }
                        }
                        DropArea {
                            id: listDrop
                            anchors.fill: parent
                            keys: ["orneos/list"]
                            onDropped: drag => {
                                const href = String(drag.getDataAsString("orneos/list"))
                                if (href !== row.modelData.href) tasks.afterDrag("reorderList", [href, row.modelData.href])
                                drag.accept()
                            }
                        }
                        DragHandler { id: listDrag; target: null }
                        Drag.active: listDrag.active
                        Drag.dragType: Drag.Automatic
                        Drag.supportedActions: Qt.MoveAction
                        Drag.mimeData: ({ "orneos/list": row.modelData.href })
                        Drag.onDragStarted: tasks.dragStarted()
                        Drag.onDragFinished: tasks.dragEnded()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    Layout.bottomMargin: 6
                    visible: tasks.tags.length > 0
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
                    visible: tasks.tags.length > 0
                    Repeater {
                        model: tasks.tags
                        AbstractButton {
                            id: chip
                            required property var modelData
                            readonly property bool active: tasks.view === "tag:" + modelData.tag && tasks.query === ""
                            implicitHeight: 26
                            implicitWidth: chipText.implicitWidth + 18
                            hoverEnabled: true
                            onClicked: { search.text = ""; tasks.setView(active ? "all" : "tag:" + modelData.tag) }
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
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6; Layout.bottomMargin: 6
            spacing: 2
            OButton {
                kind: "quiet"; iconName: "plus"; text: app.t.list_new
                onClicked: side.newList()
            }
            Item { Layout.fillWidth: true }
            OButton {
                kind: "quiet"; implicitWidth: 34; iconName: "sort"; tip: app.t.smart_new
                onClicked: side.newSmart()
            }
        }

        AccountBar {
            Layout.fillWidth: true
            Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
            name: app.profile.name || ""
            email: app.profile.email || ""
            initials: app.profile.initials || ""
            onSettingsRequested: side.settingsRequested()
            OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/tasks/") }
            OMenuItem { text: app.t.open_notes; iconName: "note"; onTriggered: app.openNotes() }
            OMenuItem { text: app.t.reconnect; iconName: "refresh"; onTriggered: app.openConnect() }
        }
    }

    OMenu {
        id: listMenu
        property var list: ({})
        function openFor(l, item) {
            list = l
            const p = item.mapToItem(side, item.width - 40, item.height)
            x = p.x; y = p.y
            open()
        }
        OMenuItem { visible: !listMenu.list.readonly; text: app.t.list_edit; iconName: "edit"; onTriggered: side.editList(listMenu.list) }
        OMenuItem { text: app.t.list_default; iconName: "check"; visible: !listMenu.list.readonly && tasks.defaultList !== listMenu.list.href; onTriggered: app.setPref("default_list", listMenu.list.href) }
        // shared with me: the owner shares it, not me
        OMenuItem { visible: !listMenu.list.readonly && !listMenu.list.owner && String(listMenu.list.href || "").indexOf("local:") !== 0; text: app.t.list_share; iconName: "share"; onTriggered: side.shareList(listMenu.list) }
        OMenuItem { visible: tasks.lists.length > 1 && tasks.lists[0].href !== listMenu.list.href; text: app.t.list_up; iconName: "chevronLeft"; onTriggered: tasks.nudgeList(listMenu.list.href, -1) }
        OMenuItem { visible: tasks.lists.length > 1 && tasks.lists[tasks.lists.length - 1].href !== listMenu.list.href; text: app.t.list_down; iconName: "chevronRight"; onTriggered: tasks.nudgeList(listMenu.list.href, 1) }
        OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/tasks/") }
        OMenuItem {
            visible: !listMenu.list.readonly
            text: app.t.list_delete; iconName: "trash"
            onTriggered: {
                const l = listMenu.list
                deleteDialog.ask(app.t.list_delete_title.replace("%1", l.name),
                                 l.events ? app.t.list_delete_events : app.plural("list_delete_text", tasks.counts["list:" + l.href] || 0),
                                 [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.list_delete, kind: "danger" }],
                                 () => tasks.deleteList(l.href))
            }
        }
    }
    ChoiceDialog { id: deleteDialog }
}
