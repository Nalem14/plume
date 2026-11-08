// One task: a round box in its list's colour (ticked with a little bounce), its priority, its title (typed in
// place), the first line of its notes, then what matters at a glance: the date (red when late), repeat,
// reminder, tags, the list (in smart lists), the mail or the note it comes from, its subtasks. The flag on
// the right; ⓘ on hover opens the details. Dragged: onto another place (manual order), a list or a tile.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

AbstractButton {
    id: row
    required property int index
    property var list
    readonly property var c: theme.c
    readonly property var r: list.rows[index] || ({})
    readonly property bool chosen: list.chosen.length > 0 && list.isChosen(r.key)
    readonly property bool current: list.chosen.length > 0 ? chosen : r.key === list.selected
    readonly property bool editing: list.editing === r.key
    readonly property color tone: Colors.display(r.listColor || "#002FA7", theme.dark)
    readonly property bool faded: !!r.done && !r.lingering && tasks.view !== "completed"

    implicitHeight: r.empty ? 40 : Math.max(48, body.implicitHeight + 18)
    hoverEnabled: !r.empty
    enabled: !r.empty
    focusPolicy: Qt.NoFocus
    Accessible.name: r.title || ""
    onClicked: { list.focusView(); list.clickRow(index, app.modifier()) }
    onDoubleClicked: list.inspect(r.key)

    background: Rectangle {
        anchors.fill: parent
        anchors.leftMargin: 12; anchors.rightMargin: 12; anchors.topMargin: 1; anchors.bottomMargin: 1
        radius: 9
        color: row.current || list.linkAt === row.index ? theme.c.tint : (row.hovered ? theme.c.hover : "transparent")
        border.width: list.linkAt === row.index ? 2 : 0
        border.color: theme.c.accent
        Rectangle {
            visible: list.dropAt === row.index
            anchors.top: parent.top; anchors.topMargin: -2
            x: 16 + row.r.depth * 28; width: parent.width - x - 16; height: 2; radius: 1
            color: row.tone
        }
    }

    // an empty section: only a hint, where tasks can be dropped
    Text {
        visible: !!row.r.empty
        x: 60; anchors.verticalCenter: parent.verticalCenter
        text: app.t.section_empty
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.italic: true
        color: theme.c.faint
    }

    contentItem: RowLayout {
        visible: !row.r.empty
        anchors.fill: parent
        anchors.leftMargin: 24 + (row.r.depth || 0) * 28
        anchors.rightMargin: 22
        spacing: 12

        // the box
        AbstractButton {
            id: box
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 11
            implicitWidth: 22; implicitHeight: 22
            hoverEnabled: true
            enabled: !row.r.readonly
            Accessible.name: row.r.done ? app.t.mark_open : app.t.mark_done
            onClicked: tasks.toggleDone(row.r.key)
            background: Rectangle {
                radius: 11
                color: row.r.done ? row.tone : "transparent"
                border.width: row.r.done ? 0 : 1.5
                border.color: box.hovered ? row.tone : Qt.alpha(row.tone, 0.55)
                scale: box.pressed ? 0.86 : 1
                Behavior on color { ColorAnimation { duration: 160 } }
                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutBack } }
                Rectangle {
                    anchors.centerIn: parent
                    visible: !row.r.done && box.hovered
                    width: 10; height: 10; radius: 5
                    color: Qt.alpha(row.tone, 0.35)
                }
                Icon {
                    anchors.centerIn: parent
                    visible: !!row.r.done
                    name: "check"; size: 14; color: "#FFFFFF"
                }
            }
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.topMargin: 9; Layout.bottomMargin: 9
            spacing: 3
            opacity: row.faded || row.r.lingering ? 0.55 : 1
            Behavior on opacity { NumberAnimation { duration: 200 } }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    visible: (row.r.priority || 0) > 0 && !row.editing
                    text: "!".repeat(row.r.priority || 0)
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold; font.letterSpacing: 1
                    color: row.tone
                }
                Text {
                    Layout.fillWidth: true
                    visible: !row.editing
                    text: row.r.title || app.t.untitled
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15
                    font.strikeout: !!row.r.done && tasks.view !== "completed"
                    color: row.r.done ? theme.c.muted : theme.c.text
                    TapHandler {
                        enabled: !row.r.readonly
                        onTapped: { if (row.current) row.list.editing = row.r.key; else row.list.clickRow(row.index, app.modifier()) }
                    }
                }
                TextField {
                    id: titleField
                    Layout.fillWidth: true
                    visible: row.editing
                    text: row.r.title || ""
                    padding: 0
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15
                    color: theme.c.text
                    selectionColor: theme.c.tint
                    background: null
                    onVisibleChanged: if (visible) { text = row.r.title || ""; forceActiveFocus(); selectAll() }
                    onAccepted: { if (text.trim()) tasks.edit(row.r.key, { title: text.trim() }); row.list.editing = "" }
                    onActiveFocusChanged: if (!activeFocus && row.editing) { if (text.trim() && text !== row.r.title) tasks.edit(row.r.key, { title: text.trim() }); row.list.editing = "" }
                    Keys.onEscapePressed: row.list.editing = ""
                    Keys.onTabPressed: { tasks.indent(row.r.key); event.accepted = true }
                }
            }

            Text {
                Layout.fillWidth: true
                visible: (row.r.notes || "") !== ""
                text: row.r.notes || ""
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: theme.c.muted
            }

            Flow {
                Layout.fillWidth: true
                spacing: 10
                visible: (row.r.due || "") !== "" || (list.smart && (row.r.listName || "") !== "") || chips.count > 0 || !!row.r.alarm
                         || (row.r.repeat || "") !== "" || (row.r.children || 0) > 0 || !!row.r.mail || (row.r.note || "") !== ""
                         || (row.r.links || []).length > 0
                Text {
                    visible: (row.r.due || "") !== ""
                    text: row.r.due || ""
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    font.weight: row.r.dueState === "overdue" ? Font.DemiBold : Font.Normal
                    color: row.r.dueState === "overdue" ? theme.c.danger : theme.c.muted
                }
                Icon { visible: !!row.r.alarm; name: "bell"; size: 14; color: theme.c.muted }
                Icon { visible: (row.r.repeat || "") !== ""; name: "repeat"; size: 14; color: theme.c.muted }
                Row {
                    visible: list.smart && (row.r.listName || "") !== ""
                    spacing: 5
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: row.tone }
                    Text { text: row.r.listName || ""; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.muted }
                }
                Repeater {
                    id: chips
                    model: row.r.tags || []
                    Text {
                        required property string modelData
                        text: "#" + modelData
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: theme.c.accent
                    }
                }
                AbstractButton {
                    visible: !!row.r.mail
                    implicitHeight: 22; implicitWidth: mailRow.implicitWidth + 14
                    hoverEnabled: true
                    onClicked: tasks.openMail(row.r.key)
                    ToolTip.text: app.t.open_mail; ToolTip.visible: hovered; ToolTip.delay: 500
                    background: Rectangle { radius: 11; color: parent.hovered ? theme.c.tint : theme.c.card; border.width: 1; border.color: theme.c.line }
                    contentItem: Item { Row {
                        id: mailRow
                        anchors.centerIn: parent
                        spacing: 5
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: "mail"; size: 13; color: theme.c.accent }
                        Text { text: row.r.mailFrom || app.t.mail; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.text }
                    } }
                }
                // the mails, notes and tasks linked to it (dropped on it, or « Lier à… »): a click opens one
                Repeater {
                    model: row.r.links || []
                    AbstractButton {
                        id: linkChip
                        required property var modelData
                        implicitHeight: 22; implicitWidth: Math.min(linkRow.implicitWidth, 200) + 14
                        hoverEnabled: true
                        onClicked: tasks.openLink(modelData.url)
                        ToolTip.text: modelData.title || modelData.url; ToolTip.visible: hovered; ToolTip.delay: 500
                        background: Rectangle { radius: 11; color: linkChip.hovered ? theme.c.tint : theme.c.card; border.width: 1; border.color: theme.c.line }
                        contentItem: Item { Row {
                            id: linkRow
                            anchors.centerIn: parent
                            spacing: 5
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: linkChip.modelData.icon; size: 13; color: theme.c.accent }
                            Text {
                                width: Math.min(implicitWidth, 200 - 18)
                                text: linkChip.modelData.title || app.t.link
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.text
                            }
                        } }
                    }
                }
                AbstractButton {
                    visible: (row.r.note || "") !== ""
                    implicitHeight: 22; implicitWidth: noteRow.implicitWidth + 14
                    hoverEnabled: true
                    onClicked: tasks.openNote(row.r.key)
                    ToolTip.text: app.t.open_note; ToolTip.visible: hovered; ToolTip.delay: 500
                    background: Rectangle { radius: 11; color: parent.hovered ? theme.c.tint : theme.c.card; border.width: 1; border.color: theme.c.line }
                    contentItem: Item { Row {
                        id: noteRow
                        anchors.centerIn: parent
                        spacing: 5
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: "note"; size: 13; color: theme.c.saffronInk }
                        Text { text: app.t.note; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.text }
                    } }
                }
                AbstractButton {
                    visible: (row.r.children || 0) > 0
                    implicitHeight: 22; implicitWidth: kidsRow.implicitWidth + 12
                    hoverEnabled: true
                    onClicked: tasks.toggleCollapsed(row.r.key)
                    background: Rectangle { radius: 11; color: parent.hovered ? theme.c.hover : "transparent" }
                    contentItem: Item { Row {
                        id: kidsRow
                        anchors.centerIn: parent
                        spacing: 4
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: row.r.collapsed ? "expand" : "collapse"; size: 12; color: theme.c.muted }
                        Text {
                            text: app.plural("subtasks_open", row.r.childrenOpen || 0)
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.muted
                        }
                    } }
                }
            }
        }

        Rectangle {
            visible: !!row.r.pending
            Layout.alignment: Qt.AlignTop; Layout.topMargin: 18
            implicitWidth: 6; implicitHeight: 6; radius: 3
            color: theme.c.saffron
            ToolTip.text: app.t.pending_one
            ToolTip.visible: pendingHover.hovered
            HoverHandler { id: pendingHover }
        }
        OButton {
            Layout.alignment: Qt.AlignTop; Layout.topMargin: 6
            visible: row.hovered && !row.editing
            kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "info"; iconSize: 17; tip: app.t.details + "  (Ctrl+I)"
            onClicked: row.list.inspect(row.r.key)
        }
        AbstractButton {
            Layout.alignment: Qt.AlignTop; Layout.topMargin: 8
            visible: !!row.r.flagged || row.hovered
            implicitWidth: 24; implicitHeight: 24
            enabled: !row.r.readonly
            hoverEnabled: true
            onClicked: tasks.toggleFlag(row.r.key)
            ToolTip.text: row.r.flagged ? app.t.unflag : app.t.flag
            ToolTip.visible: hovered; ToolTip.delay: 500
            contentItem: Item { Icon { anchors.centerIn: parent; name: "flag"; size: 17; color: row.r.flagged ? theme.c.saffron : theme.c.faint } }
            background: null
        }
    }

    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: menu.openFor()
    }

    readonly property var keys: row.chosen ? list.chosen : [r.key]
    DragHandler { id: dragger; target: null; enabled: !row.r.readonly && !row.editing && !row.r.empty }
    Drag.active: dragger.active
    Drag.dragType: Drag.Automatic
    Drag.supportedActions: Qt.MoveAction | Qt.CopyAction | Qt.LinkAction
    // a list, a tile or another place here; a link into a note (Notes), onto another task, or elsewhere
    Drag.mimeData: row.hovered ? tasks.dragData(row.keys) : ({ "orneos/tasks": row.keys.join(",") })
    Drag.onDragStarted: tasks.dragStarted()
    Drag.onDragFinished: tasks.dragEnded()

    OMenu {
        id: menu
        function openFor() {
            const p = row.mapToItem(row, Math.min(row.width - 300, 140), row.height - 8)
            x = p.x; y = p.y
            open()
        }
        readonly property bool many: row.list.chosen.length > 1 && row.chosen
        OMenuItem { text: row.r.done ? app.t.mark_open : app.t.mark_done; iconName: "done"; onTriggered: menu.many ? tasks.setDoneMany(row.keys, !row.r.done) : tasks.toggleDone(row.r.key) }
        OMenuItem { visible: !menu.many; text: app.t.details; iconName: "info"; onTriggered: row.list.inspect(row.r.key) }
        OMenuItem { visible: !row.r.readonly; text: row.r.flagged ? app.t.unflag : app.t.flag; iconName: "flag"; onTriggered: tasks.flagMany(row.keys, !row.r.flagged) }
        OMenuItem { visible: !row.r.readonly; text: app.t.due_today; iconName: "today"; onTriggered: tasks.setDue(row.keys, "today") }
        OMenuItem { visible: !row.r.readonly; text: app.t.due_tomorrow; iconName: "sun"; onTriggered: tasks.setDue(row.keys, "tomorrow") }
        OMenuItem { visible: !row.r.readonly; text: app.t.due_weekend; iconName: "calendar"; onTriggered: tasks.setDue(row.keys, "weekend") }
        OMenuItem { visible: !row.r.readonly; text: app.t.due_next_week; iconName: "arrow"; onTriggered: tasks.setDue(row.keys, "nextweek") }
        OMenuItem { visible: !row.r.readonly && (row.r.due || "") !== ""; text: app.t.due_none; iconName: "close"; onTriggered: tasks.setDue(row.keys, "none") }
        Rectangle { width: parent.width; height: 1; color: theme.c.hairline }
        OMenuItem { visible: !row.r.readonly && !menu.many && (row.r.depth || 0) === 0 && row.index > 0; text: app.t.indent; iconName: "subtask"; onTriggered: tasks.indent(row.r.key) }
        OMenuItem { visible: !row.r.readonly && !menu.many && (row.r.depth || 0) > 0; text: app.t.outdent; iconName: "subtask"; onTriggered: tasks.outdent(row.r.key) }
        OMenuItem { visible: !!row.r.mail && !menu.many; text: app.t.open_mail; iconName: "mail"; onTriggered: tasks.openMail(row.r.key) }
        OMenuItem { visible: (row.r.note || "") !== "" && !menu.many; text: app.t.open_note; iconName: "note"; onTriggered: tasks.openNote(row.r.key) }
        OMenuItem { visible: (row.r.url || "") !== "" && !row.r.mail && !menu.many; text: app.t.open_link; iconName: "link"; onTriggered: app.openUrl(row.r.url) }
        OMenuItem { text: app.t.link_copy; iconName: "link"; onTriggered: tasks.copyLinks(row.keys) }
        OMenuItem { visible: !row.r.readonly && !menu.many; text: app.t.link_to; iconName: "note"; onTriggered: win.linkTask(row.r.key) }
        OMenuItem { visible: !row.r.readonly; text: app.t.move_to + "…"; iconName: "move"; onTriggered: win.moveTasks(row.keys) }
        OMenuItem { visible: !row.r.readonly && tasks.view.indexOf("list:") === 0 && (row.r.depth || 0) === 0; text: app.t.section_move + "…"; iconName: "listBullet"; onTriggered: win.sectionTasks(row.keys) }
        OMenuItem { visible: !row.r.readonly; text: app.t.delete_task + (menu.many ? " (" + row.keys.length + ")" : ""); iconName: "trash"; onTriggered: row.list.deleteRequested(row.keys) }
    }
}
