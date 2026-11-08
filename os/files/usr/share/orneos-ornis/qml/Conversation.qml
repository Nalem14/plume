// One conversation: its title (remember it, open it in the cloud, the conversation's menu), the messages, the reply
// being written (what Ornis is looking at, its text so far), the actions waiting for a yes, then the message box.
// Empty, it greets and suggests what Ornis can do. Scrolled up, a button brings back the end. What is typed in the
// message box stays with its conversation while another one is open.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: view
    signal menuRequested(Item item)
    // Plume's side panel (Panel.qml): a narrow column beside a module, its own header (new, open in Ornis, close)
    property bool panel: false
    property var panelIdeas: []          // the panel's suggestions while empty (about what is open beside)
    signal closeRequested()
    signal expandRequested()
    readonly property var c: theme.c
    readonly property bool empty: chat.messages.length === 0 && !chat.busy && !chat.loading
    readonly property int column: panel ? Math.max(260, chatColumn.width - 24)
                                        : Math.min(app.readingWidth, Math.max(320, chatColumn.width - 64))
    property var drafts: ({})            // conversation id → what was typed ("" : a new conversation)
    property string shownFor: ""
    property int seen: 0                 // messages shown: only new ones bring the view to the end
    property bool stick: true            // follow the reply being written, unless scrolled up meanwhile
    property var why: ({})               // the « why » of a 👎 being written (Message.qml): outlives the rows of the list
    color: c.bg

    function focusInput() { composer.focusInput() }
    function setComposerText(value) { composer.setText(value || ""); composer.focusInput() }
    function pickWorkspace() { workspaceDialog.open() }
    // positionViewAtEnd stops short while the last rows learn their height: then the very end, once more after
    function toEnd() { Qt.callLater(() => { list.positionViewAtEnd(); view.toLastLine(); settle.restart() }) }
    function toLastLine() { list.contentY = Math.max(list.originY - list.topMargin, list.originY + list.contentHeight + list.bottomMargin - list.height) }
    Timer { id: settle; interval: 120; onTriggered: if (view.stick) view.toLastLine() }
    function edit(message) { composer.startEdit(message) }
    function attachFromDrive() { composer.attachFromDrive() }
    function openPlus() { composer.openPlus() }
    function openModes() { composer.openModes() }
    function pickMode(mode) { composer.pickMode(mode); composer.focusInput() }
    function openEnvironment() { composer.openEnvironment() }
    function showContext() { composer.showContext() }
    function openProjects() { composer.openProjects() }
    function clearComposer() { composer.setText(""); composer.focusInput() }
    function showImage(images, at) { imageViewer.show(images, at) }
    signal editActionsRequested()
    function editActions() { editActionsRequested() }

    Connections {
        target: chat
        function onChanged() {
            if (chat.current !== view.shownFor) {
                // a new conversation getting its id while Ornis answers keeps the box; any other change swaps drafts
                if (!(view.shownFor === "" && chat.busy)) {
                    const d = view.drafts
                    d[view.shownFor] = composer.text()
                    composer.cancelEdit()
                    composer.setText(d[chat.current] || "")
                    view.drafts = d
                }
                view.shownFor = chat.current
                view.stick = true
                view.seen = -1
            }
            if (chat.messages.length !== view.seen) {
                view.seen = chat.messages.length
                view.stick = true
                view.toEnd()
            }
        }
        function onStreamChanged() { if (view.stick) view.toEnd() }
        function onReplied() {
            if (view.stick) view.toEnd()
            composer.focusInput()
            // the answer made something to look at (a page, a drawing, a diagram): shown beside it at once
            const last = chat.messages.length ? chat.messages[chat.messages.length - 1] : null
            if (!last || last.role === "human") return
            const art = app.messageBlocks(last.content || "").filter(b => b.artifact)
            if (art.length && !view.panel) previewPane.show(art[art.length - 1].title, art[art.length - 1].lang, art[art.length - 1].code)
        }
    }
    Connections {
        target: chat
        function onLaterReturned(text) {
            const now = composer.text()
            composer.setText(now ? text + "\n\n" + now : text)
            composer.focusInput()
        }
    }
    Connections {
        target: app
        function onPreviewRequested(title, lang, code) { if (view.panel) view.expandRequested(); else previewPane.show(title, lang, code) }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

    ColumnLayout {
        id: chatColumn
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 0

        // ---- header ---------------------------------------------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: view.panel ? 46 : 52
            color: view.c.chrome
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: view.panel ? 14 : win.sidebarShown ? 20 : 10; anchors.rightMargin: view.panel ? 8 : 12
                spacing: 6
                Icon { visible: view.panel; name: "ornis"; size: 18; color: view.c.accent }
                OButton {
                    visible: !win.sidebarShown && !view.panel
                    kind: "quiet"; iconName: "sidebar"; tip: app.t.show_sidebar + "  (Ctrl+B)"
                    onClicked: win.toggleSidebar()
                }
                OButton {
                    visible: !win.sidebarShown && !view.panel
                    kind: "quiet"; iconName: "compose"; tip: app.t.new_discussion + "  (Ctrl+N)"
                    onClicked: win.newChat()
                }
                AbstractButton {             // the project it belongs to, as a breadcrumb: back to its page
                    visible: chat.project !== "" && !view.panel
                    Layout.maximumWidth: 200
                    implicitWidth: crumbRow.implicitWidth + 12; implicitHeight: 28
                    hoverEnabled: true
                    onClicked: win.openProject(chat.project)
                    Accessible.name: app.t.project_open.replace("%1", chat.projectName)
                    background: Rectangle { radius: 7; color: parent.hovered ? view.c.hover : "transparent" }
                    contentItem: RowLayout {
                        id: crumbRow
                        spacing: 6
                        Icon { Layout.leftMargin: 6; name: "folder"; size: 14; color: view.c.muted }
                        Text {
                            Layout.fillWidth: true
                            text: chat.projectName
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                            color: view.c.muted
                        }
                        Icon { name: "chevronRight"; size: 12; color: view.c.muted }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: view.panel && chat.current === "" ? app.t.app_name : chat.title
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: view.panel ? 14 : 16; font.weight: Font.DemiBold
                    color: view.c.text
                }
                AbstractButton {        // « Éphémère »: chosen on a new conversation, then its mark (not listed, deleted once left)
                    id: ephemeralBtn
                    visible: (chat.current === "" && chat.messages.length === 0 && chat.uiMode !== "goal" && chat.uiMode !== "research")
                             || chat.ephemeral
                    implicitWidth: ephRow.implicitWidth + 16; implicitHeight: 28
                    hoverEnabled: true
                    onClicked: if (chat.current === "") { chat.setEphemeral(!chat.ephemeral); composer.focusInput() }
                    Accessible.role: Accessible.CheckBox
                    Accessible.checked: chat.ephemeral
                    Accessible.name: chat.ephemeral ? app.t.ephemeral_on : app.t.ephemeral_tip
                    ToolTip.text: Accessible.name; ToolTip.delay: 500; ToolTip.visible: hovered
                    background: Rectangle {
                        radius: 14
                        color: chat.ephemeral ? view.c.tint : ephemeralBtn.hovered ? view.c.hover : "transparent"
                        border.width: chat.ephemeral ? 1 : 0; border.color: view.c.accentLine
                    }
                    contentItem: Item {
                        Row {
                            id: ephRow
                            anchors.centerIn: parent
                            spacing: 6
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: "eyeOff"; size: 15
                                   color: chat.ephemeral ? view.c.tintText : view.c.muted }
                            Text {
                                visible: chat.ephemeral || !view.panel
                                anchors.verticalCenter: parent.verticalCenter
                                text: app.t.ephemeral
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                                color: chat.ephemeral ? view.c.tintText : view.c.muted
                            }
                        }
                    }
                }
                OButton {               // remembered: said by a quiet mark (the switch is in the conversation's menu)
                    visible: chat.current !== "" && chat.remembered
                    kind: "quiet"; iconName: "history"; tip: app.t.remembered_tip
                    onClicked: chat.setRemembered(false)
                    background: Rectangle { radius: 6; color: parent.hovered ? view.c.hover : view.c.tint }
                }
                OButton {
                    id: headerMore
                    visible: chat.current !== "" && !view.panel
                    kind: "quiet"; iconName: "more"; tip: app.t.more
                    onClicked: view.menuRequested(headerMore)
                }
                OButton {
                    visible: view.panel
                    kind: "quiet"; iconName: "compose"; tip: app.t.new_discussion
                    onClicked: { chat.newChat(); composer.focusInput() }
                }
                OButton {
                    visible: view.panel
                    kind: "quiet"; iconName: "expand"; tip: app.t.panel_expand
                    onClicked: view.expandRequested()
                }
                OButton {
                    visible: view.panel
                    kind: "quiet"; iconName: "close"; tip: app.t.panel_close + "  (Ctrl+J)"
                    onClicked: view.closeRequested()
                }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: view.c.line }
        }

        // ---- a scheduled task's conversation: the task first (its instruction, how often, the last run) ----------
        TaskCard {
            visible: chat.currentTask !== ""
            task: chat.scheduled.find(t => t.id === chat.currentTask) || ({})
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.maximumHeight: Math.min(180, view.height * 0.22)
            Layout.topMargin: 10
            onDeleteRequested: id => win.deleteTask(id)
        }


        // ---- messages --------------------------------------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            // a conversation opened for the first time: the shape of its messages until they arrive (after 150 ms,
            // so that a quick answer does not blink), never the welcome of a new one
            Item {
                id: loadingShape
                anchors.fill: parent
                property bool due: false
                visible: due && chat.loading && chat.messages.length === 0
                Timer { interval: 150; running: chat.loading; onTriggered: loadingShape.due = true }
                Connections { target: chat; function onChanged() { if (!chat.loading) loadingShape.due = false } }
                Accessible.role: Accessible.Animation
                Accessible.name: app.t.loading_conversation
                opacity: visible ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                SequentialAnimation on pulse {
                    running: loadingShape.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.55; to: 1; duration: 700; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1; to: 0.55; duration: 700; easing.type: Easing.InOutSine }
                }
                property real pulse: 0.55
                Column {
                    x: (parent.width - view.column) / 2
                    y: 24
                    width: view.column
                    spacing: 26
                    opacity: loadingShape.pulse
                    Repeater {
                        model: [[0.46, [0.92, 0.78, 0.86, 0.4]], [0.32, [0.88, 0.95, 0.6]], [0.52, [0.9, 0.7, 0.82, 0.74, 0.35]]]
                        Column {
                            required property var modelData
                            width: parent.width
                            spacing: 18
                            Rectangle {                   // the question, on the right
                                anchors.right: parent.right
                                width: parent.width * modelData[0]; height: 40; radius: 18
                                color: view.c.tint
                            }
                            Row {                         // the answer: Ornis's mark, then its lines
                                width: parent.width
                                spacing: 12
                                Rectangle { width: 26; height: 26; radius: 13; color: view.c.line }
                                Column {
                                    width: parent.width - 38
                                    spacing: 10
                                    topPadding: 6
                                    Repeater {
                                        model: modelData[1]
                                        Rectangle { required property real modelData; width: parent.width * modelData; height: 11; radius: 5.5; color: view.c.line }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            ListView {
                id: list
                anchors.fill: parent
                visible: !view.empty
                clip: true
                model: chat.messages
                spacing: 18
                topMargin: 24; bottomMargin: 24
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; onPressedChanged: if (pressed) view.stick = false }
                onMovementStarted: view.stick = false
                onAtYEndChanged: if (atYEnd) view.stick = true
                // the mouse wheel starts no « movement »: scrolling up to read, the reply being written stops
                // pulling the view down (back at the bottom, it follows again); the wheel still scrolls the list
                WheelHandler { target: null; blocking: false; onWheel: ev => { if (ev.angleDelta.y > 0) view.stick = false } }
                // a vertical ListView places its delegates at x 0: each message is centred inside a full-width row
                delegate: Item {
                    required property var modelData
                    required property int index
                    width: list.width
                    height: item.implicitHeight
                    Message {
                        id: item
                        x: (list.width - view.column) / 2
                        width: view.column
                        message: modelData
                        last: index === chat.messages.length - 1
                        lastMine: modelData.role === "human" && !chat.messages.slice(index + 1).some(m => m.role === "human")
                        onEditRequested: view.edit(modelData)
                        onImageRequested: (images, at) => imageViewer.show(images, at)
                        why: view.why
                        onWhyEdited: state => view.why = state
                    }
                }
                footer: Item {
                    width: list.width
                    height: footerColumn.implicitHeight
                    Column {
                    id: footerColumn
                    x: (list.width - view.column) / 2
                    width: view.column
                    topPadding: actionCard.visible ? 8 : 18
                    spacing: 18
                    // the reply being written
                    Message {
                        visible: chat.busy
                        width: parent.width
                        message: ({ role: "assistant", content: chat.stream, tools: chat.workingTools, id: "" })
                        streaming: true
                    }
                    ActionCard {                // part of Ornis's answer: under its text, past its mark (Message: 30 + 14)
                        id: actionCard
                        Connections { target: view; function onEditActionsRequested() { actionCard.editing = true } }
                        // Ornis's questions (ask_user) are not actions: they come as a form above the box (QuestionsDock)
                        visible: chat.pending.length > 0 && !chat.busy && !chat.pending.some(a => a.ask)
                        x: 44
                        width: parent.width - 44
                        actions: chat.pending
                        onAnswered: yes => chat.confirm(yes)
                        onAnsweredEdited: edits => chat.confirmEdited(edits)
                    }
                    Rectangle {
                        visible: chat.error !== "" && !chat.busy
                        width: parent.width
                        height: problemRow.implicitHeight + 24
                        radius: 8
                        color: chat.error === "limit" ? view.c.saffronTint : view.c.dangerTint
                        RowLayout {
                            id: problemRow
                            anchors.fill: parent; anchors.margins: 12
                            spacing: 10
                            Icon { name: chat.error === "offline" ? "offline" : "warning"; size: 18
                                   color: chat.error === "limit" ? view.c.saffronInk : view.c.danger }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                text: chat.error === "offline" ? app.t.offline : chat.error === "limit" ? app.t.limit_reached : app.t.failed
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                color: view.c.text
                            }
                            OButton {
                                visible: chat.error !== "limit"
                                text: app.t.retry; iconName: "refresh"
                                onClicked: chat.retry()
                            }
                            OButton {
                                visible: chat.error === "limit"
                                text: app.t.quota_more
                                onClicked: app.openPlans()
                            }
                        }
                    }
                }
                }
            }

            Welcome {
                anchors.fill: parent
                visible: view.empty
                compact: view.panel
                custom: view.panelIdeas
                onSuggestion: text => chat.send(text)
                onWorkSuggestion: (text, kind) => {           // free plans see the goal too; sending shows the plans
                    if (kind === "plan") chat.setUiMode("plan"); else chat.setWorkKind(kind)
                    composer.setText(text)
                    composer.focusInput()
                }
            }

            // scrolled up: back to the end
            AbstractButton {
                id: toBottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 12
                implicitWidth: 36; implicitHeight: 36
                visible: opacity > 0
                opacity: !view.empty && !list.atYEnd && list.contentHeight > list.height ? 1 : 0
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

        // editing my question: say so, and how to leave
        Rectangle {
            visible: composer.editingId !== ""
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 8
            implicitHeight: editRow.implicitHeight + 12
            radius: 8
            color: view.c.saffronTint
            RowLayout {
                id: editRow
                anchors.fill: parent; anchors.margins: 6; anchors.leftMargin: 12
                spacing: 8
                Icon { name: "edit"; size: 16; color: view.c.saffronInk }
                Text {
                    Layout.fillWidth: true
                    text: app.t.editing
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: view.c.saffronInk
                }
                OButton { kind: "quiet"; text: app.t.cancel; height_: 28; onClicked: composer.cancelEdit() }
            }
        }

        // A plan is ready (plan mode, its answer there): run it (every tool back), or keep refining
        Rectangle {
            id: planBar
            visible: chat.planReady && composer.editingId === ""
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 8
            implicitHeight: planBarRow.implicitHeight + 16
            radius: 12
            color: view.c.saffronTint
            border.width: 1; border.color: view.c.saffron
            RowLayout {
                id: planBarRow
                anchors.fill: parent; anchors.margins: 8; anchors.leftMargin: 14
                spacing: 10
                Icon { name: "list"; size: 17; color: view.c.saffronInk }
                Text {
                    Layout.fillWidth: true
                    text: app.t.plan_ready
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                    color: view.c.saffronInk
                }
                OButton { kind: "quiet"; text: app.t.plan_keep; height_: 30; onClicked: composer.focusInput() }
                OButton { kind: "primary"; text: app.t.plan_run; iconName: "play"; height_: 30; onClicked: chat.runPlan() }
            }
        }

        // Plan mode, before a plan: what it means, in sight above the box (the box itself is outlined in saffron)
        Rectangle {
            visible: composer.planMode && !chat.planReady && !view.empty
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 8
            implicitHeight: planHint.implicitHeight + 14
            radius: 10
            color: view.c.saffronTint
            RowLayout {
                id: planHint
                anchors.fill: parent; anchors.margins: 7; anchors.leftMargin: 12
                spacing: 8
                Icon { name: "eye"; size: 15; color: view.c.saffronInk }
                Text {
                    Layout.fillWidth: true
                    text: app.t.plan_banner
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: view.c.saffronInk
                }
                OButton { kind: "quiet"; text: app.t.mode_agent; iconName: "ornis"; height_: 26; onClicked: chat.setUiMode("agent") }
            }
        }

        // the last change Ornis made to a file of this computer: undone in one click
        Item {
            visible: undoChip.visible
            Layout.fillWidth: true
            Layout.bottomMargin: 6
            implicitHeight: undoChip.implicitHeight
            AbstractButton {
                id: undoChip
                visible: (app.undoable.count || 0) > 0 && app.prefs.local_tools !== false
                x: (parent.width - view.column) / 2 + view.column - width
                implicitWidth: undoRow.implicitWidth + 20
                implicitHeight: 26
                hoverEnabled: true
                onClicked: app.undoLastLocalChange()
                Accessible.name: undoLabel.text
                ToolTip.visible: hovered
                ToolTip.delay: 400
                ToolTip.text: app.undoable.path || app.t.slash_undo_sub
                background: Rectangle {
                    radius: 13
                    color: undoChip.hovered ? view.c.hover : view.c.chrome
                    border.width: 1; border.color: view.c.line
                }
                contentItem: Item {
                    Row {
                        id: undoRow
                        anchors.centerIn: parent
                        spacing: 5
                        Icon { name: "restore"; size: 13; color: view.c.famCommunicate; anchors.verticalCenter: parent.verticalCenter }
                        Text {
                            id: undoLabel
                            anchors.verticalCenter: parent.verticalCenter
                            text: app.t.undo_last.replace("%1", app.undoable.name || "")
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                            color: view.c.text
                        }
                    }
                }
            }
        }
        // Ornis acts on this computer without asking: always in sight while it lasts
        AbstractButton {
            id: autonomous
            visible: app.computerMode === "full" && app.prefs.local_tools
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 4
            implicitWidth: chipRow.implicitWidth + 24
            implicitHeight: 28
            hoverEnabled: true
            onClicked: app.openComputer()
            Accessible.name: chipText.text
            background: Rectangle {
                radius: height / 2
                color: autonomous.hovered ? view.c.saffron : view.c.saffronTint
                border.width: 1; border.color: view.c.saffron
            }
            contentItem: Item {
                Row {
                    id: chipRow
                    spacing: 6
                    anchors.centerIn: parent
                    Icon { name: "devices"; size: 14; color: view.c.saffronInk; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        id: chipText
                        anchors.verticalCenter: parent.verticalCenter
                        text: app.computerUntil ? app.t.computer_chip.replace("%1", app.computerUntil) : app.t.computer_chip_forever
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                        color: view.c.saffronInk
                    }
                }
            }
        }
        WorkCard {                           // a Work job's conversation: the job, its steps live
            visible: !!chat.currentJob.session
            job: chat.currentJob
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 8
            Layout.maximumHeight: Math.min(200, view.height * 0.24)
            onResumeRequested: win.resumeWork()
        }

        // written while Ornis answers: sent one by one after the reply; each can go now, be changed or dropped
        QueueDock {
            items: chat.later
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: visible ? 6 : 0
            onSendNow: i => chat.sendLaterNow(i)
            onEditRequested: i => chat.editLater(i)
            onDropRequested: i => chat.dropLater(i)
        }

        // Ornis is working: one line above the box, the same as in Code
        WorkingLine {
            busy: chat.busy && !permDock.visible && !questionsDock.visible
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.preferredHeight: implicitHeight
            Layout.bottomMargin: busy ? 6 : 0
        }
        // Ornis asks to act on this computer: the request above the box, as in the Code mode (not a window)
        PermissionDock {
            id: permDock
            readonly property var r: chat.consent
            visible: !!r.title
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 8
            iconName: r.hasCommand ? "terminal" : "devices"
            title: r.title || ""
            subtitle: r.level || ""
            place: r.elsewhere || ""
            summary: r.summary || ""
            reason: r.reason || ""
            hasCommand: !!r.hasCommand
            command: r.command || ""
            cwd: r.cwd || ""
            preview: r.preview || ""
            warnings: r.warnings || []
            careful: !!r.careful
            until: r.until || 0
            note: r.noAlways ? app.t.perm_no_always : (r.mode || "")
            settingsVisible: true
            options: [{ id: "allow", kind: "allow", label: r.verb || app.t.perm_allow }]
                     .concat(r.always ? [{ id: "always", kind: "always", label: r.always }] : [])
                     .concat([{ id: "deny", kind: "deny", label: app.t.perm_deny }, { id: "tell", kind: "tell", label: app.t.perm_deny_tell }])
            onChosen: (id, command) => {
                chat.answerConsent(id === "tell" ? "deny" : id, command)
                composer.focusInput()
            }
            onSettingsRequested: app.openComputer()
        }
        // Ornis asks the user to choose before going on (its tool ask_user): the questions above the box
        QuestionsDock {
            id: questionsDock
            readonly property var ask: chat.pending.find(a => a.ask) || null
            visible: !!ask && !chat.busy && composer.editingId === ""
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 8
            questions: ask ? ask.questions : []
            onAnswered: answers => { chat.answerQuestions(answers); composer.focusInput() }
            onSkipped: { chat.confirm(false); composer.focusInput() }
        }

        Composer {
            id: composer
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: view.panel ? 10 : 18
            onWorkRequested: text => win.askWork(text)
            onWorkspacePickRequested: workspaceDialog.open()
            onProjectCreateRequested: win.createProject(chat.current)
            onCommandsRequested: win.openCommands()
            onEditLastRequested: {
                const mine = chat.messages.filter(m => m.role === "human" && !String(m.id).startsWith("local-"))
                if (mine.length) startEdit(mine[mine.length - 1])
            }
        }
    }

    PreviewPane {
        id: previewPane
        enabled: !view.panel
        onChangeRequested: text => chat.send(text)
        Layout.fillHeight: true
        Layout.preferredWidth: Math.max(340, Math.min(540, Math.round(view.width * 0.44)))
    }
    }

    FolderDialog {
        id: workspaceDialog
        title: app.t.workspace_pick
        onAccepted: { app.setWorkspace(selectedFolder); composer.focusInput() }
    }

    ImageViewer { id: imageViewer }

    // Files dropped anywhere on the conversation become attachments; a mail, a note or a task (Plume, Notes,
    // Tâches) goes into the text as a link Ornis can open; a web address too
    DropArea {
        id: drop
        anchors.fill: parent
        keys: ["application/x-orneos-link", "text/uri-list"]
        property bool links                  // a mail, a note or a task, not files
        onEntered: event => links = event.formats.indexOf("application/x-orneos-link") >= 0
        onDropped: event => {
            if (event.formats.indexOf("application/x-orneos-link") >= 0) {
                composer.insert(app.dropped(event.getDataAsString("application/x-orneos-link")))
            } else if (event.hasUrls) {
                const local = event.urls.filter(u => String(u).startsWith("file:"))
                if (local.length) chat.addFiles(local)
                composer.insert(event.urls.filter(u => /^https?:/.test(String(u))).join(" "))
            }
            event.acceptProposedAction()
            composer.focusInput()
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: 12
        radius: 18
        visible: drop.containsDrag
        color: view.c.saffronTint
        opacity: 0.94
        border.width: 2; border.color: view.c.saffron
        Column {
            anchors.centerIn: parent
            spacing: 10
            Icon { anchors.horizontalCenter: parent.horizontalCenter; name: drop.links ? "link" : "clip"; size: 30; color: view.c.saffronInk }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: drop.links ? app.t.drop_here : app.t.drop_files
                font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                color: view.c.saffronInk
            }
        }
    }
}
