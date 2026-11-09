// Ornis: the conversations on the left (search, scheduled tasks, today's allowance, settings), the open one on the
// right. Signed out or loading for the first time, it shows only that state. The window of Ornis (Main.qml) and
// the Ornis module of Plume both show this view.
// One menu serves every conversation (the « … » of a row or of the header, a right click): pin, rename, copy,
// Notes, export, the cloud, delete. A deletion is undone from the toast, the cloud only follows afterwards.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window
import "components"

Item {
    id: win
    readonly property var c: theme.c
    readonly property bool wide: width >= 980
    readonly property bool ready: app.connected && chat.state === "ready"
    // shortcuts only while the view is the one shown (Plume keeps its other modules in the same window)
    readonly property bool shown: ready && visible
    // its own window (Plume sets it to false: its rail marks the module)
    property bool viewKeys: true
    // the column folds by itself in a narrow window (its button still opens it there, until a choice is made)
    readonly property bool roomy: width >= 760
    property bool peek: false
    readonly property bool sidebarShown: roomy ? app.prefs.sidebar !== false : peek
    property string view: "chat"          // chat | scheduled | code | project | group (a group of Code bots)
    property alias toast: toast
    signal raiseWanted()

    function bringUp() { raiseWanted() }
    // Discussions | Tâches (the switch atop the list): the conversations, or the tasks Ornis runs on its own. A task
    // shows its conversation (each run's answer) under its card; going back to Discussions opens the last one again.
    property string mode: "chats"         // chats | projects | tasks
    // the list on the left: Chat or Code (Activité is a view over it, it does not replace it)
    property string listMode: "chats"
    onModeChanged: if (mode !== "tasks") listMode = mode
    property string taskId: ""            // the task shown in the Tasks list
    property string lastChat: ""          // the conversation to come back to from Tasks
    readonly property var task: chat.scheduled.find(t => t.id === taskId) || null
    function openChat(id) {
        const owner = chat.scheduled.find(t => t.session && t.session === id)   // a task's conversation (a notification)
        if (owner) { openTask(owner.id); return }
        if (mode !== "projects") mode = "chats"           // a conversation opened from Projects stays in Projects
        view = "chat"; lastChat = id || ""; peek = false
        chat.open(id); conversation.focusInput()
    }
    function newChat() {
        peek = false
        if (mode === "projects" || mode === "tasks" && listMode === "projects") { startCode(); return }      // the Code tab: a new Code session, in the personal folder
        mode = "chats"; view = "chat"; lastChat = ""; chat.newChat(); conversation.focusInput()
    }
    // Code: Ornis works in a folder of the computer (its conversations stay here)
    // Code is part of the paid plans (the cloud refuses its model to a free one): the plans instead
    function codeLocked() {
        if (chat.paid) return false
        showWorkPlans("code")
        return true
    }
    function openCode(folder, session) { if (codeLocked()) return; mode = "projects"; view = "code"; peek = false; bots.closeGroup(); code.open(folder, session) }
    // a group of bots: the room where they answer together (Code › Bots › Groupes)
    function openGroup(id) { if (codeLocked()) return; mode = "projects"; view = "group"; peek = false; sidebar.codeTab = "bots"; bots.openGroup(id) }
    function newCode(folder) {
        if (codeLocked()) return
        if (!folder) folder = code.homeFolder          // no folder chosen: the personal folder (as Claude Code's « Cet ordinateur »)
        mode = "projects"; view = "code"; peek = false; bots.closeGroup(); code.newIn(folder); codeView.focusInput()
    }
    function showCode() {
        if (codeLocked()) return
        mode = "projects"
        const last = code.recent.length ? code.recent[0] : null
        // the conversation already open (Ornis may be working in it) is shown again as it is: reopening it
        // cancelled the turn and replayed it under the text still streaming (« LetLet… », 04/11)
        if (code.folder) { view = "code"; return }
        if (last) openCode(last.folder, last.id)
        else if (app.workspace) newCode(app.workspace)
        else view = "code"
    }
    // « Nouvelle session » (atop the list, Ctrl+N): outside any project, in the personal folder (as Claude Code's
    // « Cet ordinateur »); a folder's own « + » in the list opens one in that folder
    function startCode() { newCode("") }
    // a new conversation in a project: its folder is the workspace, nothing else is moved
    function newChatIn(path) { if (mode === "tasks") mode = "chats"; view = "chat"; lastChat = ""; chat.newChatIn(path); conversation.focusInput() }
    function ask(text) { newChat(); chat.send(text) }
    // ---- the Work mode's projects (instructions, folder, conversations), as in ChatGPT and Claude -----------------
    function openProject(pid) { peek = false; mode = "chats"; view = "project"; projects.open(pid); projectView.focusInput() }
    function createProject(session) { projectDialog.create(session || "") }
    function editProject(p) { projectDialog.edit(p) }
    function deleteProject(p) {
        workDialog.ask(app.t.project_delete_title.replace("%1", p.name), app.t.project_delete_text,
                       [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.project_delete, kind: "danger" }],
                       () => { projects.remove(p.id); if (view === "project") { view = "chat"; chat.open(lastChat) } })
    }
    function openPlus() { conversation.openPlus() }
    function openCommands() { commandsDialog.open() }
    function openProfile() { profileDialog.open() }
    function openEnvironment() { conversation.openEnvironment() }
    function showChats() {
        mode = "chats"; view = "chat"
        if (chat.currentTask !== "") chat.open(lastChat)
        conversation.focusInput()
    }
    function showProjects() {
        mode = "projects"; view = "chat"
        if (chat.currentTask !== "") chat.open(lastChat)
        conversation.focusInput()
    }
    function showTasks() {
        peek = false
        if (mode !== "tasks" && chat.currentTask === "") lastChat = chat.current
        mode = "tasks"
        chat.loadJobs()
        chat.loadScheduled()
        if (taskId.startsWith("job:") && chat.jobs.some(j => "job:" + j.session === taskId)) openJob(taskId.slice(4))
        else if (task) openTask(taskId); else view = "scheduled"
    }
    // ---- the Work mode: what a job takes before it starts, a free plan's way to it, a stopped job resumed ----------
    function openJob(sid) {
        peek = false
        if (mode !== "tasks" && chat.currentTask === "" && !chat.jobs.some(j => j.session === chat.current)) lastChat = chat.current
        mode = "tasks"; taskId = "job:" + sid; view = "chat"
        chat.open(sid); conversation.focusInput()
    }
    function showWorkPlans(kind) {
        const research = kind === "research"
        const other = kind === "code" || kind === "think"          // Code, the reasoning: paid plans as well
        workDialog.ask(other ? app.t[kind + "_plus_title"] : research ? app.t.research_plus_title : app.t.work_plus_title,
                       other ? app.t[kind + "_plus_text"] : research ? app.t.research_plus_text : app.t.work_plus_text,
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
    function openTask(id) {
        peek = false
        if (mode !== "tasks" && chat.currentTask === "") lastChat = chat.current
        mode = "tasks"; taskId = id
        const t = chat.scheduled.find(x => x.id === id)
        if (t && t.session) { view = "chat"; chat.open(t.session) } else view = "scheduled"
    }
    function showScheduled() { showTasks() }
    function toggleMode() { if (mode === "tasks") showChats(); else showTasks() }
    function deleteTask(id) {
        confirmDeleteTask.ask(app.t.task_delete_title, app.t.task_delete_text,
                              [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.task_delete, kind: "danger" }],
                              () => { chat.deleteScheduled(id); if (taskId === id) { taskId = ""; view = "scheduled" } })
    }
    function remove(id) { chat.remove(id) }
    function toggleSidebar() { if (roomy) app.setPref("sidebar", !sidebarShown); else peek = !peek }
    function lastAnswer() {
        const all = chat.messages
        for (let i = all.length - 1; i >= 0; i--)
            if (all[i].role !== "human" && all[i].content) return all[i]
        return null
    }
    function copyLast(code) {
        const m = lastAnswer()
        let text = m ? m.content : ""
        if (code) {
            const blocks = [...text.matchAll(/```[^\n]*\n([\s\S]*?)```/g)]
            text = blocks.length ? blocks[blocks.length - 1][1].replace(/\n$/, "") : ""
        }
        if (!text) { toast.show(code ? app.t.no_code : app.t.no_answer); return }
        app.copy(text)
        toast.show(app.t.copied)
    }
    function readLast() {
        const m = lastAnswer()
        if (m) chat.voice.speak(String(m.id), m.content)
        else toast.show(app.t.no_answer)
    }
    // a screen reader hears the answer once it is written (the text streams in silently before)
    function announce(text) {
        try { conversation.Accessible.announce(text) } catch (e) { }
    }

    Connections {
        target: app
        function onToast(message) { toast.show(message) }
        function onRaiseRequested() { win.bringUp() }
        function onNotificationClicked(id) { win.bringUp(); if (id) win.openChat(id) }
        function onActionRequested(action, value) {
            if (action === "session") win.openChat(value)
            else if (action === "ask") win.ask(value)
            else if (action === "draft") { win.newChat(); conversation.setComposerText(value) }
            else if (action === "new") win.newChat()
            else if (action === "scheduled") win.showScheduled()
            else if (action === "code") win.showCode()
            else if (action === "mode") { win.mode = "chats"; win.newChat(); conversation.pickMode(value) }
        }
    }
    Connections {
        target: cron
        function onManageRequested(id) { cronSheet.openFor(id) }
        function onOpenSession(folder, session) { win.openCode(folder, session) }
        function onShowCode() { win.showCode() }
        function onToast(message) {
            const undoable = / — /.test(message) && /Annuler|Undo|Rückgängig/i.test(message)
            if (undoable) toast.show(message.replace(/\s*—\s*.*$/, ""), app.t.undo, () => cron.undoLast(), 8)
            else toast.show(message)
        }
        function onConsentChanged() {
            if (!cron.waiting) { cronConsent.close(); return }
            const c = cron.consent
            cronConsent.title = c.title || app.t.cron_section
            cronConsentLead.text = c.detail || ""
            cronConsent.open()
        }
        function onFinished(taskId, status, summary) {
            // notification already fired from Python when the window is in the background
        }
    }
    Connections {
        target: chat
        function onProblem(message) { toast.show(message) }
        function onExported(message) { toast.show(message) }
        function onRemoved(id, title) { toast.show(app.t.deleted, app.t.undo, () => chat.undoRemove(id), 7) }
        function onArchivedOne(id, title) { toast.show(app.t.archived_toast, app.t.undo, () => chat.archive(id, false), 7) }
        function onScheduledChanged() {
            if (win.mode === "tasks" && win.view === "scheduled" && win.task && win.task.session) {
                win.view = "chat"
                chat.open(win.task.session)
            }
        }
        function onReplied() {
            if (win.visible && win.Window.active && win.shown) {
                const m = chat.pending.length ? null : win.lastAnswer()
                win.announce(chat.pending.length ? app.t.pending_ready + " : " + chat.pending[0].title
                                                 : app.t.reply_ready + (m ? " : " + chat.voice.plainText(m.content) : ""))
            }
            if ((win.visible && win.Window.active) || chat.panelShown || !app.prefs.notify || !chat.current) return
            const last = chat.messages.length ? chat.messages[chat.messages.length - 1] : null
            app.notify(chat.pending.length ? app.t.pending_ready : chat.title,
                       chat.pending.length ? chat.pending[0].title : (last ? last.content : app.t.reply_ready), chat.current)
        }
    }

    Shortcut { sequence: "Ctrl+N"; enabled: win.shown; onActivated: win.newChat() }
    Shortcut { sequence: "Ctrl+F"; enabled: win.shown; onActivated: { if (!win.sidebarShown) win.toggleSidebar(); sidebar.focusSearch() } }
    Shortcut { sequence: "Ctrl+B"; enabled: win.shown; onActivated: win.toggleSidebar() }
    Shortcut { sequence: "Ctrl+Shift+S"; enabled: win.shown; onActivated: win.toggleMode() }
    Shortcut { sequences: ["Ctrl+,", StandardKey.Preferences]; enabled: win.shown; onActivated: settings.open() }
    Shortcut { sequence: "Esc"; enabled: win.shown && win.view !== "code" && chat.busy; onActivated: chat.stop() }
    Shortcut { sequence: "F5"; enabled: win.shown; onActivated: chat.refresh(false) }
    // the same keys as the cloud and ChatGPT where they have one (list: shortcuts.js)
    Shortcut { sequence: "Ctrl+Shift+O"; enabled: win.shown; onActivated: win.newChat() }
    Shortcut { sequence: "Shift+Esc"; enabled: win.shown && win.view === "chat"; onActivated: conversation.focusInput() }
    Shortcut { sequence: "Ctrl+Shift+C"; enabled: win.shown && win.view === "chat"; onActivated: win.copyLast(false) }
    Shortcut { sequence: "Ctrl+Shift+;"; enabled: win.shown && win.view === "chat"; onActivated: win.copyLast(true) }
    Shortcut { sequence: "Ctrl+Shift+L"; enabled: win.shown && win.view === "chat" && chat.voice.canSpeak; onActivated: win.readLast() }
    Shortcut { sequence: "Ctrl+Shift+Space"; enabled: win.shown && win.view === "chat" && chat.voice.available; onActivated: { conversation.focusInput(); chat.voice.toggle() } }
    Shortcut { sequence: "Ctrl+Shift+Backspace"; enabled: win.shown && win.view === "chat" && chat.current !== "" && !chat.busy; onActivated: win.remove(chat.current) }
    Shortcut { sequences: ["Ctrl+/", "F1"]; enabled: win.shown; onActivated: shortcutsDialog.open() }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: win.ready

        // the family band down the window's edge (in Plume, its rail marks the module instead)
        Band { Layout.fillHeight: true; visible: win.viewKeys; color: win.c.famCommunicate }
        Sidebar {
            id: sidebar
            visible: win.sidebarShown
            Layout.fillHeight: true
            Layout.preferredWidth: win.wide ? 284 : 256
            view: win.view
            mode: win.mode
            listMode: win.listMode
            taskId: win.taskId
            onChosen: id => win.openChat(id)
            onNewChat: win.newChat()
            onNewProjectChat: path => win.newCode(path)
            onProjectChosen: id => win.openProject(id)
            onProjectCreateRequested: win.createProject("")
            onCodeChosen: (folder, session) => win.openCode(folder, session)
            onCodeMenuRequested: (session, item, x, y) => codeMenu.openFor(session, item, x, y)
            onProjectPickRequested: codeFolderDialog.open()          // the Code tab: a folder to work in
            onBotChosen: id => { if (win.codeLocked()) return; win.mode = "projects"; win.view = "code"; win.peek = false; sidebar.codeTab = "bots"; bots.closeGroup(); bots.open(id) }   // win.: the sidebar has a view of its own
            onGroupChosen: id => win.openGroup(id)
            onGroupMenuRequested: (g, item, x, y) => groupMenu.openFor(g, item, x, y)
            onGroupCreateRequested: { if (codeLocked()) return; groupDialog.openNew("") }
            onBotCreateRequested: { if (win.codeLocked()) return; win.mode = "projects"; win.view = "code"; sidebar.codeTab = "bots"; botDialog.openNew() }
            onBotEditRequested: id => botDialog.openEdit(id)
            onBotMenuRequested: (bot, item, x, y) => botMenu.openFor(bot, item, x, y)
            onModeChosen: m => m === "tasks" ? win.showTasks() : m === "projects" ? win.showCode() : win.showChats()
            onTaskChosen: id => win.openTask(id)
            onJobChosen: session => win.openJob(session)
            onMenuRequested: (session, item, x, y) => sessionMenu.openFor(session, item, x, y)
            onDeleteRequested: id => win.remove(id)
            onRenameRequested: (id, title) => renameDialog.openFor(id, title)
            onSettingsRequested: settings.open()
            onUsageRequested: settings.showUsage()
            onHideRequested: win.toggleSidebar()
        }
        Rectangle { visible: win.sidebarShown; Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline }
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: win.view === "scheduled" ? 1 : win.view === "code" ? 2 : win.view === "project" ? 3 : win.view === "group" ? 4 : 0
            Conversation {
                id: conversation
                onMenuRequested: item => sessionMenu.openFor(chat.allSessions.find(s => s.id === chat.current)
                                                             || { id: chat.current, title: chat.title, pinned: false },
                                                             item, 0, item.height + 4)
            }
            Scheduled { onAskRequested: text => win.ask(text); onDraftRequested: text => { win.newChat(); conversation.setComposerText(text) } }
            CodeView {
                id: codeView
                onFolderPickRequested: codeFolderDialog.open()
                onMenuRequested: item => codeMenu.openFor(code.recent.find(s => s.id === code.session && s.folder === code.folder)
                                                          || { id: code.session, folder: code.folder, title: code.title }, item, 0, item.height + 4)
                // Agent, Plan, Objectif or Recherche chosen in Code's mode menu: a new conversation of the Discussion in that mode
                onLeaveRequested: uiMode => { win.mode = "chats"; win.view = "chat"; chat.newChat(); chat.setUiMode(uiMode); conversation.focusInput() }
            }
            ProjectView {
                id: projectView
                onSettingsRequested: p => win.editProject(p)
                onMenuRequested: (session, item, x, y) => sessionMenu.openFor(session, item, x, y)
            }
            GroupView {
                id: groupView
                onEditRequested: id => groupDialog.openEdit(id)
                onBotRequested: id => { win.view = "code"; bots.open(id) }
            }
        }
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
    Rectangle {
        anchors.fill: parent
        visible: app.connected && chat.state !== "ready"
        color: win.c.bg
        Skeleton { anchors.fill: parent; anchors.margins: 28; visible: chat.state === "loading"; tone: theme.c.line; lead: false; rows: 6; Accessible.name: app.t.loading }
        EmptyState {
            anchors.fill: parent
            visible: chat.state === "offline_first" || chat.state === "error_first"
            iconName: chat.state === "offline_first" ? "offline" : "warning"
            title: chat.state === "offline_first" ? app.t.first_offline_title : app.t.first_error_title
            lead: chat.state === "offline_first" ? app.t.first_offline_lead : app.t.first_error_lead
            actionText: app.t.retry_now
            actionIcon: "refresh"
            onActivated: chat.refresh(true)
        }
    }

    // ---- one menu for every conversation ------------------------------------------------------------------------
    OMenu {
        id: sessionMenu
        property var session: ({})
        parent: Overlay.overlay
        function openFor(s, item, px, py) {
            session = s
            const p = item.mapToItem(Overlay.overlay, px, py)
            x = Math.min(p.x, Overlay.overlay.width - implicitWidth - 8)
            y = Math.min(p.y, Overlay.overlay.height - implicitHeight - 8)
            open()
        }
        OMenuItem {
            text: sessionMenu.session.pinned ? app.t.unpin : app.t.pin; iconName: "pushpin"
            onTriggered: chat.pin(sessionMenu.session.id, !sessionMenu.session.pinned)
        }
        OMenuItem { text: app.t.rename; iconName: "edit"; onTriggered: renameDialog.openFor(sessionMenu.session.id, sessionMenu.session.title) }
        OMenuItem {             // out of the list, kept (« Archivées » in the list's views), the same on every device
            text: sessionMenu.session.archived ? app.t.unarchive : app.t.archive; iconName: "archive"
            onTriggered: chat.archive(sessionMenu.session.id, !sessionMenu.session.archived)
        }
        OMenuItem {             // only for the conversation shown (the cloud keeps it with the open one)
            visible: sessionMenu.session.id === chat.current
            text: app.t.remember_menu; iconName: chat.remembered ? "check" : "history"
            onTriggered: chat.setRemembered(!chat.remembered)
        }
        // its project (Work mode): moved into one, a new one, or out of any
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        Text {
            leftPadding: 10; topPadding: 6; bottomPadding: 2
            text: app.t.menu_project
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            color: win.c.muted
        }
        Repeater {
            model: projects.items.slice(0, 8)
            OMenuItem {
                required property var modelData
                text: modelData.name
                iconName: (sessionMenu.session.project || "") === modelData.id ? "check" : "folder"
                onTriggered: projects.assign(sessionMenu.session.id, modelData.id)
            }
        }
        OMenuItem { text: app.t.project_new; iconName: "folderPlus"; onTriggered: win.createProject(sessionMenu.session.id) }
        OMenuItem {
            visible: (sessionMenu.session.project || "") !== ""
            text: app.t.menu_no_project; iconName: "close"
            onTriggered: projects.assign(sessionMenu.session.id, "")
        }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem { text: app.t.copy_chat; iconName: "copy"; onTriggered: chat.export(sessionMenu.session.id, "copy") }
        OMenuItem {             // a read-only public link (the conversation as a file in the Drive), after a warning
            text: app.t.share_chat; iconName: "share"
            onTriggered: {
                const id = sessionMenu.session.id
                workDialog.ask(app.t.share_title, app.t.share_text,
                               [{ id: "cancel", text: app.t.cancel }, { id: "share", text: app.t.share_go, kind: "primary" }],
                               () => chat.export(id, "share"))
            }
        }
        OMenuItem { text: app.t.send_notes; iconName: "note"; onTriggered: chat.export(sessionMenu.session.id, "notes") }
        OMenuItem {
            text: app.t.export_file; iconName: "export"
            onTriggered: { exportDialog.sessionId = sessionMenu.session.id; exportDialog.title_ = sessionMenu.session.title || app.t.app_name; exportDialog.open() }
        }
        OMenuItem { text: app.t.open_cloud; iconName: "openExternal"; onTriggered: app.openCloud("/apps/assistant/?sessionId=" + sessionMenu.session.id) }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem { text: app.t.delete; iconName: "trash"; onTriggered: win.remove(sessionMenu.session.id) }
    }

    FileDialog {
        id: exportDialog
        property string sessionId
        property string title_
        fileMode: FileDialog.SaveFile
        nameFilters: ["Markdown (*.md)"]
        defaultSuffix: "md"
        currentFile: app.exportUrl(title_)
        onAccepted: chat.export(sessionId, "file:" + app.localPath(selectedFile))
    }

    OMenu {                                  // a Code conversation: on this computer only
        id: codeMenu
        property var session: ({})
        parent: Overlay.overlay
        function openFor(s, item, px, py) {
            session = s
            const p = item.mapToItem(Overlay.overlay, px, py)
            x = Math.min(p.x, Overlay.overlay.width - implicitWidth - 8)
            y = Math.min(p.y, Overlay.overlay.height - implicitHeight - 8)
            open()
        }
        readonly property bool open_: codeMenu.session.id === code.session && codeMenu.session.folder === code.folder
        OMenuItem {
            text: codeMenu.session.pinned ? app.t.unpin : app.t.pin; iconName: "pushpin"
            onTriggered: code.pin(codeMenu.session.folder, codeMenu.session.id, !codeMenu.session.pinned)
        }
        OMenuItem { text: app.t.rename; iconName: "edit"; onTriggered: codeRename.openFor(codeMenu.session) }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem {
            text: app.t.copy_chat; iconName: "copy"
            onTriggered: { if (!codeMenu.open_) win.openCode(codeMenu.session.folder, codeMenu.session.id); code.copyConversation() }
        }
        OMenuItem {
            text: app.t.export_file; iconName: "export"
            onTriggered: { if (!codeMenu.open_) win.openCode(codeMenu.session.folder, codeMenu.session.id)
                           codeExport.title_ = codeMenu.session.title || code.folderName; codeExport.open() }
        }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem { text: app.t.code_open_folder; iconName: "folder"; onTriggered: app.openFolder(codeMenu.session.folder) }
        OMenuItem { text: app.t.code_terminal; iconName: "terminal"; enabled: codeMenu.open_; onTriggered: code.openTerminal() }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem { text: app.t.delete; iconName: "trash"; onTriggered: code.forget(codeMenu.session.folder, codeMenu.session.id) }
    }
    FileDialog {
        id: codeExport
        property string title_
        fileMode: FileDialog.SaveFile
        nameFilters: ["Markdown (*.md)"]
        defaultSuffix: "md"
        currentFile: app.exportUrl(title_)
        onAccepted: code.exportTo(app.localPath(selectedFile))
    }
    ODialog {
        id: codeRename
        property var session: ({})
        title: app.t.rename
        width: Math.min(460, win.width - 48)
        function openFor(s) { session = s; codeField.text = s.title || s.label || ""; open(); codeField.selectAll(); codeField.forceActiveFocus() }
        OTextField { id: codeField; Layout.fillWidth: true; onAccepted: { code.rename(codeRename.session.folder, codeRename.session.id, text); codeRename.close() } }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: codeRename.close() },
            OButton { kind: "primary"; text: app.t.ok; onClicked: { code.rename(codeRename.session.folder, codeRename.session.id, codeField.text); codeRename.close() } }
        ]
    }
    FolderDialog {
        id: codeFolderDialog
        title: app.t.code_choose_folder
        onAccepted: win.newCode(app.localPath(selectedFolder))
    }
    BotDialog { id: botDialog }
    GroupDialog { id: groupDialog }
    OMenu {
        id: botMenu
        property var bot: ({})
        parent: Overlay.overlay
        function openFor(b, item, px, py) {
            bot = b
            const p = item.mapToItem(Overlay.overlay, px, py)
            x = Math.min(p.x, Overlay.overlay.width - implicitWidth - 8)
            y = Math.min(p.y, Overlay.overlay.height - implicitHeight - 8)
            open()
        }
        OMenuItem {
            text: app.t.bots_edit; iconName: "edit"
            onTriggered: botDialog.openEdit(botMenu.bot.id)
        }
        OMenuItem {
            text: botMenu.bot.paused ? app.t.bots_resume : app.t.bots_pause; iconName: botMenu.bot.paused ? "play" : "stop"
            onTriggered: bots.setPaused(botMenu.bot.id, !botMenu.bot.paused)
        }
        OMenuItem {
            text: app.t.groups_new_with; iconName: "people"
            onTriggered: groupDialog.openNew(botMenu.bot.id)
        }
        OMenuItem {
            text: botMenu.bot.hidden ? app.t.bots_unhide : app.t.bots_hide; iconName: "eye"
            onTriggered: bots.setHidden(botMenu.bot.id, !botMenu.bot.hidden)
        }
        OMenuItem {
            text: app.t.bots_open_folder; iconName: "folder"
            onTriggered: {
                const path = bots.profilePath(botMenu.bot.id)
                if (path) app.openFolder(path)
            }
        }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem {
            text: app.t.delete; iconName: "trash"
            onTriggered: workDialog.ask(
                app.t.bots_delete_title.replace("%1", botMenu.bot.title || botMenu.bot.id),
                app.t.bots_delete_text,
                [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete, kind: "danger" }],
                () => bots.remove(botMenu.bot.id))
        }
    }
    OMenu {
        id: groupMenu
        property var group: ({})
        parent: Overlay.overlay
        function openFor(g, item, px, py) {
            group = g
            const p = item.mapToItem(Overlay.overlay, px, py)
            x = Math.min(p.x, Overlay.overlay.width - implicitWidth - 8)
            y = Math.min(p.y, Overlay.overlay.height - implicitHeight - 8)
            open()
        }
        OMenuItem {
            text: app.t.groups_edit; iconName: "edit"
            onTriggered: groupDialog.openEdit(groupMenu.group.id)
        }
        OMenuItem {
            text: app.t.groups_folder_open; iconName: "folder"
            onTriggered: {
                const path = bots.groupFolder(groupMenu.group.id)
                if (path) app.openFolder(path)
            }
        }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: win.c.hairline }
        OMenuItem {
            text: app.t.delete; iconName: "trash"
            onTriggered: workDialog.ask(
                app.t.groups_delete_title.replace("%1", groupMenu.group.title || groupMenu.group.id),
                app.t.groups_delete_text,
                [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete, kind: "danger" }],
                () => { const open = win.view === "group" && bots.group.id === groupMenu.group.id
                        bots.removeGroup(groupMenu.group.id)
                        if (open) win.view = "code" })
        }
    }
    ProfileDialog { id: profileDialog }
    CommandsDialog { id: commandsDialog }
    ProjectDialog { id: projectDialog }
    Shortcuts { id: shortcutsDialog }
    Settings { id: settings; onProfileRequested: profileDialog.open(); onCommandsRequested: commandsDialog.open(); onDeleteAllRequested: confirmDeleteAll.ask(app.t.delete_all_title,
                                                                         app.t.delete_all_text.replace("%1", app.plural("conversations_count", chat.count)),
                                                                         [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete_all, kind: "danger" }],
                                                                         () => { settings.close(); chat.removeAll() }) }
    ChoiceDialog { id: confirmDeleteAll }
    ChoiceDialog { id: confirmDeleteTask }
    ChoiceDialog { id: workDialog }
    CronSheet { id: cronSheet }
    ODialog {
        id: cronConsent
        width: Math.min(460, win.width - 48)
        Text {
            id: cronConsentLead
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: win.c.muted
        }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: { cron.answerConsent("reject"); cronConsent.close() } },
            OButton { kind: "primary"; text: app.t.ok; onClicked: { cron.answerConsent("allow"); cronConsent.close() } }
        ]
        onClosed: if (cron.waiting) cron.answerConsent("reject")
    }
    Toast { id: toast }
    ODialog {
        id: renameDialog
        property string sessionId
        title: app.t.rename
        width: Math.min(460, win.width - 48)
        function openFor(id, current) { sessionId = id; field.text = current; open(); field.selectAll(); field.forceActiveFocus() }
        OTextField {
            id: field
            Layout.fillWidth: true
            onAccepted: { chat.rename(renameDialog.sessionId, text); renameDialog.close() }
        }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: renameDialog.close() },
            OButton { kind: "primary"; text: app.t.ok; onClicked: { chat.rename(renameDialog.sessionId, field.text); renameDialog.close() } }
        ]
    }
}
