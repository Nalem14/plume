// The list shown: the hero (the ring of the day, or the count; the title in the list's colour), the capture
// line for a new task, which understands « Appeler Inès demain 18h !! #travail », then the tasks on a card
// (round boxes in the list's colour, the subtasks under their task, sections by day in « Programmées »).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

Rectangle {
    id: pane
    readonly property var c: theme.c
    readonly property var h: tasks.heading
    readonly property var rows: tasks.rows
    property string selected
    property string editing: ""            // the task whose title is being typed in place
    signal picked(string key)
    signal inspect(string key)
    signal deleteRequested(var keys)
    signal ornisPlan()
    signal ornisExtract()
    color: c.bg

    readonly property bool smart: !!h.smart || tasks.query !== ""
    readonly property bool canAdd: !h.readonly && tasks.view !== "completed" && tasks.view !== "mail"
    // a smart list takes the colour of its card in the side column, a list its own
    readonly property var smartTones: ({ today: c.famOrganize, scheduled: c.danger, all: c.famTools,
                                         flagged: c.saffronInk, completed: c.ok, mail: c.famCommunicate })
    readonly property color tone: tasks.query === "" && smartTones[tasks.view] !== undefined ? smartTones[tasks.view]
                                  : Colors.display(h.color || "#002FA7", theme.dark)

    function focusList() { view.forceActiveFocus(); if (view.currentIndex < 0 && rows.length) { view.currentIndex = 0; picked(rows[0].key) } }
    function focusAdd() { quick.focusField() }
    function typeAdd(text) { quick.setText(text) }
    function addInSection(name) { quick.setExtra("section", name); quick.focusField() }
    function focusView() { view.forceActiveFocus() }

    // a selection of several: Ctrl+click, Shift+click, Ctrl+A
    property var chosen: []
    property int anchor: -1
    function isChosen(key) { return chosen.indexOf(key) >= 0 }
    function clickRow(index, mod) {
        const r = rows[index]
        if (!r) return
        if (mod === "") {
            chosen = []
            anchor = index
            view.currentIndex = index
            picked(r.key)
            return
        }
        let out
        if (mod === "shift") {
            const from = anchor >= 0 ? anchor : Math.max(0, rows.findIndex(x => x.key === selected))
            out = rows.slice(Math.min(from, index), Math.max(from, index) + 1).map(x => x.key)
        } else {
            out = chosen.length ? chosen.slice() : (rows.some(x => x.key === selected) ? [selected] : [])
            const at = out.indexOf(r.key)
            if (at >= 0) out.splice(at, 1)
            else out.push(r.key)
            anchor = index
        }
        chosen = Array.from(new Set(out))
    }
    function targets() { return chosen.length ? chosen : (selected ? [selected] : []) }

    ListModel { id: rowModel }
    onRowsChanged: fill()
    property string shown: ""
    function fill() {
        const next = rows.map(r => ({ rk: r.key, section: r.section + "|" + r.sectionLabel }))
        for (let i = 0; i < next.length; i++) {
            if (i >= rowModel.count) rowModel.append(next[i])
            else if (rowModel.get(i).rk !== next[i].rk || rowModel.get(i).section !== next[i].section) rowModel.set(i, next[i])
        }
        if (rowModel.count > next.length)
            rowModel.remove(next.length, rowModel.count - next.length)
        const id = tasks.view + "|" + tasks.query
        if (id !== shown) {
            shown = id
            chosen = []
            anchor = -1
            view.positionViewAtBeginning()
        } else if (chosen.length) {
            chosen = chosen.filter(k => rows.some(r => r.key === k))
        }
        view.currentIndex = rows.findIndex(r => r.key === selected)
    }
    onSelectedChanged: view.currentIndex = rows.findIndex(r => r.key === selected)
    Component.onCompleted: fill()

    // drag to reorder (manual order, in a list): where the task would land
    property int dropAt: -1
    property int linkAt: -1                  // the task a dragged mail, note or task would be linked to
    property string dragging: ""

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- the hero: the ring of the day (or the count), the title in the list's colour, the figures ----------
        Hero {
            id: hero
            readonly property bool today: tasks.view === "today"
            readonly property int done: tasks.counts.done_today || 0
            readonly property int total: done + (tasks.counts.today || 0)
            readonly property int open: tasks.view === "completed" ? (tasks.counts.completed || 0) : pane.rows.filter(r => !r.done).length
            Layout.fillWidth: true
            Layout.leftMargin: 20; Layout.rightMargin: 20
            Layout.topMargin: 16; Layout.bottomMargin: 10
            tint: pane.tone
            kicker: today ? new Date().toLocaleDateString(Qt.locale(), "dddd d MMMM")
                  : pane.h.owner ? app.t.shared_by.replace("%1", pane.h.owner) + (pane.h.readonly ? " · " + app.t.read_only : "")
                  : app.t.app_name
            title: pane.h.title || ""
            meta: today ? app.t.done_ratio.replace("%1", done).replace("%2", total) : app.plural("tasks_count", open)
            offline: !tasks.online
            offlineText: (tasks.pending > 0 ? app.t.offline_pending.replace("%1", tasks.pending) : app.t.offline)
                         + (tasks.syncedAt ? " · " + app.t.synced_at.replace("%1", app.ago(tasks.syncedAt)) : "")
            // « Aujourd'hui »: the ring of the day, one segment per task, in the family colour once done
            // (docs/ROADMAP.md › Anneau); elsewhere the count, in the data face
            leading: Item {
                implicitWidth: 64; implicitHeight: 64
                Accessible.role: Accessible.StaticText
                Accessible.name: hero.today ? hero.meta : String(hero.open)
                Ring {
                    visible: hero.today
                    anchors.fill: parent
                    lineWidth: 6
                    drawTrack: hero.total === 0
                    separated: true
                    trackColor: pane.c.accentLine
                    segments: {
                        const out = [], n = hero.total
                        for (let i = 0; i < n; i++)
                            out.push({ from: i / n, to: (i + 1) / n, color: i < hero.done ? pane.tone : pane.c.accentLine })
                        return out
                    }
                }
                Text {
                    anchors.centerIn: parent
                    text: hero.today ? hero.done + "/" + hero.total : hero.open
                    font.family: "JetBrains Mono"; font.pixelSize: hero.today ? 16 : 26; font.weight: Font.Medium
                    font.letterSpacing: -0.5
                    color: hero.today ? pane.c.text : pane.tone
                }
            }
            OButton {
                visible: tasks.view === "today" && pane.rows.length > 1
                kind: "accent"; iconName: "ornis"; text: pane.width > 700 ? app.t.ornis_plan : ""; tip: app.t.ornis_plan
                onClicked: pane.ornisPlan()
            }
            OButton {
                id: more
                kind: "quiet"; implicitWidth: 36; iconName: "more"; tip: app.t.list_options
                onClicked: listMenu.open()
                OMenu {
                    id: listMenu
                    y: more.height + 6
                    x: more.width - width
                    implicitWidth: 290
                    heading: tasks.query !== "" ? "" : app.t.sort_by
                    OMenuItem { visible: tasks.query !== ""; text: app.t.search_done; switchable: true; on: tasks.searchDone; onTriggered: tasks.toggleSearchDone() }
                    OMenuItem { visible: tasks.view.indexOf("list:") === 0; text: app.t.sort_manual; iconName: tasks.sort === "manual" ? "check" : ""; onTriggered: tasks.setSort("manual") }
                    OMenuItem { text: app.t.sort_due; iconName: tasks.sort === "due" ? "check" : ""; onTriggered: tasks.setSort("due") }
                    OMenuItem { text: app.t.sort_priority; iconName: tasks.sort === "priority" ? "check" : ""; onTriggered: tasks.setSort("priority") }
                    OMenuItem { text: app.t.sort_title; iconName: tasks.sort === "title" ? "check" : ""; onTriggered: tasks.setSort("title") }
                    OMenuItem { text: app.t.sort_created; iconName: tasks.sort === "created" ? "check" : ""; onTriggered: tasks.setSort("created") }
                    Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                    OMenuItem { visible: tasks.view.indexOf("list:") === 0; text: app.t.show_done; switchable: true; on: tasks.showDone; onTriggered: tasks.toggleShowDone() }
                    OMenuItem {
                        visible: tasks.view.indexOf("list:") === 0 && !pane.h.readonly
                        text: app.t.clear_done; iconName: "trash"
                        onTriggered: tasks.clearCompleted(pane.h.list)
                    }
                    OMenuItem { visible: tasks.view.indexOf("list:") === 0 && !pane.h.readonly; text: app.t.section_new; iconName: "listBullet"; onTriggered: win.newSection(pane.h.list) }
                    OMenuItem { visible: !!pane.h.custom; text: app.t.smart_edit; iconName: "edit"; onTriggered: win.editSmart(tasks.smartLists.find(s => s.id === pane.h.id)) }
                    OMenuItem { visible: pane.canAdd; text: app.t.ornis_extract; iconName: "ornis"; onTriggered: pane.ornisExtract() }
                }
            }
        }

        QuickAdd {
            id: quick
            Layout.fillWidth: true
            Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 10
            visible: pane.canAdd
            tone: pane.tone
            onAdded: key => { pane.picked(key); view.positionViewAtEnd() }
        }

        // several tasks chosen: what can be done to all of them
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24; Layout.rightMargin: 14
            Layout.bottomMargin: 4
            visible: pane.chosen.length > 0
            spacing: 4
            Text {
                Layout.fillWidth: true
                text: app.plural("selected_count", pane.chosen.length)
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: pane.c.text
            }
            OButton { kind: "quiet"; height_: 28; iconName: "done"; iconSize: 16; text: app.t.mark_done; onClicked: { tasks.setDoneMany(pane.chosen, true); pane.chosen = [] } }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "flag"; iconSize: 16; tip: app.t.flag; onClicked: tasks.flagMany(pane.chosen, true) }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "today"; iconSize: 16; tip: app.t.due_today; onClicked: tasks.setDue(pane.chosen, "today") }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "sun"; iconSize: 16; tip: app.t.due_tomorrow; onClicked: tasks.setDue(pane.chosen, "tomorrow") }
            OButton {
                id: prioBtn
                kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "priority"; iconSize: 16; tip: app.t.priority_menu
                onClicked: prioMenu.open()
                OMenu {
                    id: prioMenu
                    y: prioBtn.height + 4
                    x: prioBtn.width - width
                    implicitWidth: 200
                    heading: app.t.priority_menu
                    OMenuItem { text: app.t.priority_1; onTriggered: tasks.setPriorityMany(pane.chosen, 1) }
                    OMenuItem { text: app.t.priority_5; onTriggered: tasks.setPriorityMany(pane.chosen, 5) }
                    OMenuItem { text: app.t.priority_9; onTriggered: tasks.setPriorityMany(pane.chosen, 9) }
                    OMenuItem { text: app.t.priority_0; onTriggered: tasks.setPriorityMany(pane.chosen, 0) }
                }
            }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "move"; iconSize: 16; tip: app.t.move_to; onClicked: win.moveTasks(pane.chosen) }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "trash"; iconSize: 16; danger: true; tip: app.t.delete_task; onClicked: pane.deleteRequested(pane.chosen) }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "close"; iconSize: 14; tip: app.t.select_clear; onClicked: pane.chosen = [] }
        }

        // ---- the tasks, on a card ------------------------------------------------------------------------
        Surface {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 16
            visible: pane.rows.length > 0
        ListView {
            id: view
            anchors.fill: parent
            anchors.topMargin: 4; anchors.bottomMargin: 4
            clip: true
            model: rowModel
            currentIndex: -1
            keyNavigationEnabled: true
            highlightMoveDuration: 0
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            section.property: "section"
            section.criteria: ViewSection.FullString
            section.delegate: Item {
                id: head
                required property string section
                readonly property string label: section.split("|").slice(1).join("|")
                readonly property var first: pane.rows.find(r => r.section + "|" + r.sectionLabel === section) || {}
                // a section of the list (not « Terminées »): add a task in it, rename, order, delete; tasks dropped on it go in
                readonly property bool own: tasks.view.indexOf("list:") === 0 && section.charAt(0) === "s" && !pane.h.readonly
                width: ListView.view.width
                height: label === "" ? 0 : 44
                visible: label !== ""
                HoverHandler { id: headHover }
                Rectangle {
                    visible: headDrop.containsDrag
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 14; rightMargin: 14 }
                    height: 30; radius: 8; color: pane.c.tint
                }
                Text {
                    id: headText
                    x: 20; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                    text: parent.label
                    textFormat: Text.PlainText
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                    font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                    color: parent.first.sectionColor ? Colors.display(parent.first.sectionColor, theme.dark) : pane.c.muted
                }
                Row {
                    visible: head.own && (headHover.hovered || headMenu.opened)
                    anchors { right: parent.right; rightMargin: 18; bottom: parent.bottom; bottomMargin: 2 }
                    spacing: 2
                    OButton { kind: "quiet"; implicitWidth: 28; height_: 26; iconName: "plus"; iconSize: 14; tip: app.t.section_add_task
                              onClicked: pane.addInSection(head.label) }
                    OButton {
                        id: headMore
                        kind: "quiet"; implicitWidth: 28; height_: 26; iconName: "more"; iconSize: 14; tip: app.t.list_options
                        onClicked: headMenu.open()
                        OMenu {
                            id: headMenu
                            y: headMore.height + 4
                            x: headMore.width - width
                            implicitWidth: 240
                            OMenuItem { text: app.t.section_rename; iconName: "edit"; onTriggered: win.renameSection(pane.h.list, head.label) }
                            OMenuItem { text: app.t.list_up; iconName: "chevronLeft"; onTriggered: tasks.nudgeSection(pane.h.list, head.label, -1) }
                            OMenuItem { text: app.t.list_down; iconName: "chevronRight"; onTriggered: tasks.nudgeSection(pane.h.list, head.label, 1) }
                            OMenuItem { text: app.t.section_delete; iconName: "trash"; onTriggered: tasks.deleteSection(pane.h.list, head.label) }
                        }
                    }
                }
                DropArea {
                    id: headDrop
                    anchors.fill: parent
                    keys: ["orneos/tasks"]
                    enabled: head.own
                    onDropped: drag => { tasks.afterDrag("setSection", [String(drag.getDataAsString("orneos/tasks")).split(","), head.label]); drag.accept() }
                }
            }
            onCurrentIndexChanged: {
                if (activeFocus && currentIndex >= 0 && currentIndex < pane.rows.length && pane.rows[currentIndex].key !== pane.selected)
                    pane.picked(pane.rows[currentIndex].key)
            }
            Keys.onPressed: event => {
                const key = pane.selected.indexOf("~") === 0 ? "" : pane.selected
                const ctrl = event.modifiers & Qt.ControlModifier, alt = event.modifiers & Qt.AltModifier
                if (event.key === Qt.Key_A && ctrl) { pane.chosen = pane.rows.filter(r => !r.empty).map(r => r.key); event.accepted = true }
                else if (!key) return
                else if (event.key === Qt.Key_Space) { tasks.toggleDone(key); event.accepted = true }
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { pane.editing = key; event.accepted = true }
                else if (event.key === Qt.Key_Delete) { pane.deleteRequested(pane.targets()); event.accepted = true }
                else if (event.key === Qt.Key_Tab) { tasks.indent(key); event.accepted = true }
                else if (event.key === Qt.Key_Backtab) { tasks.outdent(key); event.accepted = true }
                else if (alt && event.key === Qt.Key_Up) { tasks.nudge(key, -1); event.accepted = true }
                else if (alt && event.key === Qt.Key_Down) { tasks.nudge(key, 1); event.accepted = true }
                else if (ctrl && event.key === Qt.Key_I) { pane.inspect(key); event.accepted = true }
                else if (event.key === Qt.Key_Escape && pane.chosen.length) { pane.chosen = []; event.accepted = true }
            }

            delegate: TaskRow {
                width: ListView.view.width
                list: pane
            }

            // a mail (Plume), a note (Notes) or a task dragged here: onto a task, linked to it; under the tasks,
            // a new task named after it, linked to it
            DropArea {
                anchors.fill: parent
                keys: ["application/x-orneos-link"]
                onPositionChanged: drag => {
                    const i = view.indexAt(drag.x, drag.y + view.contentY)
                    pane.linkAt = i >= 0 && !pane.rows[i].readonly ? i : -1
                }
                onExited: pane.linkAt = -1
                onDropped: drop => {
                    const payload = drop.getDataAsString("application/x-orneos-link")
                    const target = pane.linkAt
                    pane.linkAt = -1
                    if (target >= 0) {
                        if (tasks.addLinks(pane.rows[target].key, payload)) app.toast(app.t.link_added)
                    } else if (pane.canAdd) {
                        tasks.newFromLinks(payload)
                    }
                    drop.acceptProposedAction()
                }
            }
            // dropped among the tasks of a list: the manual order changes
            DropArea {
                anchors.fill: parent
                keys: ["orneos/tasks"]
                enabled: tasks.view.indexOf("list:") === 0 && !pane.h.readonly
                onPositionChanged: drag => pane.dropAt = view.indexAt(drag.x, drag.y + view.contentY)
                onExited: pane.dropAt = -1
                onDropped: drag => {
                    const keys = String(drag.getDataAsString("orneos/tasks")).split(",")
                    const row = pane.dropAt >= 0 ? pane.rows[pane.dropAt] : null
                    pane.dropAt = -1
                    // after the drag (dragguard.py): rebuilt during it, the dragged row would be gone under Qt (macOS)
                    if (row && row.empty) tasks.afterDrag("setSection", [keys, row.sectionLabel])       // an empty section: in it
                    else if (keys.indexOf(row ? row.key : "") < 0)
                        for (const k of keys) tasks.afterDrag("reorder", [k, row ? row.key : ""])
                    drag.accept()
                }
            }

            footer: Item {
                width: ListView.view.width
                height: 40
                // a click under the tasks starts a new one
                TapHandler { enabled: pane.canAdd; onTapped: pane.focusAdd() }
            }
        }
        }

        // ---- nothing here --------------------------------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: pane.rows.length === 0
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(420, parent.width - 48)
                spacing: 10
                Icon { Layout.alignment: Qt.AlignHCenter; name: tasks.query !== "" ? "search" : (pane.h.icon || "done"); size: 34; color: pane.c.faint }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: tasks.query !== "" ? app.t.empty_search
                        : tasks.view.indexOf("smart:") === 0 ? app.t.empty_smart : (app.t["empty_" + tasks.view] || app.t.empty_list)
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15
                    color: pane.c.muted
                    lineHeight: 1.3
                }
            }
        }
    }
}
