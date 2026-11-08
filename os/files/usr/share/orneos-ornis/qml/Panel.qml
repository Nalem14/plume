// Ornis beside a module of Plume (Ctrl+J), as the assistants of other mail apps: the real agent, the same
// conversations as the Ornis module (one Chat for both: a conversation started here is there, « Open in Ornis »).
// What the module has open (a message, an event, a contact) goes with the next question (chat.setAbout), shown as
// a badge in the box. The conversation is the Ornis module's own (Conversation.qml, panel: true); this file gives
// it what it asks of its view (win: new, goal, project…) without a sidebar.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: win
    readonly property var c: theme.c
    readonly property bool sidebarShown: true      // nothing to show again: the panel has its own header
    readonly property bool wide: false
    readonly property bool ready: app.connected && chat.state === "ready"
    property var ideas: []                         // the module's suggestions about what it has open
    property alias toast: toast
    signal closeRequested()
    signal expandRequested()
    color: c.bg

    function focusInput() { conversation.focusInput() }
    function newChat() { chat.newChat(); conversation.focusInput() }
    function ask(text) { chat.newChat(); chat.send(text) }
    function startCode() { expandRequested() }      // Code needs the whole window
    function toggleSidebar() { }
    function openCommands() { commandsDialog.open() }
    function openProfile() { profileDialog.open() }
    function openProject(pid) { expandRequested() }
    function createProject(session) { expandRequested() }
    function deleteTask(id) { chat.deleteScheduled(id) }
    function showWorkPlans(kind) {
        const other = kind === "code" || kind === "think"
        workDialog.ask(other ? app.t[kind + "_plus_title"] : kind === "research" ? app.t.research_plus_title : app.t.work_plus_title,
                       other ? app.t[kind + "_plus_text"] : kind === "research" ? app.t.research_plus_text : app.t.work_plus_text,
                       [{ id: "cancel", text: app.t.cancel }, { id: "plans", text: app.t.work_see_plans, kind: "primary" }],
                       () => app.openPlans())
    }
    function lowDialog() {
        workDialog.ask(app.t.work_low_title, app.t.work_low_text,
                       [{ id: "cancel", text: app.t.work_wait }, { id: "extra", text: app.t.work_extra, kind: "primary" }],
                       () => app.openExtra())
    }
    function askWork(text) {
        const e = chat.workEstimate
        const research = chat.workKind === "research"
        if (e.allowed === false) { showWorkPlans(chat.workKind); return }
        if (e.enough === false) { lowDialog(); return }
        const lead = e.lowPercent ? app.t.work_estimate_text.replace("%1", e.lowPercent).replace("%2", e.highPercent) : ""
        workDialog.ask(research ? app.t.research_estimate_title : app.t.work_estimate_title, lead,
                       [{ id: "cancel", text: app.t.cancel }, { id: "go", text: research ? app.t.research_start : app.t.work_start, kind: "primary" }],
                       () => { conversation.clearComposer(); chat.sendWork(text) })
    }
    function resumeWork() {
        chat.loadEstimate()
        const e = chat.workEstimate
        if (e.remaining !== undefined && e.remaining !== null && e.remaining < 5000) { lowDialog(); return }
        chat.resumeWork()
    }

    Connections {
        target: chat
        function onProblem(message) { if (win.visible) toast.show(message) }
    }

    Rectangle { anchors.left: parent.left; width: 1; height: parent.height; color: win.c.line; z: 2 }

    Conversation {
        id: conversation
        anchors.fill: parent
        anchors.leftMargin: 1
        visible: win.ready
        panel: true
        panelIdeas: win.ideas
        onCloseRequested: win.closeRequested()
        onExpandRequested: win.expandRequested()
    }
    EmptyState {
        anchors.fill: parent
        visible: !app.connected
        iconName: "sparkle"
        title: app.t.welcome_title
        lead: app.t.welcome_lead
        actionText: app.t.welcome_action
        onActivated: app.openConnect()
    }
    Skeleton { anchors.fill: parent; anchors.margins: 20; visible: app.connected && chat.state === "loading"; tone: theme.c.line; lead: false; rows: 4 }

    ChoiceDialog { id: workDialog }
    CommandsDialog { id: commandsDialog }
    ProfileDialog { id: profileDialog }
    Toast { id: toast }
}
