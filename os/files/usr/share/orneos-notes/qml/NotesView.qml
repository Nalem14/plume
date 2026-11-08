// Notes: the sidebar (folders, tags), the list of the folder, then the open note, with Ornis beside it. The two
// side columns step aside to write (Ctrl+Maj+E), and the sidebar on its own when the window is narrow.
// Signed out or loading for the first time, it shows only that state. The window of Notes (Main.qml) and the
// Notes module of Plume both show this view; they bring it up (raiseWanted) and close it their own way.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"

Item {
    id: win
    readonly property var c: theme.c
    readonly property bool wide: width >= 1120
    readonly property bool narrow: width < 900
    readonly property bool focusMode: !!app.prefs.focus_mode
    readonly property bool ready: app.connected && notes.state === "ready"
    // shortcuts only while the view is the one shown (Plume keeps its other modules in the same window)
    readonly property bool shown: ready && visible
    // its own window (Plume sets it to false: its rail marks the module, and Ctrl+1… switch modules)
    property bool viewKeys: true
    property string selected: ""
    property alias toast: toast
    property alias quickNoteOpen: quickNote.visible
    signal raiseWanted()
    signal quickClosed()
    signal aboutChanged()                   // the note shown changed (Plume: Ornis beside reads it again)

    function bringUp() { raiseWanted() }
    function flush() { editor.flush() }
    function openNote(key) {
        if (!key) return
        const d = notes.detail(key)
        if (!d.key) return
        if (notes.folder === "trash" || (notes.folder !== "all" && notes.folder !== "folder:" + d.folder))
            notes.setFolder("all")
        notes.setQuery("")
        sidebar.setSearch("")
        selected = key
    }
    function newNote() {
        if (notes.folder === "trash")
            notes.setFolder("all")
        editor.flush()
        const tagged = notes.folder.indexOf("tag:") === 0
        selected = notes.create("")
        if (tagged) Qt.callLater(editor.focusStart)       // the tag is below: the title is typed above it
    }
    function newFrom(template) {
        if (notes.folder === "trash") notes.setFolder("all")
        editor.flush()
        selected = notes.createFrom(template)
        Qt.callLater(editor.focusText)
    }
    function daily() {
        editor.flush()
        const key = notes.daily()
        if (key) { openNote(key); Qt.callLater(() => { editor.focusText() }) }
    }
    function toggleFocus() { app.setPref("focus_mode", !focusMode) }
    // Ctrl+F: in the note when it is being written, else among all the notes
    function find(withReplace) {
        if (selected && (editor.textFocused || editor.findOpen || withReplace)) editor.openFind(withReplace)
        else searchAll()
    }
    function searchAll() {
        if (focusMode) app.setPref("focus_mode", false)
        if (narrow) { sidebarMenu.open(); Qt.callLater(() => { if (sidebarLoader.item) sidebarLoader.item.focusSearch() }) }
        else sidebar.focusSearch()
    }
    // what Ornis beside the module (Plume, Ctrl+J) reads: the note shown ({} when there is none)
    function ornisAbout() {
        if (!app.connected || !selected) return {}
        editor.flush()
        const d = notes.detail(selected)
        if (!d.key || d.trashed) return {}
        return { kind: "note", icon: "note", label: d.title || app.t.untitled,
                 text: "Note « " + (d.title || app.t.untitled) + " »" + (d.folder ? " (folder: " + d.folder + ")" : "")
                       + "\n\n" + (d.content || "").slice(0, 12000) }
    }
    function askNotes(q) { askDialog.start(q) }
    function askOrnis(kind) { if (selected && editor.editable) ornisPanel.start(kind) }
    function openSettings() { settings.open() }
    // Delete: to « Récemment supprimées » with « Annuler »; from there, for good after a question
    function remove(keys) {
        if (!keys.length) return
        if (keys[0].indexOf("trash:") === 0 || keys[0].indexOf("deleted:") === 0) {
            purgeDialog.ask(keys.length > 1 ? app.plural("purge_many", keys.length) : app.t.purge_title, app.t.purge_text,
                            [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete_forever, kind: "danger" }],
                            () => { notes.purge(keys); list.chosen = [] })
            return
        }
        editor.flush()
        notes.delete(keys)
        list.chosen = []
    }

    Connections {
        target: app
        function onToast(message) { toast.show(message) }
        function onRaiseRequested() { win.bringUp() }
        function onShowRequested(ref) { const k = notes.resolve(ref); if (k) { win.openNote(k); win.bringUp() } }
        function onActionRequested(action, value) {
            if (action === "new") { win.bringUp(); win.newNote() }
            else if (action === "daily") { win.bringUp(); win.daily() }
            else if (action === "quick") quickNote.start()
            else if (action === "folder") notes.setFolder("folder:" + value)
            else if (action === "search") { sidebar.setSearch(value); win.bringUp() }
            else if (action === "files") { const k = notes.from_files(JSON.parse(value)); if (k) { win.openNote(k); win.bringUp() } }
        }
    }
    Connections {
        target: notes
        function onFolderChanged() {
            if (notes.items.length && !notes.items.some(r => r.key === win.selected))
                win.selected = notes.items[0].key
            else if (!notes.items.length && notes.folder !== "trash")
                win.selected = ""
        }
        function onCreated(key) { win.openNote(key) }
        function onStateChanged() { if (!win.viewKeys) aboutTimer.restart() }
        // the first note opens with the window, and after the open one left the list
        function onChanged() {
            if (win.selected === "" && notes.items.length && notes.folder !== "trash")
                win.selected = notes.items[0].key
        }
        function onDone(what, ok, message) {
            if (!ok) problem.tell(message)
            else if (what === "deleted") toast.show(message, app.t.undo, () => notes.undoDelete(), 6)
            else if (message) toast.show(message)
        }
    }

    Shortcut { sequence: "Ctrl+N"; enabled: win.shown; onActivated: win.newNote() }
    Shortcut { sequence: "Ctrl+F"; enabled: win.shown; onActivated: win.find(false) }
    Shortcut { sequence: "Ctrl+H"; enabled: win.shown && win.selected !== ""; onActivated: win.find(true) }
    Shortcut { sequence: "Ctrl+Shift+F"; enabled: win.shown; onActivated: win.searchAll() }
    Shortcut { sequence: "F3"; enabled: win.shown && editor.findOpen; onActivated: editor.findStep(false) }
    Shortcut { sequence: "Shift+F3"; enabled: win.shown && editor.findOpen; onActivated: editor.findStep(true) }
    Shortcut { sequence: "Escape"; enabled: win.shown && editor.findOpen; onActivated: editor.closeFind() }
    Shortcut { sequence: "Ctrl+,"; enabled: win.shown && win.viewKeys; onActivated: settings.open() }
    Shortcut { sequence: "Ctrl+Shift+N"; enabled: win.shown; onActivated: quickNote.start() }
    Shortcut { sequence: "Ctrl+Shift+D"; enabled: win.shown; onActivated: win.daily() }
    Shortcut { sequence: "Ctrl+Shift+E"; enabled: win.shown; onActivated: win.toggleFocus() }
    // in Plume, Ctrl+J is Ornis beside the module (it reads the note shown): « Demander à vos notes » stays a button
    Shortcut { sequence: "Ctrl+J"; enabled: win.shown && win.viewKeys; onActivated: win.askNotes("") }
    Shortcut { sequence: "Ctrl+P"; enabled: win.shown && win.selected !== ""; onActivated: { editor.flush(); notes.printNote(win.selected) } }
    Shortcut { sequence: "Ctrl+Shift+P"; enabled: win.shown && win.selected !== ""; onActivated: notes.togglePin(win.selected) }
    Shortcut { sequence: "F5"; enabled: win.shown; onActivated: notes.refresh() }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: win.ready

        // the family band down the window's edge (in Plume, its rail marks the module instead)
        Band { Layout.fillHeight: true; visible: win.viewKeys; color: win.c.famDocs }
        Sidebar {
            id: sidebar
            Layout.fillHeight: true
            Layout.preferredWidth: win.wide ? 280 : 248
            visible: !win.focusMode && !win.narrow
            onToList: list.focusList()
            onSettingsRequested: settings.open()
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline; visible: sidebar.visible }
        NoteList {
            id: list
            Layout.fillHeight: true
            Layout.preferredWidth: win.wide ? 330 : 280
            visible: !win.focusMode
            // narrow: the sidebar is a menu at the top of the list
            compact: win.narrow
            onFolderMenuRequested: item => sidebarMenu.openAt(item)
            selected: win.selected
            onPicked: key => { editor.flush(); win.selected = key }
            onNewNote: win.newNote()
            onNewFrom: template => win.newFrom(template)
            onDailyRequested: win.daily()
            onDeleteRequested: keys => win.remove(keys)
            onMoveRequested: keys => moveDialog.openFor(keys)
            onTasksRequested: key => tasksDialog.openFor(key)
            onShareRequested: key => shareDialog.openFor(key)
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline; visible: list.visible }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Editor {
                id: editor
                focusMode: win.focusMode
                onFocusToggled: win.toggleFocus()
                onOpenRequested: key => win.openNote(key)
                onVersionsRequested: key => versionsDialog.openFor(key)
                onConflictRequested: copy => conflictDialog.openFor(copy)
                anchors.fill: parent
                anchors.rightMargin: ornisPanel.opened ? ornisPanel.width - 12 : 0
                key: win.selected
                onDeleteRequested: keys => win.remove(keys)
                onOrnisRequested: kind => ornisPanel.start(kind)
                onAskRequested: win.askNotes("")
                onTasksRequested: key => tasksDialog.openFor(key)
                onShareRequested: key => shareDialog.openFor(key)
                onNewNoteRequested: win.newNote()
                onToastRequest: message => toast.show(message)
            }
            OrnisPanel {
                id: ornisPanel
                anchors.right: parent.right
                anchors.top: parent.top; anchors.topMargin: 52
                anchors.bottom: parent.bottom
                width: Math.min(400, parent.width * 0.5)
                editor: editor
            }
        }
    }

    EmptyState {
        anchors.fill: parent
        visible: !app.connected
        iconName: "note"
        title: app.t.welcome_title
        lead: app.t.welcome_lead
        actionText: app.t.welcome_action
        onActivated: app.openConnect()
    }
    Rectangle {
        anchors.fill: parent
        visible: app.connected && notes.state !== "ready"
        color: win.c.bg
        Skeleton { anchors.fill: parent; anchors.margins: 28; visible: notes.state === "loading"; tone: win.c.line; lead: false; rows: 8; Accessible.name: app.t.loading }
        EmptyState {
            anchors.fill: parent
            visible: notes.state === "offline_first" || notes.state === "error_first"
            iconName: notes.state === "offline_first" ? "offline" : "warning"
            title: notes.state === "offline_first" ? app.t.first_offline_title : app.t.first_error_title
            lead: notes.state === "offline_first" ? app.t.first_offline_lead : app.t.first_error_lead
            actionText: app.t.retry
            actionIcon: "refresh"
            onActivated: notes.refresh()
        }
    }

    // the window narrow: the sidebar opens over the list
    Popup {
        id: sidebarMenu
        property string folderShown
        function openAt(item) { open() }
        onAboutToShow: folderShown = notes.folder
        x: 0; y: 0
        width: 280; height: win.height
        padding: 0
        modal: true
        Overlay.modal: Rectangle { color: win.c.scrim }
        contentItem: Item {
            Loader {
                id: sidebarLoader
                anchors.fill: parent
                active: sidebarMenu.opened
                sourceComponent: Sidebar {
                    onToList: { sidebarMenu.close(); list.focusList() }
                    onSettingsRequested: { sidebarMenu.close(); settings.open() }
                }
            }
        }
        Connections { target: notes; function onFolderChanged() { if (notes.folder !== sidebarMenu.folderShown) sidebarMenu.close() } }
    }
    // a note opened from search results: the words found are shown in it
    Connections {
        target: win
        function onSelectedChanged() { Qt.callLater(() => editor.showWords(notes.query)) }
    }

    Timer { id: aboutTimer; interval: 800; onTriggered: win.aboutChanged() }
    Toast { id: toast }
    VersionsDialog { id: versionsDialog; editor: editor }
    ConflictDialog { id: conflictDialog; onOpenRequested: key => win.openNote(key) }
    ChoiceDialog { id: purgeDialog }
    ProblemDialog { id: problem }
    AskDialog { id: askDialog }
    TasksDialog { id: tasksDialog }
    MoveDialog { id: moveDialog }
    ShareDialog { id: shareDialog }
    SettingsDialog { id: settings }
    QuickNote { id: quickNote }
}
