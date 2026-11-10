// The « Code » mode: Ornis works in a folder of the computer (ornis_core/code.py over ornis_code: Mistral Vibe by
// ACP, through the cloud's gateway, in the sandbox). A head (the folder, what Ornis does without asking, the
// sandbox, the context), the conversation (messages, a card per tool with its diff or output, the permissions to
// give right on the card), the plan, and the composer. Conversations stay on this computer.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Qt.labs.qmlmodels
import "components"

Item {
    id: view
    property var why: ({})        // the « why ? » of a 👎 open under an answer (Message.why)
    readonly property var c: theme.c
    readonly property real room: width - (benchTab !== "" && !benchOver ? benchWidth : 0)      // beside the panel
    readonly property int column: Math.min(app.readingWidth + 80, Math.max(300, room - 56))
    property bool stick: true
    signal backRequested()
    signal leaveRequested(string uiMode)        // a mode of the Discussion chosen in the mode menu
    signal folderPickRequested()
    signal menuRequested(Item item)             // « … » of the header: the conversation's menu (OrnisView's codeMenu)
    // the panel on the right (BenchPanel): its tab ("" closed), its width, over the conversation when the view is narrow
    readonly property string benchTab: code.folder !== "" ? (app.prefs.bench_tab || "") : ""
    readonly property bool benchOver: width < 880 || benchMax
    property bool benchMax: false
    property alias benchPanel: benchPanel
    property real benchDrag: -1
    readonly property real benchWidth: benchMax ? width : benchOver ? Math.min(width - 24, 460)
        : Math.max(300, Math.min(width * 0.62, benchDrag > 0 ? benchDrag : (app.prefs.bench_width || 440)))
    function toggleBench(tab) {
        app.setPref("bench_tab", benchTab === tab ? "" : tab)
        if (benchTab === "") benchMax = false
        else benchPanel.show(tab)
    }
    // a file of a message (joined or named with @) opened in the panel; one outside the folder, in its app
    function openInBench(path) {
        if (!path) return
        if (code.bench.absolute(path) === "") { Qt.openUrlExternally("file://" + path); return }
        app.setPref("bench_tab", "files")
        const root = String(code.folder).replace(/\/+$/, "") + "/"
        benchPanel.openFile(path.startsWith(root) ? path.slice(root.length) : path)
    }
    // a file of a turn's card opened in the panel, with what changed in it
    function showChange(rev, path) {
        app.setPref("bench_tab", "changes")
        benchPanel.openDiff("turn", rev, path)
    }
    // @path written where the cursor is (a file of the panel, dragged or « Mentionner »)
    function mention(path) {
        const at = input.cursorPosition
        const before = input.text.slice(0, at)
        input.insert(at, (before !== "" && !/\s$/.test(before) ? " @" : "@") + mentionText(path) + " ")
        input.forceActiveFocus()
    }
    function focusInput() { input.forceActiveFocus() }
    // a path in the message: @src/app.py, or @"A LIRE.txt" when it has a space (code.mentioned reads both)
    function mentionText(path) { return /\s/.test(path) ? '"' + path + '"' : path }
    // positionViewAtEnd stops short while the last rows learn their height: then the very end, once more after
    // (as the Discussions)
    function toEnd() { Qt.callLater(() => { list.positionViewAtEnd(); view.toLastLine(); settle.restart() }) }
    function toLastLine() { list.contentY = Math.max(list.originY - list.topMargin, list.originY + list.contentHeight + list.bottomMargin - list.height) }
    Timer { id: settle; interval: 120; onTriggered: if (view.stick) view.toLastLine() }
    property int historyBack: 0                 // ↑ in the box: how far back in the messages sent here
    function send() {
        const text = input.text.trim()
        historyBack = 0
        if (!text) return                       // while Ornis works, it waits and goes after the turn (as in Claude Code)
        mentionPopup.close()
        code.send(text)
        input.text = ""
        view.stick = true
        view.toEnd()
    }
    // @: the project's files, suggested from what follows the @ before the cursor
    property string mentionQuery: ""
    property int mentionStart: -1
    property int mentionIndex: 0
    property var mentionRows: []
    function updateMention() {
        const before = input.text.slice(0, input.cursorPosition)
        const m = before.match(/(^|\s)@([^\s@]*)$/)
        const sl = before.match(/^\/(\S*)$/)            // a command: « / » at the start of the message
        if (!m && !sl) { mentionPopup.close(); mentionStart = -1; return }
        popupKind = m ? "mention" : "slash"
        const q = m ? m[2] : sl[1]
        mentionStart = input.cursorPosition - q.length - 1
        mentionQuery = q
        mentionRows = m ? code.files(q) : code.commands(q)
        mentionIndex = 0
        if (mentionRows.length) mentionPopup.open(); else mentionPopup.close()
    }
    function applyMention(row) {
        if (mentionStart < 0 || !row) return
        input.remove(mentionStart, input.cursorPosition)
        mentionPopup.close()
        mentionStart = -1
        if (popupKind === "slash") { applySlash(row); return }
        // written in the message, as in Claude Code: the file goes with it and shows on the sent message
        const at = input.cursorPosition
        const after = input.text.charAt(at)
        input.insert(at, "@" + mentionText(row.path) + (after === "" || !/\s/.test(after) ? " " : ""))
    }
    // « / »: an action at once (ours), or the agent's own command written for the message
    property string popupKind: "mention"
    function applySlash(row) {
        if (row.kind === "new") { if (code.bot) code.compact(); else code.newIn(code.folder); return }
        if (row.kind === "compact") { code.compact(); return }
        if (row.kind === "terminal") { code.openTerminal(); return }
        if (row.kind === "undo") { code.undoLast(); return }
        if (row.kind === "plan") { code.setAgentMode("plan"); return }
        if (row.kind === "ask") { code.setAgentMode("ask"); return }
        if (row.kind === "init") { code.send(app.t.code_init_text); return }
        if (row.kind === "notebook") { code.openNotebook(); return }
        if (row.kind === "code") { code.setAgentMode("agent"); return }
        if (row.kind === "goal" || row.kind === "research") { view.leaveRequested(row.kind); return }
        if (row.kind === "retry") { code.send("/retry"); return }
        input.insert(input.cursorPosition, row.value)
    }
    // OMenu is a Popup (no popup(item) of Menu): placed above its button, in the view, then opened
    function openAbove(menu, button) {
        const at = button.mapToItem(view, 0, 0)
        menu.x = Math.min(at.x, view.width - menu.implicitWidth - 8)
        menu.y = at.y - menu.implicitHeight - 6
        menu.open()
    }
    function openModes() { openAbove(workMenu, modeBtn) }
    readonly property var modeInfo: ({
        ask: { label: app.t.code_mode_ask, sub: app.t.code_mode_ask_sub, icon: "hand" },
        edits: { label: app.t.code_mode_edits, sub: app.t.code_mode_edits_sub, icon: "shieldCheck" },
        auto: { label: app.t.code_mode_auto, sub: app.t.code_mode_auto_sub, icon: "play" }
    })

    Rectangle { anchors.fill: parent; color: view.c.bg }

    Connections {
        target: code
        function onChanged() { if (view.stick) view.toEnd() }
        function onProblem(message) { win.toast.show(message) }
        function onLaterReturned(text) {        // « Modifier » on a waiting message, or a stopped turn
            input.text = input.text ? text + "\n\n" + input.text : text
            input.cursorPosition = input.length
            input.forceActiveFocus()
        }
    }
    Connections {                           // a bot opened with answers you have not read: the « Non lu » bar
        target: code
        function onUnreadMarkAt(at) {
            view.stick = false
            Qt.callLater(() => list.positionViewAtIndex(at, ListView.Beginning))
        }
    }
    Connections {
        target: code.items
        function onRowsInserted() { if (view.stick) view.toEnd() }
        function onDataChanged() { if (view.stick) view.toEnd() }
    }

    // Routines float over the conversation (chip / retractable sheet); they never shrink the column
    // Leaving a bot closes the Routines bench tab (it has no meaning on a project session).
    Connections {
        target: code
        function onChanged() {
            if (code.bot === "" && view.benchTab === "routines")
                app.setPref("bench_tab", "")
        }
    }

    ColumnLayout {
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        anchors.right: view.benchTab !== "" && !view.benchOver ? benchPanel.left : parent.right
        spacing: 0

        // ---- the head: the folder, the mode, the sandbox, the context -------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            visible: code.folder !== ""
            color: view.c.bg
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: view.c.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: win.sidebarShown ? 16 : 8; anchors.rightMargin: 12
                spacing: 10
                OButton { visible: !win.sidebarShown; kind: "quiet"; iconName: "sidebar"; height_: 30; tip: app.t.show_sidebar + "  (Ctrl+B)"; onClicked: win.toggleSidebar() }
                BotFace {
                    visible: code.bot !== ""
                    face: (bots.current && bots.current.face) || {}
                    size: 30
                    busy: code.busy
                }
                Rectangle {
                    visible: code.bot === ""
                    implicitWidth: 30; implicitHeight: 30; radius: 8
                    color: view.c.tint
                    Icon { anchors.centerIn: parent; name: "code"; size: 16; color: view.c.tintText }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            Layout.fillWidth: !(code.bot && bots.current && bots.current.badge)
                            Layout.maximumWidth: implicitWidth
                            text: code.bot ? ((bots.current && bots.current.title) || code.folderName) : (code.title || code.folderName || app.t.mode_code)
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                            color: view.c.text
                        }
                        BotBadge {
                            text: code.bot && bots.current ? (bots.current.badge || "") : ""
                            tint: (bots.current && bots.current.face && bots.current.face.color) || view.c.accent
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout {              // bot role, or the folder (its full path on hover) + Git branch
                        Layout.fillWidth: true
                        spacing: 5
                        ToolbarChip {        // a bot on pause: says so, one click resumes it
                            visible: code.bot !== "" && !!(bots.current && bots.current.paused)
                            implicitHeight: 20
                            iconName: "play"; label: app.t.bots_paused; tone: "saffron"; chevron: false
                            tip: app.t.bots_resume
                            onClicked: bots.setPaused(code.bot, false)
                        }
                        Text {
                            visible: code.bot !== "" && !!(bots.current && bots.current.description)
                            Layout.maximumWidth: 320
                            text: (bots.current && bots.current.description) || ""
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                            color: view.c.muted
                        }
                        Icon {
                            visible: code.bot === "" || !!(bots.current && bots.current.folder)
                            name: "folder"; size: 12; color: view.c.muted
                        }
                        Text {
                            id: headFolder
                            // bot with a role: only the description; otherwise the folder name
                            visible: code.bot === "" || !!(bots.current && bots.current.folder)
                            Layout.maximumWidth: 280
                            text: code.bot ? String(code.folder).replace(/\\/g, "/").split("/").pop() : code.folderName
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                            color: view.c.muted
                            HoverHandler { id: pathHover }
                            ToolTip.visible: pathHover.hovered
                            ToolTip.delay: 500
                            ToolTip.text: code.folder + "\n" + app.t.code_local
                        }
                        Icon { visible: !!code.git.branch; Layout.leftMargin: 4; name: "branch"; size: 11; color: view.c.faint }
                        Text {
                            visible: !!code.git.branch
                            Layout.fillWidth: true
                            text: (code.git.branch || "") + (code.git.dirty ? " · " + app.plural("code_git_dirty", code.git.dirty) : "")
                            elide: Text.ElideRight
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: view.c.faint
                        }
                        Item { Layout.fillWidth: !code.git.branch }
                    }
                }
                // the panel's tabs: Routines (bots), Fichiers, Modifications, Plan, Terminal
                Row {
                    spacing: 2
                    Repeater {
                        model: {
                            const rows = []
                            if (code.bot !== "")
                                rows.push({ key: "routines", icon: "clock", tip: app.t.bots_routines,
                                            keys: "", badge: cron.botRoutines(code.bot).length, dot: false })
                            rows.push(
                                { key: "files", icon: "folder", tip: app.t.bench_files, keys: "Ctrl+Shift+E", badge: 0, dot: false },
                                { key: "changes", icon: "history", tip: app.t.bench_changes, keys: "Ctrl+Shift+G",
                                  badge: code.bench.status.length || (code.bench.turn.files || []).length, dot: false },
                                { key: "plan", icon: "list", tip: app.t.bench_plan, keys: "", badge: 0, dot: code.planReady },
                                { key: "terminal", icon: "terminal", tip: app.t.bench_terminal, keys: "Ctrl+`", badge: 0, dot: false }
                            )
                            if (browser)
                                rows.push({ key: "browser", icon: "globe", tip: app.t.bench_browser, keys: "", badge: 0, dot: false })
                            return code.bot !== "" ? rows.filter(r => r.key !== "plan") : rows   // bots: no Plan mode
                        }
                        AbstractButton {
                            id: benchBtn
                            required property var modelData
                            readonly property bool on: view.benchTab === modelData.key
                            width: 34; height: 32
                            hoverEnabled: true
                            onClicked: view.toggleBench(modelData.key)
                            Accessible.name: modelData.tip
                            Accessible.checkable: true
                            Accessible.checked: on
                            ToolTip.visible: hovered
                            ToolTip.delay: 450
                            ToolTip.text: modelData.tip + (modelData.keys ? "  (" + modelData.keys + ")" : "")
                            background: Rectangle {
                                radius: 9
                                color: benchBtn.on ? view.c.tint : benchBtn.hovered ? view.c.hover : "transparent"
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }
                            contentItem: Item {
                                Icon { anchors.centerIn: parent; name: benchBtn.modelData.icon; size: 16
                                       color: benchBtn.on ? view.c.tintText : view.c.muted }
                                Rectangle {          // what changed: a count; a plan ready: a dot
                                    visible: benchBtn.modelData.badge > 0 || benchBtn.modelData.dot
                                    x: parent.width - width - 2; y: 2
                                    width: benchBtn.modelData.dot ? 8 : Math.max(15, bCount.implicitWidth + 7); height: benchBtn.modelData.dot ? 8 : 15
                                    radius: height / 2
                                    color: benchBtn.modelData.dot ? view.c.saffron : view.c.famCommunicate
                                    border.width: 1.5; border.color: view.c.bg
                                    Text { id: bCount; anchors.centerIn: parent; visible: !benchBtn.modelData.dot
                                           text: benchBtn.modelData.badge > 9 ? "9+" : benchBtn.modelData.badge
                                           font.family: "Schibsted Grotesk"; font.pixelSize: 9; font.weight: Font.Bold; color: "white" }
                                }
                            }
                        }
                    }
                }
                Rectangle { width: 1; height: 20; color: view.c.hairline }
                // a new session: the column has it; here only when the column is folded
                OButton { visible: !win.sidebarShown; kind: "quiet"; iconName: "compose"; height_: 30; tip: app.t.code_new + "  (Ctrl+N)"; enabled: !code.busy; onClicked: { code.newIn(code.folder); view.focusInput() } }
                OButton {                    // the conversation's menu, as in Work
                    id: headMore
                    visible: code.session !== ""
                    kind: "quiet"; iconName: "more"; height_: 30; tip: app.t.more
                    onClicked: view.menuRequested(headMore)
                }
            }
        }

        // ---- the conversation -------------------------------------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // no folder yet: choose one
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(460, parent.width - 48)
                visible: code.folder === ""
                spacing: 14
                Icon { Layout.alignment: Qt.AlignHCenter; name: "code"; size: 34; color: view.c.accent }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: app.t.code_pick_lead
                    font.family: "Schibsted Grotesk"; font.pixelSize: 17; font.weight: Font.DemiBold
                    color: view.c.text
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: app.t.code_lead
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: view.c.muted
                }
                OButton { Layout.alignment: Qt.AlignHCenter; kind: "primary"; iconName: "folder"; text: app.t.code_choose_folder
                          onClicked: view.folderPickRequested() }
                OButton { Layout.alignment: Qt.AlignHCenter; kind: "quiet"; iconName: "plus"; text: app.t.new_session + " · " + app.t.code_home
                          onClicked: { code.newIn(code.homeFolder); view.focusInput() } }
            }

            // getting ready (once), starting, or a problem
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(460, parent.width - 48)
                visible: code.state === "installing" || code.state === "starting" || code.state === "error"
                spacing: 14
                Icon {
                    Layout.alignment: Qt.AlignHCenter
                    name: code.state === "error" ? "warning" : "ornis"
                    thinking: code.state !== "error"
                    size: 34
                    color: code.state === "error" ? view.c.danger : view.c.accent
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: code.state === "error" ? (app.t[code.error] || app.t.code_failed)
                          : code.state === "installing" ? app.t.code_installing : app.t.code_starting
                    font.family: "Schibsted Grotesk"; font.pixelSize: 17; font.weight: Font.DemiBold
                    color: view.c.text
                }
                Text {
                    Layout.fillWidth: true
                    visible: code.state === "installing"
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: app.t.code_installing_sub
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: view.c.muted
                }
                ProgressBar {
                    Layout.fillWidth: true
                    visible: code.state === "installing"
                    from: 0; to: 100
                    value: Math.max(0, code.progress)
                    indeterminate: code.progress < 0
                    Accessible.name: app.t.code_installing
                }
                OButton {
                    Layout.alignment: Qt.AlignHCenter
                    visible: code.state === "error" && code.error !== "code_unsupported" && code.error !== "code_offline"
                    kind: "primary"; iconName: "refresh"; text: app.t.code_retry
                    onClicked: code.retry()
                }
            }

            // the conversation is read again: said, never an empty welcome that looks like a lost history (09/11)
            ColumnLayout {
                anchors.centerIn: parent
                visible: code.state === "ready" && list.count === 0 && code.replaying
                spacing: 10
                BotFace { visible: code.bot !== ""; Layout.alignment: Qt.AlignHCenter; face: (bots.current && bots.current.face) || {}; size: 40; busy: true }
                Icon { visible: code.bot === ""; Layout.alignment: Qt.AlignHCenter; name: "ornis"; thinking: true; size: 30; color: view.c.accent }
                Text { Layout.alignment: Qt.AlignHCenter; text: app.t.code_loading_history
                       font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: view.c.muted }
            }
            // a bot that never spoke: who it is, three things to ask it
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(520, parent.width - 48)
                visible: code.bot !== "" && code.state === "ready" && list.count === 0 && !code.replaying
                spacing: 12
                BotFace { Layout.alignment: Qt.AlignHCenter; face: (bots.current && bots.current.face) || {}; size: 56 }
                Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                       text: (bots.current && bots.current.title) || ""
                       font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.DemiBold; color: view.c.text }
                Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                       text: (bots.current && bots.current.description) || app.t.bots_new_sub
                       font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: view.c.muted }
                Repeater {
                    model: [app.t.bots_idea_1, app.t.bots_idea_2, app.t.bots_idea_3]
                    AbstractButton {
                        id: botIdea
                        required property string modelData
                        Layout.fillWidth: true
                        implicitHeight: 40
                        hoverEnabled: true
                        onClicked: { input.text = modelData; view.send() }
                        Accessible.name: modelData
                        background: Rectangle { radius: 20; color: botIdea.hovered ? view.c.hover : view.c.card; border.color: view.c.line }
                        contentItem: Text { leftPadding: 16; rightPadding: 16; verticalAlignment: Text.AlignVCenter
                                            text: botIdea.modelData; elide: Text.ElideRight
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: view.c.text }
                    }
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 8
                    Icon { name: "shieldCheck"; size: 14; color: view.c.okInk }
                    Text { text: (app.t.bots_autonome_note || "") + " · " + app.t.code_local
                           font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: view.c.muted }
                }
            }
            // a new conversation: what Code does, three ideas
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(560, parent.width - 48)
                visible: code.bot === "" && code.state === "ready" && list.count === 0 && !code.replaying
                spacing: 12
                Text {
                    Layout.fillWidth: true
                    text: app.t.code_title_new.replace("%1", code.folderName)
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.DemiBold
                    color: view.c.text
                }
                Text {
                    Layout.fillWidth: true
                    text: app.t.code_lead
                    wrapMode: Text.Wrap
                    lineHeight: 1.25
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: view.c.muted
                }
                RowLayout {                      // the personal folder: said, and another one in one click
                    visible: code.folder === code.homeFolder
                    Layout.fillWidth: true
                    spacing: 8
                    Icon { name: "info"; size: 14; color: view.c.muted }
                    Text {
                        Layout.fillWidth: true
                        text: app.t.code_home_note
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: view.c.muted
                    }
                    OButton { kind: "quiet"; iconName: "folder"; text: app.t.code_choose_folder; height_: 28; onClicked: view.folderPickRequested() }
                }
                Repeater {
                    model: [app.t.code_example_1, app.t.code_example_2, app.t.code_example_3]
                    AbstractButton {
                        id: idea
                        required property string modelData
                        Layout.fillWidth: true
                        implicitHeight: 40
                        hoverEnabled: true
                        onClicked: { input.text = modelData; view.send() }
                        Accessible.name: modelData
                        background: Rectangle { radius: 10; color: idea.hovered ? view.c.hover : view.c.card; border.color: view.c.line }
                        contentItem: RowLayout {
                            spacing: 10
                            Item { implicitWidth: 2 }
                            Icon { name: "sparkle"; size: 14; color: view.c.accent }
                            Text { Layout.fillWidth: true; text: idea.modelData; elide: Text.ElideRight
                                   font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: view.c.text }
                        }
                    }
                }
                RowLayout {
                    visible: code.bot === ""
                    spacing: 8
                    Icon { name: code.sandbox ? "shieldCheck" : "shield"; size: 14; color: code.sandbox ? view.c.okInk : view.c.saffronInk }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: (code.sandbox ? app.t.code_sandbox : app.t.code_no_sandbox) + " · " + app.t.code_local
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: view.c.muted
                    }
                }
                RowLayout {
                    visible: code.bot !== ""
                    spacing: 8
                    Icon { name: "shieldCheck"; size: 14; color: view.c.okInk }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: (app.t.bots_autonome_note || "") + " · " + app.t.code_local
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: view.c.muted
                    }
                }
            }

            ListView {
                id: list
                anchors.fill: parent
                visible: count > 0
                clip: true
                model: code.items
                // bots: tools and thoughts are hidden (height 0); a spacing between them all made long empty
                // stretches (09/11) — there, each shown row carries its own gap
                readonly property int gap: code.bot !== "" ? 12 : 0
                spacing: code.bot !== "" ? 0 : 12
                topMargin: 20; bottomMargin: 20
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; onPressedChanged: if (pressed) view.stick = false }
                onMovementStarted: view.stick = false
                onAtYEndChanged: if (atYEnd) view.stick = true
                // the wheel starts no « movement »: scrolling up to read stops the following (as the Discussions)
                WheelHandler { target: null; blocking: false; onWheel: ev => { if (ev.angleDelta.y > 0) view.stick = false } }
                delegate: DelegateChooser {
                    role: "kind"
                    DelegateChoice { roleValue: "tool"; delegate: Item {
                        id: d1; required property var item; required property int index
                        // Bot chat: tools stay invisible — only the typing bubble and the answer
                        width: list.width; height: code.bot !== "" ? 0 : c1.implicitHeight
                        visible: code.bot === ""
                        ToolCard { id: c1; x: (list.width - view.column) / 2 + 44; width: view.column - 44;   // in the answer's column, as the steps of the Discussions
                                   entry: d1.item; rowIndex: d1.index }
                    } }
                    DelegateChoice { roleValue: "error"; delegate: Item {
                        id: d2; required property var item
                        width: list.width; height: c2.implicitHeight + list.gap
                        ErrorCard { id: c2; x: (list.width - view.column) / 2; width: view.column; entry: d2.item }
                    } }
                    DelegateChoice { roleValue: "planready"; delegate: Item {
                        id: d6; required property var item
                        width: list.width; height: code.bot !== "" || d6.item.done ? 0 : c6.implicitHeight
                        visible: code.bot === "" && !d6.item.done
                        Rectangle {
                            id: c6
                            x: (list.width - view.column) / 2; width: view.column
                            implicitHeight: 48
                            radius: 10
                            color: view.c.saffronTint
                            border.color: view.c.saffron
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 8
                                spacing: 10
                                Icon { name: "list"; size: 15; color: view.c.saffronInk }
                                Text { Layout.fillWidth: true; text: app.t.code_plan_ready; wrapMode: Text.Wrap
                                       font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: view.c.text }
                                OButton { text: app.t.plan_keep; height_: 30; onClicked: input.forceActiveFocus() }
                                OButton { kind: "primary"; text: app.t.plan_run; height_: 30; enabled: !code.busy; onClicked: code.runPlan() }
                            }
                        }
                    } }
                    DelegateChoice { roleValue: "changes"; delegate: Item {
                        id: d5; required property var item
                        width: list.width; height: code.bot !== "" ? 0 : c5.implicitHeight
                        visible: code.bot === ""
                        ChangesCard { id: c5; x: (list.width - view.column) / 2; width: view.column; entry: d5.item }
                    } }
                    DelegateChoice { roleValue: "notice"; delegate: Item {    // the turn went on by itself
                        id: d7; required property var item
                        width: list.width
                        // [SILENT] peer replies leave an empty notice: take no space
                        height: d7.item.key === "bots_silent" ? 0 : c7.implicitHeight + list.gap
                        visible: d7.item.key !== "bots_silent"
                        RowLayout {
                            id: c7
                            x: (list.width - view.column) / 2; width: view.column
                            spacing: 8
                            Icon { name: d7.item.key === "bots_group_turn" ? "people" : "refresh"; size: 13; color: view.c.muted }
                            Text {
                                Layout.fillWidth: true
                                text: String(app.t[d7.item.key] || "").replace("%1", d7.item.content || "")
                                wrapMode: width > 80 ? Text.Wrap : Text.NoWrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
                                color: view.c.muted
                            }
                        }
                    } }
                    DelegateChoice { roleValue: "unreadmark"; delegate: Item {   // what the bot said while you were away
                        width: list.width; height: 28 + list.gap
                        RowLayout {
                            x: (list.width - view.column) / 2; width: view.column
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 10
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.danger }
                            Text { text: app.t.unread_bar; font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                   font.capitalization: Font.AllUppercase; font.letterSpacing: 0.6; color: view.c.danger }
                        }
                    } }
                    DelegateChoice { roleValue: "peer"; delegate: Item {
                        id: dPeer; required property var item
                        width: list.width
                        height: (dPeer.item.count || 0) > 0 ? peerPill.implicitHeight + 8 + list.gap : 0
                        visible: (dPeer.item.count || 0) > 0
                        AbstractButton {
                            id: peerPill
                            anchors.horizontalCenter: parent.horizontalCenter
                            implicitHeight: 28
                            implicitWidth: peerRow.implicitWidth + 20
                            hoverEnabled: true
                            onClicked: {
                                peerPopup.openFor(dPeer.item.peer || "", dPeer.item.content || "")
                                dPeer.item.unread = false
                            }
                            background: Rectangle {
                                radius: 14
                                color: peerPill.hovered ? view.c.hover : view.c.field
                                border.width: 1; border.color: view.c.line
                            }
                            contentItem: Row {
                                id: peerRow
                                anchors.centerIn: parent
                                spacing: 6
                                BotFace {
                                    face: {
                                        const id = dPeer.item.peer || ""
                                        const all = bots.list.concat(bots.hidden)
                                        const hit = all.find(b => b.id === id)
                                        return (hit && hit.face) || {}
                                    }
                                    size: 16
                                }
                                Text {
                                    text: {
                                        const id = dPeer.item.peer || ""
                                        const all = bots.list.concat(bots.hidden)
                                        const hit = all.find(b => b.id === id)
                                        const name = (hit && hit.title) || id
                                        return (dPeer.item.count || 1) <= 1
                                            ? app.t.bots_peer_1.replace("%1", name)
                                            : app.t.bots_peer_n.replace("%1", String(dPeer.item.count || 1))
                                                               .replace("%2", name)
                                    }
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                    color: view.c.muted
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Rectangle {
                                    visible: !!dPeer.item.unread
                                    width: 6; height: 6; radius: 3
                                    color: view.c.saffron
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    } }
                    // what Ornis thought: the same folded block as in the Discussions (« Réflexion », its last lines
                    // going by while it thinks), in the answer's column
                    DelegateChoice { roleValue: "thought"; delegate: Item {
                        id: d3; required property var item; required property int index
                        width: list.width; height: code.bot !== "" || !c3.visible ? 0 : c3.implicitHeight
                        visible: code.bot === ""
                        ReasoningBlock { id: c3; x: (list.width - view.column) / 2 + 44; width: view.column - 44
                                         text: String(d3.item.content || "")
                                         autoLive: true
                                         live: code.busy && d3.index === list.count - 1 }
                    } }
                    DelegateChoice { delegate: Item {
                        id: d4; required property var item; required property int index
                        // Bot chat: an answer with no text yet (only tools behind it) is no empty bubble
                        readonly property bool blank: code.bot !== "" && d4.item.kind === "agent"
                                                      && String(d4.item.content || "").trim() === ""
                        width: list.width; height: blank ? 0 : c4.implicitHeight + list.gap
                        visible: !blank
                        Message { id: c4; x: (list.width - view.column) / 2; width: view.column; message: d4.item
                                  lastMine: d4.index === code.lastUser
                                  localFiles: true
                                  chatOnly: code.bot !== ""
                                  botFace: code.bot !== "" && bots.current ? bots.current.face : null
                                  botName: code.bot !== "" && bots.current ? (bots.current.title || "") : ""
                                  onFileRequested: path => view.openInBench(path)
                                  editable: d4.index === code.lastUser && !code.busy
                                  onEditRequested: { const t = code.editLast(); if (t) { input.text = t; input.cursorPosition = input.length; input.forceActiveFocus() } }
                                  // Bot: the live status is the bubble above the box; the answer streams once it has text
                                  streaming: code.busy && d4.index === list.count - 1 && d4.item.kind === "agent"
                                  // 👍 / 👎 and the « Was it useful? » card of Code and Bots (CodeChat.vote, answerCard, voteDetail)
                                  voter: code
                                  reasons: ["wrong", "not_asked", "didnt_act", "stuck", "broke", "too_long", "other"]
                                  shareNote: app.t.vote_share_note_code
                                  why: view.why
                                  onWhyEdited: state => view.why = state }
                    } }
                }
            }
            // back to the bottom when scrolled up (as the Discussions)
            AbstractButton {
                id: toBottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 12
                implicitWidth: 36; implicitHeight: 36
                visible: opacity > 0
                opacity: list.count > 0 && !list.atYEnd && list.contentHeight > list.height ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 140 } }
                hoverEnabled: true
                onClicked: { view.stick = true; view.toEnd() }
                Accessible.name: app.t.scroll_down
                ToolTip.text: app.t.scroll_down
                ToolTip.visible: hovered
                ToolTip.delay: 450
                background: Rectangle {
                    radius: width / 2
                    color: toBottom.hovered ? view.c.hover : view.c.card
                    border.width: 1; border.color: view.c.line
                }
                contentItem: Item { Icon { anchors.centerIn: parent; name: "chevronDown"; size: 18; color: view.c.text } }
            }
        }

        // ---- the plan --------------------------------------------------------------------------------------------
        Rectangle {
            id: planBox
            property bool open: false
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.preferredHeight: visible ? planCol.implicitHeight + 16 : 0
            // the agent's to-do list while it works on it; once all done and the turn over, it goes
            visible: code.plan.length > 0 && (code.busy || code.plan.some(p => p.status !== "completed"))
            radius: 10
            color: view.c.card
            border.color: view.c.line
            ColumnLayout {
                id: planCol
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4
                AbstractButton {
                    Layout.fillWidth: true
                    implicitHeight: 24
                    onClicked: planBox.open = !planBox.open
                    Accessible.name: app.t.code_plan
                    contentItem: RowLayout {
                        spacing: 8
                        Icon { name: "checklist"; size: 14; color: view.c.accent }
                        Text {
                            Layout.fillWidth: true
                            readonly property int done: code.plan.filter(p => p.status === "completed").length
                            readonly property var current: code.plan.find(p => p.status === "in_progress")
                            text: app.t.code_plan + " · " + done + "/" + code.plan.length + (current ? " · " + current.text : "")
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                            color: view.c.text
                        }
                        Icon { name: planBox.open ? "collapse" : "expand"; size: 12; color: view.c.muted }
                    }
                }
                Repeater {
                    model: planBox.open ? code.plan : []
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 8
                        Icon {
                            name: modelData.status === "completed" ? "done" : modelData.status === "in_progress" ? "play" : "circle"
                            size: 13
                            color: modelData.status === "completed" ? view.c.okInk : modelData.status === "in_progress" ? view.c.accent : view.c.muted
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.text
                            wrapMode: Text.Wrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.strikeout: modelData.status === "completed"
                            color: modelData.status === "completed" ? view.c.muted : view.c.text
                        }
                    }
                }
            }
        }

        // ---- the composer ----------------------------------------------------------------------------------------
        Flow {                                  // the files joined to the message
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.topMargin: 8
            visible: code.attachments.length > 0
            spacing: 6
            Repeater {
                model: code.attachments
                LinkBadge {
                    required property var modelData
                    required property int index
                    label: modelData.short
                    iconName: modelData.dir ? "folder" : "note"
                    tip: modelData.path
                    onRemoveRequested: { code.removeAttachment(index); input.forceActiveFocus() }
                }
            }
        }
        // written while Ornis works: waiting above the box (send now, change, drop), the same as in the Discussions
        QueueDock {
            items: code.later
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.topMargin: visible ? 6 : 0
            onSendNow: i => code.sendLaterNow(i)
            onEditRequested: i => code.editLater(i)
            onDropRequested: i => code.dropLater(i)
        }
        // Bot: live status bubble (réfléchit / écrit un fichier / appelle un outil…) — not part of the history
        BotStatusBubble {
            active: code.chatTyping && !codePerm.visible && !codeQuestions.visible
            text: code.botStatus
            face: bots.current ? bots.current.face : null
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.topMargin: active ? 8 : 0
        }
        // Ornis is working: one line above the box (project sessions only)
        WorkingLine {
            busy: code.bot === "" && code.busy && code.folder !== "" && !codePerm.visible && !codeQuestions.visible
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.preferredHeight: implicitHeight
            Layout.topMargin: busy ? 6 : 0
        }
        // the agent asks before acting: above the box, the same as the Discussion mode (once, always this pattern
        // in this conversation, refuse, or refuse and say what to do instead)
        PermissionDock {
            id: codePerm
            readonly property var r: code.asking
            readonly property bool command_: r.tool === "execute" && !!r.command
            visible: r.row !== undefined && code.folder !== ""
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.topMargin: 8
            iconName: r.icon || "sparkle"
            title: r.approvalTitle || (command_ ? app.t.perm_title_command : r.tool === "edit" || r.tool === "delete" || r.tool === "move" ? app.t.perm_title_files
                   : app.t.code_permission_wanted)
            subtitle: command_ || r.tool === "edit" ? (r.path || "") : ""
            summary: command_ ? "" : (r.title || r.path || "")
            hasCommand: command_
            commandEditable: false
            command: command_ ? r.command : ""
            previewLines: r.diff || []
            options: (r.options || []).map(o => ({
                id: o.id,
                kind: o.kind === "allow_once" ? "allow" : o.kind === "allow_always" ? "always" : "deny",
                label: o.kind === "allow_once" ? (o.label || app.t.code_allow)
                       : o.kind === "allow_always" ? app.t.code_allow_always.replace("%1", o.label || "…") : app.t.code_reject
            })).concat([{ id: "__tell", kind: "tell", label: app.t.perm_deny_tell }])
            onChosen: (id, command) => {
                const row = r.row
                if (id === "__tell") {
                    const no = (r.options || []).find(o => String(o.kind).indexOf("reject") === 0)
                    code.answer(row, no ? no.id : "reject_once")
                } else {
                    code.answer(row, id)
                }
                input.forceActiveFocus()
            }
        }
        // Ornis asks the user to choose (Vibe's ask_user_question): the same form as the Discussion mode
        QuestionsDock {
            id: codeQuestions
            visible: code.questions.length > 0 && code.folder !== ""
            questions: code.questions
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.topMargin: 8
            onAnswered: answers => { code.answerQuestions(answers); input.forceActiveFocus() }
            onSkipped: { code.skipQuestions(); input.forceActiveFocus() }
        }
        Rectangle {
            id: composerBox
            visible: code.folder !== ""
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.topMargin: 8
            Layout.bottomMargin: 14
            Layout.preferredHeight: Math.min(260, Math.max(52, input.implicitHeight + 16)) + toolbar.implicitHeight + 8
            radius: 16
            color: view.c.field
            border.width: input.activeFocus || drop.containsDrag || pathDrop.containsDrag ? 2 : 1
            border.color: input.activeFocus || drop.containsDrag || pathDrop.containsDrag ? view.c.accentLine : view.c.line
            DropArea {                           // a file of the panel dropped on the box: @path in the text
                id: pathDrop
                anchors.fill: parent
                z: 5
                keys: ["application/x-ornis-path"]
                onDropped: d => {
                    const path = d.getDataAsString("application/x-ornis-path")
                    if (path) { view.mention(path); d.acceptProposedAction() }
                }
            }
            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 6
                spacing: 0
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: 8; Layout.rightMargin: 8
                    TextArea {
                        id: input
                        // always writable: sending starts the agent again if it stopped (idle, error)
                        placeholderText: code.waiting ? app.t.code_asks
                                         : code.bot !== "" ? app.t.bots_placeholder.replace("%1", code.folderName)
                                         : app.t.code_placeholder
                        wrapMode: TextArea.Wrap
                        background: null
                        font.family: "Schibsted Grotesk"; font.pixelSize: app.textSize
                        color: view.c.text
                        placeholderTextColor: view.c.muted
                        Accessible.name: app.t.code_placeholder
                        onTextChanged: view.updateMention()
                        onCursorPositionChanged: if (mentionPopup.opened) view.updateMention()
                        Keys.onReturnPressed: event => view.enter(event)
                        Keys.onEnterPressed: event => view.enter(event)
                        Keys.onTabPressed: event => {
                            if (mentionPopup.opened) { view.applyMention(view.mentionRows[view.mentionIndex]); event.accepted = true }
                            else event.accepted = false
                        }
                        Keys.onUpPressed: event => {
                            if (mentionPopup.opened) { view.mentionIndex = (view.mentionIndex - 1 + view.mentionRows.length) % view.mentionRows.length; event.accepted = true }
                            else if ((input.text === "" || view.historyBack > 0) && input.text.lastIndexOf("\n", input.cursorPosition - 1) < 0) {
                                const older = code.historyAt(view.historyBack + 1)      // the messages sent here, as in a terminal
                                if (older) { view.historyBack++; input.text = older; input.cursorPosition = input.length }
                                event.accepted = true
                            }
                            else event.accepted = false
                        }
                        Keys.onDownPressed: event => {
                            if (mentionPopup.opened) { view.mentionIndex = (view.mentionIndex + 1) % view.mentionRows.length; event.accepted = true }
                            else if (view.historyBack > 0 && input.text.indexOf("\n", input.cursorPosition) < 0) {
                                view.historyBack--
                                input.text = view.historyBack > 0 ? code.historyAt(view.historyBack) : ""
                                input.cursorPosition = input.length
                                event.accepted = true
                            }
                            else event.accepted = false
                        }
                        Keys.onPressed: event => {
                            if (event.matches(StandardKey.Paste) && code.paste()) event.accepted = true   // an image, files
                        }
                        Keys.onEscapePressed: event => {
                            if (mentionPopup.opened) { mentionPopup.close(); event.accepted = true }
                            else event.accepted = false
                        }
                        // Maj+Tab, as in Claude Code: Demander → Modifier → Autonome → Plan → Ask → Demander
                        Keys.onBacktabPressed: event => {
                            if (code.bot !== "" || code.busy) { event.accepted = true; return }
                            if (code.agentMode === "plan") code.setAgentMode("ask")
                            else if (code.agentMode === "ask") { code.setAgentMode("agent"); code.setMode("ask") }
                            else if (code.mode === "auto") code.setAgentMode("plan")
                            else code.setMode(code.mode === "ask" ? "edits" : "auto")
                            event.accepted = true
                        }
                    }
                }
                RowLayout {                      // the toolbar under the text (the same as in the Discussion mode)
                    id: toolbar
                    Layout.fillWidth: true
                    Layout.leftMargin: 6; Layout.rightMargin: 8; Layout.bottomMargin: 6
                    spacing: 4
                    OButton {                    // "+": files of this computer
                        Layout.alignment: Qt.AlignVCenter
                        kind: "quiet"; iconName: "plus"; iconSize: 19; height_: 32
                        tip: app.t.code_attach
                        enabled: code.state === "ready"
                        onClicked: attachDialog.open()
                    }
                    AbstractButton {             // "@": a file of the project (sessions only — bots stay a plain chat)
                        id: atBtn
                        visible: code.bot === ""
                        Layout.alignment: Qt.AlignVCenter
                        implicitWidth: 30; implicitHeight: 32
                        hoverEnabled: true
                        onClicked: { input.insert(input.cursorPosition, (input.cursorPosition > 0 && !/\s$/.test(input.text.slice(0, input.cursorPosition)) ? " @" : "@")); input.forceActiveFocus() }
                        Accessible.name: app.t.mention_tip
                        ToolTip.text: app.t.mention_tip; ToolTip.delay: 500; ToolTip.visible: hovered
                        background: Rectangle { radius: 14; color: atBtn.hovered ? view.c.hover : "transparent" }
                        contentItem: Text { horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: "@"
                                            font.family: "JetBrains Mono"; font.pixelSize: 15; font.weight: Font.DemiBold
                                            color: atBtn.hovered ? view.c.text : view.c.muted }
                    }
                    AbstractButton {             // "/": an action (a command) — hidden on bots
                        id: slashBtn
                        visible: code.bot === ""
                        Layout.alignment: Qt.AlignVCenter
                        implicitWidth: 30; implicitHeight: 32
                        hoverEnabled: true
                        onClicked: { if (input.text === "") input.text = "/"; input.cursorPosition = input.text.length; input.forceActiveFocus(); view.updateMention() }
                        Accessible.name: app.t.slash_tip || "/"
                        ToolTip.text: app.t.slash_tip || ""; ToolTip.delay: 500; ToolTip.visible: hovered && ToolTip.text !== ""
                        background: Rectangle { radius: 14; color: slashBtn.hovered ? view.c.hover : "transparent" }
                        contentItem: Text { horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: "/"
                                            font.family: "JetBrains Mono"; font.pixelSize: 15; font.weight: Font.DemiBold
                                            color: slashBtn.hovered ? view.c.text : view.c.muted }
                    }
                    ToolbarChip {                // the mode: Agent, Plan or Ask — on the left, the same chip as the Discussion's
                        id: modeBtn
                        readonly property string m: code.agentMode
                        visible: code.bot === ""     // bots: always classic Agent
                        enabled: !code.busy
                        Layout.alignment: Qt.AlignVCenter
                        Layout.leftMargin: 4
                        onClicked: view.openModes()
                        menuOpen: workMenu.opened
                        iconName: m === "plan" ? "list" : m === "ask" ? "chat" : "ornis"
                        mascot: m === "agent"
                        label: m === "plan" ? app.t.mode_plan : m === "ask" ? app.t.mode_ask : app.t.mode_agent
                        detail: m === "plan" && view.width >= 640 ? app.t.plan_readonly : ""
                        tone: m === "plan" ? "saffron" : m === "ask" ? "tint" : "plain"
                        tip: (m === "plan" ? app.t.code_plan_sub : m === "ask" ? app.t.code_ask_sub : app.t.code_code_sub) + "  ·  " + app.t.mode_cycle_tip
                    }
                    Item { Layout.fillWidth: true }
                    ToolbarChip {                // what Ornis does without asking: on the right, the same chip as the Discussion's
                        id: autoBtn
                        enabled: !code.busy || code.bot !== ""
                        Layout.alignment: Qt.AlignVCenter
                        onClicked: if (code.bot === "") view.openAbove(modeMenu, autoBtn)
                        menuOpen: modeMenu.opened
                        // bots: Autonome is forced (shown, not a menu)
                        iconName: code.bot !== "" ? "play" : view.modeInfo[code.mode].icon
                        label: code.bot !== "" ? app.t.code_mode_auto : view.modeInfo[code.mode].label
                        showLabel: view.width >= 560 || code.mode === "auto" || code.bot !== ""
                        chevron: code.bot === ""
                        tone: code.bot !== "" || code.mode === "auto" ? "saffron" : code.mode === "edits" ? "tint" : "plain"
                        tip: code.bot !== "" ? app.t.bots_autonome_note
                             : view.modeInfo[code.mode].sub + "  ·  " + (code.sandbox ? app.t.code_sandbox : app.t.code_no_sandbox)
                    }
                    AbstractButton {             // dictation, as in the Discussion's box (the same recorder)
                        id: codeMic
                        readonly property var v: chat.voice
                        visible: v.available
                        Layout.alignment: Qt.AlignVCenter
                        implicitWidth: v.recording ? codeMicRow.implicitWidth + 20 : 32; implicitHeight: 32
                        hoverEnabled: true
                        enabled: !v.busy
                        onClicked: v.toggle()
                        Accessible.name: v.recording ? app.t.dictate_stop : v.busy ? app.t.dictate_busy : app.t.dictate
                        ToolTip.text: Accessible.name; ToolTip.delay: 450; ToolTip.visible: hovered
                        background: Rectangle { radius: height / 2; color: codeMic.v.recording ? view.c.danger : codeMic.hovered ? view.c.hover : "transparent" }
                        contentItem: Item {
                            Row {
                                id: codeMicRow
                                anchors.centerIn: parent
                                spacing: 6
                                Rectangle { visible: codeMic.v.recording; anchors.verticalCenter: parent.verticalCenter; width: 10; height: 10; radius: 2; color: "white" }
                                Icon { visible: !codeMic.v.recording; anchors.verticalCenter: parent.verticalCenter; name: "mic"; size: 18
                                       color: codeMic.hovered ? view.c.text : view.c.muted; opacity: codeMic.v.busy ? 0.5 : 1 }
                                Text { visible: codeMic.v.recording; anchors.verticalCenter: parent.verticalCenter
                                       text: Math.floor(codeMic.v.elapsed / 60) + ":" + String(codeMic.v.elapsed % 60).padStart(2, "0")
                                       font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: "white" }
                            }
                        }
                        Connections {
                            target: chat.voice
                            function onText(said) { if (view.visible) { input.insert(input.cursorPosition, said); input.forceActiveFocus() } }
                        }
                    }
                    ContextGauge {               // what the next step carries; a click compacts (as in the Discussion mode)
                        Layout.alignment: Qt.AlignVCenter
                        visible: code.bot === ""    // a bot's thread never ends: it summarises itself, nothing to watch
                        info: code.context
                        onTipDismissed: key => code.dismissTip(key)
                        onTipRequested: prompt => { input.text = prompt; input.forceActiveFocus() }
                        busy: code.busy
                        onCompactRequested: code.compact()
                    }
                    AbstractButton {             // send, or while Ornis works, stop
                        id: action
                        Layout.alignment: Qt.AlignVCenter
                        implicitWidth: 34; implicitHeight: 34
                        hoverEnabled: true
                        enabled: code.busy || input.text.trim() !== ""
                        onClicked: code.busy ? code.stop() : view.send()
                        Accessible.name: code.busy ? app.t.stop : app.t.send
                        ToolTip.text: Accessible.name; ToolTip.delay: 450; ToolTip.visible: hovered
                        background: Rectangle {
                            radius: 17
                            color: code.busy ? view.c.text : action.enabled ? view.c.famCommunicate : view.c.hover
                        }
                        contentItem: Item {
                            Rectangle { visible: code.busy; anchors.centerIn: parent; width: 11; height: 11; radius: 2; color: view.c.bg }
                            Icon { visible: !code.busy; anchors.centerIn: parent; name: "send"; size: 16
                                   color: action.enabled ? "white" : view.c.muted }
                        }
                    }
                }
            }
        }
    }
    readonly property bool routinesOpen: view.benchTab === "routines"
    function openRoutines() { view.toggleBench("routines") }
    function closeRoutines() { if (view.benchTab === "routines") app.setPref("bench_tab", "") }

    Popup {
        id: peerPopup
        objectName: "peerPopup"
        property string peerId: ""
        property var rows: []
        modal: true
        padding: 16
        width: Math.min(420, view.width - 48)
        height: Math.min(360, view.height - 80)
        anchors.centerIn: Overlay.overlay
        background: Rectangle { radius: 14; color: view.c.card; border.color: view.c.line }
        function openFor(peer, preview) {
            peerId = peer
            rows = bots.exchange(code.bot, peer)
            bots.markSeen(code.bot, peer)
            open()
        }
        readonly property string peerTitle: {
            const all = bots.list.concat(bots.hidden)
            const hit = all.find(b => b.id === peerPopup.peerId)
            return (hit && hit.title) || peerPopup.peerId
        }
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Text {
                text: app.t.bots_peer_title.replace("%1", peerPopup.peerTitle)
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                color: view.c.text
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: peerPopup.rows
                spacing: 8
                delegate: Column {
                    required property var modelData
                    width: ListView.view.width
                    spacing: 2
                    Text {
                        text: (modelData.from === code.bot ? app.t.you : modelData.from) + " · "
                              + Qt.formatTime(new Date(modelData.at * 1000), "hh:mm")
                        font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: view.c.muted
                    }
                    Text {
                        width: parent.width
                        text: modelData.text
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: view.c.text
                    }
                }
            }
            OButton { kind: "quiet"; text: app.t.close; Layout.alignment: Qt.AlignRight; onClicked: peerPopup.close() }
        }
    }

    // ---- the panel on the right (Fichiers, Modifications, Plan, Terminal) -----------------------------------------------
    Rectangle {                              // under the panel when it covers the conversation
        anchors.fill: parent
        visible: view.benchTab !== "" && view.benchOver && !view.benchMax
        color: view.c.scrim
        opacity: visible ? 1 : 0
        z: 9
        MouseArea { anchors.fill: parent; onClicked: view.toggleBench(view.benchTab) }
    }
    BenchPanel {
        id: benchPanel
        z: 10
        visible: view.benchTab !== ""
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: view.benchWidth
        tab: view.benchTab || "files"
        maximized: view.benchMax
        onCloseRequested: { app.setPref("bench_tab", ""); view.benchMax = false; view.focusInput() }
        onMaximizeRequested: view.benchMax = !view.benchMax
        onMentionRequested: path => { view.mention(path); if (view.benchOver) { view.benchMax = false; app.setPref("bench_tab", "") } }
        onCommitRequested: commitDialog.openFor()
        onTabChanged: if (tab !== view.benchTab && view.benchTab !== "") app.setPref("bench_tab", tab)
        Component.onCompleted: if (view.benchTab !== "") show(view.benchTab)
        // a soft shadow when it lies over the conversation
        Rectangle {
            visible: view.benchOver
            anchors { right: parent.left; top: parent.top; bottom: parent.bottom }
            width: 18
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 1; color: Qt.rgba(0, 0, 0, theme.dark ? 0.35 : 0.10) }
            }
        }
        MouseArea {                          // its left edge: dragged, it sets the width (kept)
            visible: !view.benchOver
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; leftMargin: -3 }
            width: 7
            cursorShape: Qt.SplitHCursor
            hoverEnabled: true
            property real startX: 0
            property real startW: 0
            onPressed: mouse => { startX = mapToItem(view, mouse.x, 0).x; startW = view.benchWidth }
            onPositionChanged: mouse => { if (pressed) view.benchDrag = Math.max(300, Math.min(view.width * 0.62, startW + startX - mapToItem(view, mouse.x, 0).x)) }
            onReleased: { app.setPref("bench_width", Math.round(view.benchWidth)); view.benchDrag = -1 }
            Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 2; height: parent.height
                        color: parent.containsMouse || parent.pressed ? view.c.accentLine : "transparent" }
        }
    }
    Shortcut { sequence: "Ctrl+Shift+E"; enabled: view.visible && code.folder !== ""; onActivated: view.toggleBench("files") }
    Shortcut { sequence: "Ctrl+Shift+G"; enabled: view.visible && code.folder !== ""; onActivated: view.toggleBench("changes") }
    Shortcut { sequence: "Ctrl+`"; enabled: view.visible && code.folder !== ""; onActivated: view.toggleBench("terminal") }

    // @-suggestions above the composer
    Popup {
        id: mentionPopup
        parent: composerBox
        x: 0
        y: -height - 6
        width: Math.min(composerBox.width, 520)
        padding: 6
        focus: false
        closePolicy: Popup.CloseOnPressOutside
        background: Rectangle { radius: 10; color: view.c.card; border.color: view.c.line }
        contentItem: Column {
            spacing: 2
            Repeater {
                model: view.mentionRows
                AbstractButton {
                    id: mrow
                    required property var modelData
                    required property int index
                    width: mentionPopup.width - 12
                    implicitHeight: 30
                    hoverEnabled: true
                    onClicked: view.applyMention(modelData)
                    Accessible.name: modelData.path
                    background: Rectangle { radius: 6; color: mrow.index === view.mentionIndex || mrow.hovered ? view.c.hover : "transparent" }
                    contentItem: RowLayout {
                        spacing: 8
                        Item { implicitWidth: 2 }
                        Icon { name: mrow.modelData.icon || "note"; size: 13; color: view.c.muted }
                        Text { text: mrow.modelData.name || mrow.modelData.label; font.family: view.popupKind === "slash" ? "JetBrains Mono" : "Schibsted Grotesk"
                               font.pixelSize: 13; font.weight: Font.Medium; color: view.c.text }
                        Text { Layout.fillWidth: true; text: mrow.modelData.path || mrow.modelData.sub || ""; elide: Text.ElideRight
                               font.family: "JetBrains Mono"; font.pixelSize: 11; color: view.c.muted }
                    }
                }
            }
        }
    }
    FileDialog {
        id: attachDialog
        title: app.t.code_attach
        fileMode: FileDialog.OpenFiles
        currentFolder: code.folder ? "file://" + code.folder : ""
        onAccepted: code.addFiles(selectedFiles)
    }
    // files dropped anywhere on the view join the message
    DropArea {
        id: drop
        anchors.fill: parent
        enabled: code.state === "ready"
        keys: ["text/uri-list"]
        onDropped: drop => { if (drop.hasUrls) { code.addFiles(drop.urls); drop.accept() } }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 8
            visible: drop.containsDrag
            radius: 14
            color: "transparent"
            border.width: 2
            border.color: view.c.accent
            Rectangle { anchors.fill: parent; radius: 14; color: view.c.accent; opacity: 0.06 }
            Text { anchors.centerIn: parent; text: app.t.code_drop; font.family: "Schibsted Grotesk"; font.pixelSize: 16
                   font.weight: Font.DemiBold; color: view.c.accent }
        }
    }
    function enter(event) {
        if (mentionPopup.opened && view.mentionRows.length) {   // Entrée completes the suggestion, it never sends half a message
            view.applyMention(view.mentionRows[view.mentionIndex])
            event.accepted = true
            return
        }
        const ctrl = event.modifiers & Qt.ControlModifier
        const shift = event.modifiers & Qt.ShiftModifier
        if (shift || (app.prefs.enter_sends === false && !ctrl)) { event.accepted = false; return }
        view.send()
        event.accepted = true
    }
    Shortcut { sequence: "Esc"; enabled: view.visible && code.busy; onActivated: code.stop() }

    // a command or a title on one line: the agent's preamble (`export PATH=…`, `cd <the project>`) left out, the
    // other lines joined by ⏎
    function oneLine(text) {
        const lines = String(text || "").split("\n").map(l => l.trim())
            .filter(l => l !== "" && !/^export PATH=/.test(l) && !(code.folder && l === "cd " + code.folder))
        return lines.join("  ⏎  ")
    }

    // ---- the cards -------------------------------------------------------------------------------------------------
    // what a turn changed in the folder (checkpoint taken before it), and « Annuler ces modifications »
    ODialog {
        id: commitDialog
        parent: Overlay.overlay
        title: app.t.code_commit_title
        width: Math.min(520, view.width - 48)
        function openFor() {
            message.text = code.title || ""
            branch.text = ""
            open()
            message.forceActiveFocus()
            message.selectAll()
        }
        Text {
            Layout.fillWidth: true
            text: app.plural("code_git_dirty", code.git.dirty || 0) + " · " + app.t.code_branch_on + " " + (code.git.branch || "")
            font.family: "JetBrains Mono"; font.pixelSize: 12
            color: view.c.muted
        }
        Text { Layout.topMargin: 6; text: app.t.code_commit_message; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: view.c.text }
        OTextField { id: message; Layout.fillWidth: true; onAccepted: commitGo.clicked() }
        Text { Layout.topMargin: 6; text: app.t.code_commit_branch; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: view.c.text }
        OTextField { id: branch; Layout.fillWidth: true; placeholderText: app.t.code_commit_branch_ph }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: commitDialog.close() },
            OButton {
                id: commitGo
                kind: "primary"; iconName: "check"; text: app.t.code_commit
                enabled: message.text.trim() !== "" && /^[A-Za-z0-9._\/-]*$/.test(branch.text.trim())
                onClicked: { if (!enabled) return; code.commit(message.text, branch.text); commitDialog.close() }
            }
        ]
    }

    component ChangesCard: Rectangle {
            id: ch
            property var entry: ({})
            property bool open: false
            implicitHeight: chCol.implicitHeight + 16
            radius: 10
            color: view.c.card
            border.color: view.c.line
            opacity: entry.undone ? 0.7 : 1
            ColumnLayout {
                id: chCol
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AbstractButton {
                        Layout.fillWidth: true
                        implicitHeight: 28
                        hoverEnabled: true
                        onClicked: ch.open = !ch.open
                        Accessible.name: chLabel.text
                        contentItem: RowLayout {
                            spacing: 8
                            Icon { name: ch.entry.undone ? "restore" : "edit"; size: 14; color: view.c.muted }
                            Text {
                                id: chLabel
                                Layout.fillWidth: true
                                text: ch.entry.undone ? app.t.code_changes_undone
                                      : app.plural("code_files_changed", ch.entry.count || 0) + (ch.entry.added || ch.entry.removed ? "  ·  " + app.t.code_changes.replace("%1", ch.entry.added || 0).replace("%2", ch.entry.removed || 0) : "")
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                                color: view.c.text
                            }
                            Icon { name: "chevronDown"; size: 12; color: view.c.muted; rotation: ch.open ? 180 : 0 }
                        }
                    }
                    OButton {
                        visible: !ch.entry.undone
                        enabled: !code.busy
                        iconName: "restore"; text: app.t.code_undo; height_: 28
                        tip: app.t.code_undo_tip
                        onClicked: code.rewind(ch.entry.rev)
                    }
                }
                Repeater {
                    model: ch.open ? (ch.entry.files || []) : []
                    RowLayout {
                        id: fileRow
                        required property var modelData
                        readonly property bool back: (ch.entry.reverted || []).indexOf(modelData.path) >= 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        spacing: 8
                        HoverHandler { id: fileHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: view.showChange(ch.entry.rev, fileRow.modelData.path) }
                        Text {
                            text: modelData.status
                            font.family: "JetBrains Mono"; font.pixelSize: 12; font.weight: Font.Bold
                            color: modelData.status === "A" ? view.c.okInk : modelData.status === "D" ? view.c.danger : view.c.saffronInk
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.path
                            font.underline: fileHover.hovered
                            elide: Text.ElideMiddle
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: view.c.text
                        }
                        Text {
                            text: fileRow.back ? app.t.code_file_undone
                                  : (modelData.added ? "+" + modelData.added : "") + (modelData.removed ? "  −" + modelData.removed : "")
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: view.c.muted
                        }
                        OButton {           // this file only, back as it was before the turn
                            visible: !ch.entry.undone && !fileRow.back
                            enabled: !code.busy
                            kind: "quiet"; iconName: "restore"; iconSize: 13; height_: 24
                            tip: app.t.code_file_undo
                            onClicked: code.rewindFile(ch.entry.rev, fileRow.modelData.path)
                        }
                    }
                }
            }
    }
    component ErrorCard: Rectangle {
            property var entry: ({})
            implicitHeight: errRow.implicitHeight + 20
            radius: 10
            color: entry.key === "code_quota" || entry.key === "code_stopped" ? view.c.saffronTint : view.c.dangerTint
            RowLayout {
                id: errRow
                anchors.fill: parent
                anchors.margins: 10
                spacing: 10
                Icon { name: entry.key === "code_stopped" ? "stop" : "warning"; size: 15
                       color: entry.key === "code_quota" || entry.key === "code_stopped" ? view.c.saffronInk : view.c.danger }
                Text {
                    Layout.fillWidth: true
                    text: app.t[entry.key] || app.t.code_error
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: view.c.text
                }
                OButton { visible: entry.key === "code_quota"; text: app.t.code_plans; height_: 28; onClicked: app.openPlans() }
            }
    }
    component ToolCard: Rectangle {
            id: card
            property var entry: ({})
            property int rowIndex: -1
            // open by itself: what asks, a command that failed, a short change (seen without a click)
            property bool open: !!entry.permission || (entry.tool === "execute" && entry.status === "failed")
                                || (entry.tool === "edit" && (entry.diff || []).length > 0 && (entry.diff || []).length <= 14)
            readonly property bool asking: !!entry.permission
            readonly property var lines: entry.diff || []
            implicitHeight: cardCol.implicitHeight + 16
            radius: 10
            color: asking ? view.c.saffronTint : view.c.card
            border.color: asking ? view.c.saffron : view.c.line
            Accessible.role: Accessible.Grouping
            Accessible.name: (entry.title || entry.tool) + (entry.status === "failed" ? ", " + app.t.code_tool_failed : "")
            ColumnLayout {
                id: cardCol
                anchors.fill: parent
                anchors.margins: 8
                spacing: 6
                AbstractButton {
                    Layout.fillWidth: true
                    implicitHeight: 26
                    hoverEnabled: true
                    onClicked: card.open = !card.open
                    Accessible.name: entry.title || entry.tool
                    contentItem: RowLayout {
                        spacing: 8
                        Icon { name: entry.icon || "sparkle"; size: 14; color: view.c.muted }
                        Text {
                            Layout.fillWidth: true
                            // one line in a 26 px row: a command of several lines (Vibe starts with `export PATH=…`
                            // and `cd …`) overflowed onto the text below (04/11); the whole command on hover
                            text: entry.tool === "execute" && entry.command ? view.oneLine(entry.command)
                                  : view.oneLine(entry.short ? (entry.title && entry.tool !== "edit" && entry.tool !== "read" ? entry.title : entry.short) : (entry.title || entry.tool))
                            textFormat: Text.PlainText
                            maximumLineCount: 1
                            elide: Text.ElideMiddle
                            ToolTip.visible: entry.tool === "execute" && String(entry.command || "").indexOf("\n") >= 0 && cardHover.hovered
                            ToolTip.delay: 400
                            ToolTip.text: String(entry.command || "")
                            HoverHandler { id: cardHover }
                            font.family: entry.tool === "execute" || entry.short ? "JetBrains Mono" : "Schibsted Grotesk"
                            font.pixelSize: 13
                            color: view.c.text
                        }
                        OButton {                // the file in the editor of the computer
                            visible: !!entry.path && (entry.tool === "edit" || entry.tool === "read")
                            kind: "quiet"; iconName: "openExternal"; iconSize: 13; height_: 22
                            tip: app.t.code_open_file
                            onClicked: code.openPath(entry.path)
                        }
                        Text {
                            visible: (entry.added || 0) + (entry.removed || 0) > 0
                            text: app.t.code_changes.replace("%1", entry.added || 0).replace("%2", entry.removed || 0)
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: view.c.muted
                        }
                        Text {
                            visible: !!entry.answer
                            text: entry.answer === "plan" ? app.t.code_refused_plan : entry.answer === "blocked" ? app.t.code_blocked : entry.answer === "rejected" ? app.t.code_rejected : app.t.code_allowed
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: entry.answer === "allowed" ? view.c.okInk : entry.answer === "plan" ? view.c.saffronInk : view.c.danger
                        }
                        BusyIndicator { visible: entry.status === "in_progress" || entry.status === "pending" && !card.asking && code.busy
                                        running: visible; implicitWidth: 16; implicitHeight: 16 }
                        Icon {
                            visible: entry.status === "completed" || entry.status === "failed"
                            name: entry.status === "failed" ? "close" : "check"
                            size: 13
                            color: entry.status === "failed" ? view.c.danger : view.c.okInk
                        }
                        Icon { visible: card.lines.length > 0 || (entry.output || "") !== ""; name: card.open ? "collapse" : "expand"; size: 11; color: view.c.muted }
                    }
                }
                RowLayout {
                    visible: !!entry.retryOutside || (entry.tool === "execute" && card.open)
                    Layout.fillWidth: true
                    OButton {
                        visible: !!entry.retryOutside
                        enabled: !code.busy && !code.waiting
                        text: app.t.code_retry_outside
                        iconName: "shieldCheck"; kind: "quiet"
                        onClicked: code.retryOutside(card.rowIndex)
                    }
                    Item { Layout.fillWidth: true }
                    OButton {
                        visible: entry.tool === "execute" && card.open
                        text: app.t.code_copy_command
                        iconName: "copy"; kind: "quiet"
                        onClicked: code.copyCommand(card.rowIndex)
                    }
                }
                Text {
                    visible: !!entry.manual
                    Layout.fillWidth: true
                    text: app.t.code_admin_terminal
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: view.c.muted
                }
                // a diff: + and − lines, monospace
                Rectangle {
                    Layout.fillWidth: true
                    visible: card.open && card.lines.length > 0
                    Layout.preferredHeight: visible ? Math.min(diffCol.implicitHeight, 360) : 0
                    radius: 6
                    color: view.c.bg
                    clip: true
                    Flickable {
                        anchors.fill: parent
                        contentHeight: diffCol.implicitHeight
                        contentWidth: width
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        Column {
                            id: diffCol
                            width: parent.width
                            Repeater {
                                model: card.open ? card.lines : []
                                Rectangle {
                                    required property var modelData
                                    width: diffCol.width
                                    height: lineText.implicitHeight + 2
                                    color: modelData.t === "+" ? view.c.okTint : modelData.t === "-" ? view.c.dangerTint : "transparent"
                                    Text {
                                        id: lineText
                                        x: 8; width: parent.width - 16
                                        y: 1
                                        text: (modelData.t === "@" ? "" : modelData.t + " ") + modelData.s
                                        textFormat: Text.PlainText
                                        wrapMode: Text.WrapAnywhere
                                        font.family: "JetBrains Mono"; font.pixelSize: 12
                                        color: modelData.t === "@" ? view.c.muted : view.c.text
                                    }
                                }
                            }
                        }
                    }
                }
                // what a command printed (or what a tool returned)
                Rectangle {
                    Layout.fillWidth: true
                    visible: card.open && card.lines.length === 0 && (entry.output || "") !== ""
                    Layout.preferredHeight: visible ? Math.min(outText.implicitHeight + 16, 260) : 0
                    radius: 6
                    color: view.c.bg
                    clip: true
                    Flickable {
                        id: outFlick
                        anchors.fill: parent
                        anchors.margins: 8
                        contentHeight: outText.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        onContentHeightChanged: if (entry.status === "in_progress") contentY = Math.max(0, contentHeight - height)
                        Text {
                            id: outText
                            width: outFlick.width
                            text: card.open ? String(entry.output || "") : ""
                            textFormat: Text.PlainText
                            wrapMode: Text.WrapAnywhere
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: view.c.text
                        }
                    }
                }
                // the agent asks: the choices are above the message box (PermissionDock), as in the Discussion mode
            }
    }

    OMenu {
        id: workMenu
        implicitWidth: 320
        heading: app.t.mode_menu_title
        subheading: app.t.mode_cycle_tip
        Repeater {
            // the modes of a folder: Agent (it edits and runs), Plan (read only, then a plan), Ask (read only, it answers)
            model: [["agent", "ornis", app.t.mode_agent, app.t.code_code_sub],
                    ["plan", "list", app.t.mode_plan + " · " + app.t.plan_readonly, app.t.code_plan_sub],
                    ["ask", "chat", app.t.mode_ask + " · " + app.t.plan_readonly, app.t.code_ask_sub]]
            OMenuItem {
                required property var modelData
                text: modelData[2]
                iconName: code.agentMode === modelData[0] ? "check" : modelData[1]
                enabled: !code.busy
                onTriggered: { code.setAgentMode(modelData[0]); input.forceActiveFocus() }
                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: modelData[3]
            }
        }
    }
    OMenu {
        id: modeMenu
        implicitWidth: 340
        heading: app.t.code_mode_title
        subheading: code.sandbox ? app.t.code_sandbox : app.t.code_no_sandbox
        Repeater {
            model: ["ask", "edits", "auto"]
            OMenuItem {
                required property string modelData
                text: view.modeInfo[modelData].label
                iconName: code.mode === modelData ? "check" : view.modeInfo[modelData].icon
                enabled: !code.busy
                onTriggered: code.setMode(modelData)
                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: view.modeInfo[modelData].sub
            }
        }
    }
}
