// The right side of Activité when no conversation is shown: the task picked that has not run yet (its card), or
// the dashboard: what runs now (goals, research, Code), what finished lately, the scheduled tasks. A task is created by asking Ornis (« every morning at 8… »).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: page
    signal askRequested(string text)
    signal draftRequested(string text)
    readonly property var c: theme.c
    readonly property var task: win.task
    // the rows of the dashboard: {kind, id, title, sub, status, unread, progress (0..1 or -1)}
    readonly property var running: {
        const out = code.busy && code.session
            ? [{ kind: "code", id: code.session, folder: code.folder, title: code.title || app.t.code_new,
                 sub: app.t.mode_code + " · " + (code.folderName || ""), status: "running", unread: 0, progress: -1 }] : []
        return out.concat(chat.jobs.filter(j => j.status === "running").map(page.jobRow))
    }
    readonly property var recent: chat.jobs.filter(j => j.status !== "running").slice(0, 6).map(page.jobRow)
    readonly property var planned: chat.scheduled.map(t => ({ kind: "task", id: t.id, title: t.prompt, sub: t.repeat + " · " + t.last,
                                                             status: "", unread: t.unread || 0, progress: -1 }))
    function jobRow(j) {
        const total = (j.steps || []).length
        const done = (j.steps || []).filter(x => x.done).length
        return { kind: "job", id: j.session, title: j.title, status: j.status, unread: j.unread || 0,
                 sub: (j.research ? app.t.research_mode : app.t.mode_goal) + " · "
                      + (j.status === "running" && total ? app.t.activity_steps.replace("%1", Math.min(done + 1, total)).replace("%2", total) : j.label),
                 progress: j.status === "running" && total ? done / total : -1 }
    }
    function openRow(r) {
        if (r.kind === "code") win.openCode(r.folder, r.id)
        else if (r.kind === "job") win.openJob(r.id)
        else win.openTask(r.id)
    }

    component Section: ColumnLayout {
        id: sec
        property string title
        property var rows: []
        property string empty: ""
        visible: !page.task && (rows.length > 0 || empty !== "")
        Layout.fillWidth: true
        Layout.topMargin: 6
        spacing: 6
        Text {
            text: sec.title
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            color: page.c.muted
        }
        Text {
            visible: sec.rows.length === 0
            Layout.fillWidth: true
            text: sec.empty
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: page.c.faint
        }
        Repeater {
            model: sec.rows
            AbstractButton {
                id: row
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: rowCol.implicitHeight + 22
                hoverEnabled: true
                onClicked: page.openRow(modelData)
                Accessible.name: modelData.title + ", " + modelData.sub
                background: Rectangle {
                    radius: 10
                    color: row.hovered ? page.c.hover : page.c.card
                    border.width: row.visualFocus ? 2 : 1
                    border.color: row.visualFocus ? page.c.saffron : page.c.line
                }
                contentItem: RowLayout {
                    spacing: 12
                    Item { implicitWidth: 2 }
                    Icon {
                        name: row.modelData.kind === "code" ? "code" : row.modelData.kind === "task" ? "repeat"
                              : row.modelData.status === "running" ? "ornis" : row.modelData.status === "done" ? "done" : "flag"
                        size: 18
                        color: row.modelData.status === "running" ? page.c.famCommunicate : page.c.muted
                    }
                    ColumnLayout {
                        id: rowCol
                        Layout.fillWidth: true
                        spacing: 3
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.title
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14
                            font.weight: row.modelData.unread > 0 ? Font.DemiBold : Font.Medium
                            color: page.c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.sub
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: page.c.muted
                        }
                        Rectangle {            // how far a goal has gone (its plan's steps)
                            visible: row.modelData.progress >= 0
                            Layout.fillWidth: true
                            Layout.topMargin: 3
                            implicitHeight: 4; radius: 2
                            color: page.c.hairline
                            Rectangle { width: parent.width * Math.max(0.04, row.modelData.progress); height: parent.height; radius: 2; color: page.c.action }
                        }
                    }
                    BusyIndicator {
                        visible: row.modelData.status === "running"
                        running: visible
                        implicitWidth: 18; implicitHeight: 18
                    }
                    Rectangle {
                        visible: row.modelData.unread > 0
                        implicitWidth: 8; implicitHeight: 8; radius: 4
                        color: page.c.action
                    }
                    Icon { name: "chevronRight"; size: 13; color: page.c.faint; Layout.rightMargin: 10 }
                }
            }
        }
    }
    color: c.bg

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: page.c.chrome
            // the sidebar folded: the way back to it, as in a conversation
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: win.sidebarShown ? 20 : 10; anchors.rightMargin: 12
                spacing: 6
                OButton {
                    visible: !win.sidebarShown
                    kind: "quiet"; iconName: "sidebar"; tip: app.t.show_sidebar + "  (Ctrl+B)"
                    onClicked: win.toggleSidebar()
                }
                Text {
                    Layout.fillWidth: true
                    text: page.task ? page.task.prompt : app.t.mode_tasks
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                    color: page.c.text
                }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: page.c.line }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ColumnLayout {
                x: (parent.width - width) / 2
                width: Math.min(app.readingWidth, page.width - 64)
                spacing: 14
                Item { implicitHeight: 10 }
                TaskCard {                   // a task that has not run yet: no conversation, its card alone
                    visible: !!page.task
                    compact: false
                    Layout.fillWidth: true
                    task: page.task || ({})
                    onDeleteRequested: id => win.deleteTask(id)
                }
                // nothing picked: what Ornis does in the background, at a glance (running, finished, scheduled)
                Text {
                    visible: !page.task
                    Layout.fillWidth: true
                    text: app.t.activity_lead
                    wrapMode: Text.Wrap
                    lineHeight: 1.3
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: page.c.muted
                }
                Section { title: app.t.activity_running; rows: page.running; empty: app.t.activity_none_running }
                Section { title: app.t.activity_recent; rows: page.recent }
                Section { title: app.t.scheduled_section; rows: page.planned; empty: app.t.scheduled_lead }
                OButton {
                    visible: !page.task
                    kind: chat.scheduled.length ? "secondary" : "accent"; iconName: "repeat"
                    text: app.t.activity_new_task
                    onClicked: page.draftRequested(app.t.suggest_6)     // written in a new conversation, sent by the user
                }
                Item { implicitHeight: 24 }
            }
        }
    }
}
