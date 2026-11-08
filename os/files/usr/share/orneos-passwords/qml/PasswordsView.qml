// Mots de passe: the sidebar (search, category tiles, folders), the list, then the selected entry.
// Locked, signed out or loading, it shows only that state. The window of Mots de passe (Main.qml) and the
// module of Plume both show this view; they bring it up (raiseWanted) their own way.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: win
    readonly property var c: theme.c
    readonly property bool wide: width >= 1080
    property string selected: ""            // entry id, or a Wi-Fi uuid in the Wi-Fi category
    property string mode: "view"            // view | edit | new
    property var draft: ({})                // what a new entry starts with (a scanned code, a generated password)
    readonly property bool ready: app.connected && !lock.locked && (vault.state === "ready")
    // shortcuts only while the view is the one shown (Plume keeps its other modules in the same window)
    readonly property bool shown: ready && visible
    // its own window (Plume sets it to false: its rail marks the module)
    property bool viewKeys: true
    signal raiseWanted()

    Component.onCompleted: if (wifi.available) wifi.load()
    // another module of Plume in front counts as away, like a window behind (lock_minutes)
    onVisibleChanged: lock.setShown(visible)

    function select(id) {
        if (mode !== "view" && !detail.confirmLeave(() => select(id)))
            return
        mode = "view"
        selected = id
    }
    function newEntry(start) {
        if (vault.category === "wifi" || vault.category === "trash")
            vault.setCategory("all")
        draft = start || {}
        selected = ""
        mode = "new"
    }
    function edit() { if (selected) mode = "edit" }
    function closeEditor(id) {
        mode = "view"
        if (id) selected = id
    }
    function copySelected(what) {
        if (!ready || !selected || vault.category === "wifi")
            return
        const d = vault.detail(selected)
        if (what === "password") app.copy(d.password || "", "password")
        else if (what === "username") app.copy(d.username || "", "username")
        else if (what === "code" && d.otp) app.copy(vault.code(selected).code, "code")
    }

    Connections {
        target: app
        function onToast(message) { toast.show(message) }
        function onCopied(what) {
            if (what === "password" || what === "code" || what === "wifi" || what === "field")
                toast.show(app.t["copied_" + (what === "field" ? "password" : what)] + " · "
                           + app.t.copied_clears.replace("%1", app.prefs.clipboard_seconds))
            else
                toast.show(app.t.copied)
        }
        function onRaiseRequested() { win.raiseWanted() }
        function onShowRequested(id) {
            if (vault.category === "wifi" || vault.category === "trash")
                vault.setCategory("all")
            vault.setQuery("")
            win.select(id)
        }
        function onActionRequested(action, value) {
            if (action === "new") win.newEntry()
            else if (action === "security") vault.setCategory("security")
            else if (action === "wifi") vault.setCategory("wifi")
            else if (action === "generator") generatorDialog.open()
            else if (action === "otpauth") codeSetup.openWith(value, "")
        }
    }

    Connections {
        target: vault
        function onCategoryChanged() {
            if (win.mode === "view")
                win.selected = vault.category === "wifi" ? "" : (vault.items.length ? vault.items[0].id : "")
        }
        // what the window showed done and the cloud refused: said in a dialog (the change was undone)
        function onDone(what, ok, message) {
            if (!ok && message)
                (what === "history" || what === "recipients" ? toast.show(message) : problem.tell(message))
        }
    }
    Connections {
        target: lock
        function onChanged() {
            if (lock.locked) {
                generatorDialog.close(); shareDialog.close(); settings.close(); codeSetup.close()
                importDialog.close(); ornisDialog.close()
            }
        }
    }

    Shortcut { sequence: "Ctrl+N"; enabled: win.shown; onActivated: win.newEntry() }
    Shortcut { sequence: "Ctrl+F"; enabled: win.shown; onActivated: sidebar.focusSearch() }
    Shortcut { sequence: "Ctrl+,"; enabled: win.shown; onActivated: settings.open() }
    Shortcut { sequence: "Ctrl+L"; enabled: win.visible && lock.available && !lock.locked; onActivated: lock.lock() }
    Shortcut { sequence: "Ctrl+G"; enabled: win.shown; onActivated: generatorDialog.open() }
    Shortcut { sequence: "Ctrl+Shift+C"; enabled: win.shown && win.mode === "view"; onActivated: win.copySelected("username") }
    Shortcut { sequence: "Ctrl+Alt+C"; enabled: win.shown && win.mode === "view"; onActivated: win.copySelected("code") }
    Shortcut { sequence: "F5"; enabled: win.shown; onActivated: vault.refresh() }

    // ---- the app ---------------------------------------------------------------------------------------
    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: win.ready

        // the family band down the window's edge (in Plume, its rail marks the module instead)
        Band { Layout.fillHeight: true; visible: win.viewKeys; color: win.c.famTools }
        Sidebar {
            id: sidebar
            Layout.fillHeight: true
            Layout.preferredWidth: win.wide ? 268 : 244
            onToList: list.focusList()
            onSettingsRequested: settings.open()
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Toolbar {
                Layout.fillWidth: true
                onNewRequested: win.newEntry()
                onGeneratorRequested: generatorDialog.open()
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                EntryList {
                    id: list
                    Layout.fillHeight: true
                    Layout.preferredWidth: win.wide ? 340 : 290
                    selected: win.selected
                    onPicked: id => win.select(id)
                    onOrnisPlan: ornisDialog.plan()
                }
                Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: win.c.hairline }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Detail {
                        id: detail
                        anchors.fill: parent
                        visible: vault.category !== "wifi"
                        entryId: win.selected
                        mode: win.mode
                        draft: win.draft
                        onEditRequested: win.edit()
                        onDone: id => win.closeEditor(id)
                        onShareRequested: id => shareDialog.openFor(id)
                        onCodeRequested: (id, uri) => codeSetup.openWith(uri, id)
                        onOrnisTwofa: (site, label) => ornisDialog.twofa(site, label)
                        onImportRequested: importDialog.start()
                    }
                    WifiDetail {
                        anchors.fill: parent
                        visible: vault.category === "wifi"
                        uuid: win.selected
                    }
                }
            }
        }
    }

    // ---- the other states ------------------------------------------------------------------------------
    EmptyState {
        anchors.fill: parent
        visible: !app.connected
        iconName: "key"
        title: app.t.welcome_title
        lead: app.t.welcome_lead
        actionText: app.t.welcome_action
        onActivated: app.openConnect()
    }

    LockScreen {
        anchors.fill: parent
        visible: app.connected && lock.locked
    }

    Rectangle {
        anchors.fill: parent
        visible: app.connected && !lock.locked && vault.state !== "ready"
        color: win.c.bg
        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(460, parent.width - 64)
            spacing: 0
            visible: vault.state === "loading"
            Skeleton { Layout.fillWidth: true; Layout.preferredHeight: 6 * 44; tone: theme.c.line; rows: 6; Accessible.name: app.t.loading }
        }
        EmptyState {
            anchors.fill: parent
            visible: vault.state === "offline_first" || vault.state === "error_first"
            iconName: vault.state === "offline_first" ? "offline" : "warning"
            title: vault.state === "offline_first" ? app.t.first_offline_title : app.t.first_error_title
            lead: vault.state === "offline_first" ? app.t.first_offline_lead : app.t.first_error_lead
            actionText: app.t.retry
            actionIcon: "refresh"
            onActivated: vault.refresh()
        }
        EmptyState {
            anchors.fill: parent
            visible: vault.state === "cse"
            iconName: "lock"
            title: app.t.cse_title
            lead: app.t.cse_lead
            actionText: app.t.open_cloud
            actionIcon: "cloud"
            onActivated: app.openCloud("/apps/passwords/")
        }
    }

    Toast { id: toast }
    ProblemDialog { id: problem }

    GeneratorDialog {
        id: generatorDialog
        onSaveAs: password => win.newEntry({ password: password })
    }
    ShareDialog { id: shareDialog }
    SettingsDialog {
        id: settings
        onImportRequested: importDialog.start()
    }
    CodeSetupDialog {
        id: codeSetup
        onNewEntryWith: uri => win.newEntry({ otp: uri })
        onAttached: id => { if (vault.category === "wifi" || vault.category === "trash") vault.setCategory("all"); win.select(id) }
    }
    ImportDialog { id: importDialog }
    OrnisDialog { id: ornisDialog }
}
