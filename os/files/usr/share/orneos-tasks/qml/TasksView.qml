// Tâches: the sidebar (smart lists, lists, tags), the tasks of the one shown, and the details of a task
// beside them. The window of Tâches (Main.qml) and the Tâches module of Plume both show this view.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"

Item {
    id: win
    readonly property var c: theme.c
    readonly property bool wide: width >= 1100
    readonly property bool ready: app.connected && tasks.state === "ready"
    // shortcuts only while the view is the one shown (Plume keeps its other modules in the same window)
    readonly property bool shown: ready && visible
    // in Plume, Ctrl+1… switch modules: the smart lists keep their place in the sidebar only
    property bool viewKeys: true
    property string selected: ""
    property string inspected: ""
    property alias toast: toast
    signal raiseWanted()
    signal closeWanted()

    function bringUp() { raiseWanted() }
    function select(key, inspect) {
        if (!key) return
        const d = tasks.detail(key)
        if (!d.key) return
        if (!tasks.rows.some(r => r.key === key)) {
            tasks.setQuery("")
            sidebar.setSearch("")
            tasks.setView("list:" + d.list)
        }
        selected = key
        if (inspect) inspected = key
    }
    function remove(keys) {
        if (!keys.length) return
        if (keys.indexOf(inspected) >= 0) inspected = ""
        tasks.delete(keys)
        list.chosen = []
    }
    function moveTasks(keys) { moveDialog.openFor(keys) }
    // « Lier à… »: a note, another task or a mail, linked to this task
    function linkTask(key) {
        linkPicker.target = key
        linkPicker.exclude = tasks.dragData([key])["application/x-orneos-link"] ? JSON.parse(tasks.dragData([key])["application/x-orneos-link"]).map(i => i.url) : []
        linkPicker.start()
    }
    function openSettings() { settings.open() }
    function sectionTasks(keys) { sectionDialog.openFor(keys) }
    function newSection(href) {
        nameDialog.ask(app.t.section_new, app.t.section_name, "", app.t.create, name => tasks.addSection(href, name))
    }
    function renameSection(href, old) {
        nameDialog.ask(app.t.section_rename, app.t.section_name, old, app.t.save, name => tasks.renameSection(href, old, name))
    }
    function editSmart(rule) { smartDialog.ask(rule) }

    Connections {
        target: app
        function onToast(message) { toast.show(message) }
        function onRaiseRequested() { win.bringUp() }
        function onShowRequested(ref) { const k = tasks.resolve(ref); if (k) win.select(k, true) }
        function onActionRequested(action, value) {
            if (action === "new") { win.bringUp(); list.focusAdd() }
            else if (action === "view") tasks.setView(value)
            else if (action === "search") sidebar.setSearch(value)
        }
    }
    Connections {
        target: tasks
        function onDone(what, ok, message) {
            if (!ok) problem.tell(message)
            else if (what === "deleted") toast.show(message, app.t.undo, () => tasks.undoDelete(), 6)
            else if (what === "completed") toast.show(message, app.t.undo, () => tasks.undoDone(), 6)
            else if (message) toast.show(message)
        }
        function onViewChanged() { list.editing = "" }
    }

    Shortcut { sequence: "Ctrl+N"; enabled: win.shown; onActivated: list.focusAdd() }
    Shortcut { sequence: "Ctrl+Shift+N"; enabled: win.shown; onActivated: listDialog.ask(null) }
    Shortcut { sequence: "Ctrl+F"; enabled: win.shown; onActivated: sidebar.focusSearch() }
    Shortcut { sequence: "Ctrl+,"; enabled: win.shown; onActivated: settings.open() }
    Shortcut { sequence: "Ctrl+1"; enabled: win.shown && win.viewKeys; onActivated: tasks.setView("today") }
    Shortcut { sequence: "Ctrl+2"; enabled: win.shown && win.viewKeys; onActivated: tasks.setView("scheduled") }
    Shortcut { sequence: "Ctrl+3"; enabled: win.shown && win.viewKeys; onActivated: tasks.setView("all") }
    Shortcut { sequence: "Ctrl+4"; enabled: win.shown && win.viewKeys; onActivated: tasks.setView("flagged") }
    Shortcut { sequence: "Ctrl+Shift+F"; enabled: win.shown && win.selected !== ""; onActivated: tasks.toggleFlag(win.selected) }
    Shortcut { sequence: "Ctrl+T"; enabled: win.shown && win.selected !== ""; onActivated: tasks.setDue(list.targets(), "today") }
    Shortcut { sequence: "Ctrl+W"; enabled: win.visible; onActivated: win.closeWanted() }
    Shortcut { sequence: "F5"; enabled: win.shown; onActivated: tasks.refresh() }
    Shortcut { sequence: "Ctrl+/"; enabled: win.shown; onActivated: shortcutsDialog.open() }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: win.ready

        // the family band down the window's edge (in Plume, its rail marks the module instead)
        Band { Layout.fillHeight: true; visible: win.viewKeys; color: win.c.famOrganize }
        Sidebar {
            id: sidebar
            Layout.fillHeight: true
            Layout.preferredWidth: win.wide ? 290 : 256
            onSettingsRequested: settings.open()
            onToList: list.focusList()
            onNewList: listDialog.ask(null)
            onEditList: l => listDialog.ask(l)
            onShareList: l => shareDialog.openFor(l)
            onNewSmart: smartDialog.ask(null)
            onEditSmart: rule => smartDialog.ask(rule)
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            TaskList {
                id: list
                anchors.fill: parent
                selected: win.selected
                onPicked: key => { win.selected = key; if (win.inspected) win.inspected = key }
                onInspect: key => { win.selected = key; win.inspected = win.inspected === key ? "" : key }
                onDeleteRequested: keys => win.remove(keys)
                onOrnisPlan: ornisDialog.start("plan", "")
                onOrnisExtract: ornisDialog.start("extract", "")
            }
        }
        Inspector {
            Layout.fillHeight: true
            Layout.preferredWidth: win.wide ? 370 : 330
            visible: win.inspected !== ""
            key: win.inspected
            onClosed: win.inspected = ""
            onDeleteRequested: keys => win.remove(keys)
            onBreakdown: key => ornisDialog.start("breakdown", key)
        }
    }

    EmptyState {
        anchors.fill: parent
        visible: !app.connected
        iconName: "checklist"
        title: app.t.welcome_title
        lead: app.t.welcome_lead
        actionText: app.t.welcome_action
        onActivated: app.openConnect()
    }
    Rectangle {
        anchors.fill: parent
        visible: app.connected && tasks.state !== "ready"
        color: win.c.bg
        Skeleton { anchors.fill: parent; anchors.margins: 28; visible: tasks.state === "loading"; tone: theme.c.line; rows: 8; Accessible.name: app.t.loading }
        EmptyState {
            anchors.fill: parent
            visible: tasks.state === "offline_first" || tasks.state === "error_first"
            iconName: tasks.state === "offline_first" ? "offline" : "warning"
            title: tasks.state === "offline_first" ? app.t.first_offline_title : app.t.first_error_title
            lead: tasks.state === "offline_first" ? app.t.first_offline_lead : app.t.first_error_lead
            actionText: app.t.retry
            actionIcon: "refresh"
            onActivated: tasks.refresh()
        }
    }

    Toast { id: toast }
    ProblemDialog { id: problem }
    ListDialog { id: listDialog }
    MoveDialog { id: moveDialog }
    LinkPicker {
        id: linkPicker
        property string target
        search: q => tasks.linkCandidates(q)
        onPicked: item => { if (tasks.addLinks(target, JSON.stringify([item]))) app.toast(app.t.link_added) }
    }
    OrnisDialog { id: ornisDialog }
    RepeatDialog { id: repeatDialog }
    ReminderDialog { id: reminderDialog }
    ListShareDialog { id: shareDialog }
    NameDialog { id: nameDialog }
    SectionDialog { id: sectionDialog }
    SmartListDialog { id: smartDialog }
    ShortcutsDialog { id: shortcutsDialog; viewKeys: win.viewKeys }
    SettingsDialog { id: settings }
}
