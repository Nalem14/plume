// The message box: Enter sends, Shift+Enter goes to the line (or Ctrl+Enter sends, per the settings); while Ornis
// writes, Stop. Up in an empty box edits my last question. Under the text, one toolbar, as in other harnesses:
// « + », @, /, the mode (Agent, Plan, Objectif, Recherche; Shift+Tab goes round them), the conversation's project and
// where Ornis acts (this computer, its permissions), then the context gauge, the microphone and Send.
// Files for Ornis to read: the "+" (this computer or the Drive), Ctrl+V of an image or of copied files, or a drop
// anywhere on the conversation (Conversation.qml). Each shows above the text, a vignette or a pill, and leaves with
// its cross; they upload at once, so sending never waits for them.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: box
    readonly property var c: theme.c
    // while Ornis answers, a written message waits for the reply (chat.later), as in Claude Code: no goal, no edit
    readonly property bool queueing: chat.busy && input.text.trim() !== "" && !chat.workMode && !editingId
    readonly property bool canSend: (input.text.trim() !== "" || chat.attachments.length > 0) && !chat.busy || queueing
    readonly property bool enterSends: app.prefs.enter_sends !== false
    property string editingId: ""        // my question being changed (Ornis answers again from there)
    property int mentionStart: -1        // index of the active '@' in input.text, or -1
    property int mentionIndex: 0
    property int slashStart: -1          // index of the active '/' at the start of input.text, or -1
    property int slashIndex: 0
    signal commandsRequested()
    signal editLastRequested()
    signal workRequested(string text)    // Work mode: the view shows what the job takes, then starts it
    signal workspacePickRequested()
    signal projectCreateRequested()       // « Nouveau projet… » of the project chip
    readonly property bool planMode: chat.uiMode === "plan"
    readonly property bool jobLocked: !!chat.currentJob.session          // a goal's conversation stays one
    readonly property bool roomy: width >= 640
    implicitHeight: Math.min(240, Math.max(44, input.implicitHeight)) + toolbar.implicitHeight + 6 + (files.visible ? files.implicitHeight + 10 : 0)
    radius: 16
    color: c.card
    border.width: input.activeFocus || planMode ? 2 : 1
    border.color: planMode ? c.saffron : input.activeFocus ? c.action : c.line
    Behavior on border.color { ColorAnimation { duration: 140 } }

    // Agent → Plan → Objectif → Recherche (paid modes skipped on a free plan) → Agent
    function cycleMode() {
        if (jobLocked) return
        const order = ["agent", "plan"].concat(chat.workEstimate.allowed === false ? [] : ["goal", "research"])
        const at = order.indexOf(chat.uiMode)
        chat.setUiMode(order[(at + 1) % order.length])
    }
    function pickMode(mode) {
        if (mode === "code") { win.startCode(); return }     // its own view: a folder of the computer, kept here
        if ((mode === "goal" || mode === "research") && chat.workEstimate.allowed === false) {
            win.showWorkPlans(mode === "goal" ? "work" : "research")
            return
        }
        chat.setUiMode(mode)
        input.forceActiveFocus()
    }
    function openModes() {
        const at = modeBtn.mapToItem(box, 0, 0)
        modeMenu.x = at.x
        modeMenu.y = at.y - modeMenu.implicitHeight - 6
        modeMenu.open()
    }
    function openEnvironment() {         // where Ornis acts, and with which permissions: a menu, the window behind it
        const at = envBtn.mapToItem(box, 0, 0)
        envMenu.x = Math.max(0, at.x + envBtn.width - envMenu.implicitWidth)
        envMenu.y = at.y - envMenu.implicitHeight - 6
        envMenu.open()
    }
    function showContext() { contextGauge.openDetails() }
    function openProjects() {
        const at = projectBtn.mapToItem(box, 0, 0)
        projectMenu.x = at.x
        projectMenu.y = at.y - projectMenu.implicitHeight - 6
        projectMenu.open()
    }

    function focusInput() { input.forceActiveFocus() }
    function send() {
        if (!canSend) return
        if (queueing) { chat.send(input.text); input.text = ""; return }
        if (chat.workMode && !editingId) {
            if (input.text.trim() === "") return
            box.workRequested(input.text)    // the box is emptied once the job is started
            return
        }
        if (editingId) chat.edit(editingId, input.text)
        else chat.send(input.text)
        editingId = ""
        input.text = ""
    }
    function text() { return input.text }
    function setText(value) { input.text = value || ""; input.cursorPosition = input.length }
    function startEdit(message) {
        editingId = message.id
        setText(message.content)
        input.forceActiveFocus()
    }
    function cancelEdit() {
        if (!editingId) return
        editingId = ""
        input.text = ""
    }
    function insert(text) {
        if (!text) return
        const sep = input.text && !/\s$/.test(input.text) ? " " : ""
        input.insert(input.cursorPosition, sep + text + " ")
        input.forceActiveFocus()
    }
    function attachFromComputer() { picker.open() }
    function attachFromDrive() { drive.openAt("/") }

    function updateMentions() {
        const before = input.text.slice(0, input.cursorPosition)
        const sm = before.match(/^\s*\/([^\s/]*)$/)
        if (sm) {
            box.slashStart = before.indexOf("/")
            box.slashIndex = 0
            box.mentionStart = -1
            if (mentionPopup.opened) mentionPopup.close()
            chat.searchSlashes(sm[1] || "")
            if (!slashPopup.opened) slashPopup.open()
            return
        }
        box.slashStart = -1
        if (slashPopup.opened) slashPopup.close()
        const m = before.match(/(?:^|\s)@([^\s@]*)$/)
        if (!m) {
            box.mentionStart = -1
            if (mentionPopup.opened) mentionPopup.close()
            return
        }
        box.mentionStart = before.lastIndexOf("@")
        box.mentionIndex = 0
        chat.searchMentions(m[1] || "")
        if (!mentionPopup.opened) mentionPopup.open()
    }

    function openSlashes() {
        input.forceActiveFocus()
        if (!/^\s*\/[^\s/]*$/.test(input.text.slice(0, input.cursorPosition))) {
            input.text = "/" + input.text.replace(/^\s+/, "")
            input.cursorPosition = 1
        }
        updateMentions()
    }

    function applySlash(item) {
        if (!item) return
        if (box.slashStart >= 0 && input.cursorPosition >= box.slashStart) {
            input.remove(box.slashStart, input.cursorPosition)
        }
        box.slashStart = -1
        slashPopup.close()
        const k = item.kind || ""
        if (k === "mode_plan" || k === "mode_agent" || k === "mode_goal" || k === "mode_research") {
            box.pickMode(k.slice(5))
        } else if (k === "mode_code") {
            win.startCode()                  // the Code mode: Ornis works in a folder of the computer
        } else if (k === "commands") {
            box.commandsRequested()            // « Mes commandes »: create, change, delete the user's own
        } else if (k === "compact") {
            chat.compact()
        } else if (k === "new") {
            win.newChat()
        } else if (k === "undo") {
            app.undoLastLocalChange()
        } else if (k === "skill" || k === "mcp") {
            chat.addLink({ kind: k, label: item.label.replace(/^\//, ""), value: item.value, icon: k === "mcp" ? "devices" : "sparkle" })
        } else if (item.value) {
            input.insert(input.cursorPosition, item.value)
        }
        input.forceActiveFocus()
    }

    function openMentions() {
        input.forceActiveFocus()
        const before = input.text.slice(0, input.cursorPosition)
        if (!/(?:^|\s)@[^\s@]*$/.test(before)) {
            const sep = before && !/\s$/.test(before) ? " " : ""
            input.insert(input.cursorPosition, sep + "@")
        }
        updateMentions()
    }

    function applyMention(item) {
        if (!item) return
        if (box.mentionStart >= 0 && input.cursorPosition >= box.mentionStart) {
            input.remove(box.mentionStart, input.cursorPosition)
        }
        box.mentionStart = -1
        mentionPopup.close()
        const k = item.kind || ""
        if (k === "action_local_file") {
            box.attachFromComputer()
        } else if (k === "action_workspace") {
            box.workspacePickRequested()
        } else if (k === "action_drive") {
            box.attachFromDrive()
        } else if (k === "action_screenshot") {
            chat.captureScreenshot()
        } else if (k === "cloud_local") {
            chat.addFiles([item.value])
        } else if (k === "cloud_remote") {
            chat.addCloudFiles([{ path: item.value, name: item.label, size: item.size || 0, file_id: item.file_id || "" }])
        } else if (k === "local_file" || k === "local_folder") {
            if (k === "local_file" && app.prefs.local_tools === false && item.attachable) chat.addFiles([item.value])
            else chat.addLink({ kind: k, label: item.label, value: item.value, icon: k === "local_folder" ? "folder" : "note" })
        } else if (item.value) {
            input.insert(input.cursorPosition, item.value)
        }
        input.forceActiveFocus()
    }

    function openPlus() {                // above « + » (an OMenu is a Popup: placed in the composer, then opened)
        const at = plus.mapToItem(box, 0, 0)
        attachMenu.x = at.x
        attachMenu.y = at.y - attachMenu.implicitHeight - 6
        attachMenu.open()
    }
    function enter(event) {
        if (slashPopup.opened && chat.slashes.length > 0) {
            box.applySlash(chat.slashes[Math.min(box.slashIndex, chat.slashes.length - 1)])
            event.accepted = true
            return
        }
        if (mentionPopup.opened && chat.mentions.length > 0) {
            box.applyMention(chat.mentions[Math.min(box.mentionIndex, chat.mentions.length - 1)])
            event.accepted = true
            return
        }
        const ctrl = event.modifiers & Qt.ControlModifier
        const shift = event.modifiers & Qt.ShiftModifier
        if (shift || (!enterSends && !ctrl)) { event.accepted = false; return }
        send()
        event.accepted = true
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Flow {                               // the files of the message, above the text
            id: files
            visible: chat.attachments.length > 0 || chat.links.length > 0 || !!chat.about.label
            Layout.fillWidth: true
            Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.topMargin: 12
            spacing: 8
            Repeater {
                model: chat.attachments
                AttachmentChip {
                    required property var modelData
                    name: modelData.name; kind: modelData.kind; thumb: modelData.thumb; state_: modelData.state
                    removable: true
                    onRemoveRequested: { chat.removeFile(modelData.key); input.forceActiveFocus() }
                }
            }
            LinkBadge {                      // what Plume has open beside (a message, an event): goes with the question
                visible: !!chat.about.label
                label: chat.about.label || ""
                iconName: chat.about.icon || "link"
                tip: app.t.about_tip
                onRemoveRequested: { chat.setAbout({}); input.forceActiveFocus() }
            }
            Repeater {                       // what « @ » linked and « / » chose
                model: chat.links
                LinkBadge {
                    required property var modelData
                    required property int index
                    label: modelData.label
                    iconName: modelData.icon || "note"
                    tip: modelData.value || ""
                    action: modelData.kind === "skill" || modelData.kind === "mcp"
                    onRemoveRequested: { chat.removeLink(index); input.forceActiveFocus() }
                }
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 8; Layout.rightMargin: 8
            TextArea {
                id: input
                placeholderText: chat.pending.length > 0 ? app.t.placeholder_pending : chat.workKind === "research" ? app.t.research_placeholder
                                 : chat.workMode ? app.t.work_placeholder : box.planMode ? app.t.plan_placeholder : chat.ephemeral ? app.t.ephemeral_placeholder : app.t.placeholder
                wrapMode: TextEdit.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: app.textSize
                color: box.c.text
                placeholderTextColor: box.c.muted
                selectionColor: box.c.tint
                selectedTextColor: box.c.text
                background: null
                topPadding: 12; bottomPadding: 4; leftPadding: 6; rightPadding: 6
                onTextChanged: box.updateMentions()
                onCursorPositionChanged: if (mentionPopup.opened || slashPopup.opened) box.updateMentions()
                Keys.onReturnPressed: event => box.enter(event)
                Keys.onEnterPressed: event => box.enter(event)
                Keys.onTabPressed: event => {
                    if (slashPopup.opened && chat.slashes.length > 0) {
                        box.applySlash(chat.slashes[Math.min(box.slashIndex, chat.slashes.length - 1)])
                        event.accepted = true
                    } else if (mentionPopup.opened && chat.mentions.length > 0) {
                        box.applyMention(chat.mentions[Math.min(box.mentionIndex, chat.mentions.length - 1)])
                        event.accepted = true
                    } else {
                        event.accepted = false
                    }
                }
                Keys.onPressed: event => {        // an image or files on the clipboard become attachments
                    if (event.matches(StandardKey.Paste) && chat.paste()) event.accepted = true
                }
                Keys.onBacktabPressed: event => { box.cycleMode(); event.accepted = true }
                Keys.onUpPressed: event => {
                    if (slashPopup.opened && chat.slashes.length > 0) {
                        box.slashIndex = (box.slashIndex - 1 + chat.slashes.length) % chat.slashes.length
                        event.accepted = true
                    } else if (mentionPopup.opened && chat.mentions.length > 0) {
                        box.mentionIndex = (box.mentionIndex - 1 + chat.mentions.length) % chat.mentions.length
                        event.accepted = true
                    } else if (input.text === "" && !chat.busy) {
                        box.editLastRequested()
                        event.accepted = true
                    } else {
                        event.accepted = false
                    }
                }
                Keys.onDownPressed: event => {
                    if (slashPopup.opened && chat.slashes.length > 0) {
                        box.slashIndex = (box.slashIndex + 1) % chat.slashes.length
                        event.accepted = true
                    } else if (mentionPopup.opened && chat.mentions.length > 0) {
                        box.mentionIndex = (box.mentionIndex + 1) % chat.mentions.length
                        event.accepted = true
                    } else {
                        event.accepted = false
                    }
                }
                Keys.onEscapePressed: event => {
                    if (slashPopup.opened) { slashPopup.close(); box.slashStart = -1; event.accepted = true }
                    else if (mentionPopup.opened) { mentionPopup.close(); box.mentionStart = -1; event.accepted = true }
                    else if (chat.voice.recording) { chat.voice.cancel(); event.accepted = true }
                    else if (box.editingId) { box.cancelEdit(); event.accepted = true }
                    else event.accepted = false
                }
            }
        }
        RowLayout {                          // the toolbar under the text
            id: toolbar
            Layout.fillWidth: true
            Layout.leftMargin: 6; Layout.rightMargin: 8; Layout.bottomMargin: 6
            spacing: 4
            OButton {                        // "+": files from this computer or from the Drive
                id: plus
                Layout.alignment: Qt.AlignVCenter
                kind: "quiet"; iconName: "plus"; iconSize: 19; height_: 32
                tip: app.t.attach
                onClicked: box.openPlus()
            }
            ToolbarChip {                    // the mode: Agent, Plan, Objectif, Recherche (on the left, as in Code)
                id: modeBtn
                readonly property string mode: box.jobLocked ? (chat.currentJob.research ? "research" : "goal") : chat.uiMode
                Layout.alignment: Qt.AlignVCenter
                enabled: !box.jobLocked
                onClicked: box.openModes()
                menuOpen: modeMenu.opened
                iconName: mode === "plan" ? "list" : mode === "goal" ? "flag" : mode === "research" ? "search" : "ornis"
                mascot: mode === "agent"
                label: mode === "plan" ? app.t.mode_plan : mode === "goal" ? app.t.mode_goal : mode === "research" ? app.t.research_mode : app.t.mode_agent
                detail: mode === "plan" && box.roomy ? app.t.plan_readonly : ""
                tone: mode === "plan" ? "saffron" : mode === "agent" ? "plain" : "tint"
                chevron: !box.jobLocked
                tip: (mode === "plan" ? app.t.mode_plan_sub : mode === "goal" ? app.t.mode_goal_sub : mode === "research" ? app.t.mode_research_sub : app.t.mode_agent_sub)
                     + "  ·  " + app.t.mode_cycle_tip
            }
            AbstractButton {                 // the reasoning, on or off in one click (as ChatGPT's « Réfléchir »); paid plans
                id: thinkBtn
                readonly property bool locked: !chat.paid
                readonly property bool on: !locked && (app.prefs.reasoning || "think") !== "fast"
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: thinkRow.implicitWidth + 16; implicitHeight: 28
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                onClicked: {
                    if (locked) { win.showWorkPlans("think"); return }
                    app.setPref("reasoning", on ? "fast" : "think")
                    input.forceActiveFocus()
                }
                Accessible.role: Accessible.CheckBox
                Accessible.checkable: !locked
                Accessible.checked: on
                Accessible.name: app.t.think_chip
                Accessible.description: ToolTip.text
                ToolTip.text: locked ? app.t.think_locked_tip : on ? app.t.think_on_tip : app.t.think_off_tip
                ToolTip.delay: 500
                ToolTip.visible: hovered
                background: Rectangle {
                    radius: 14
                    color: thinkBtn.on ? box.c.tint : thinkBtn.hovered ? box.c.hover : "transparent"
                    border.width: thinkBtn.visualFocus ? 2 : thinkBtn.on ? 1 : 0
                    border.color: thinkBtn.visualFocus ? box.c.saffron : box.c.accentLine
                    Behavior on color { ColorAnimation { duration: 140 } }
                }
                contentItem: Item {
                    Row {
                        id: thinkRow
                        anchors.centerIn: parent
                        spacing: 5
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: thinkBtn.locked ? "lock" : "bulb"; size: 14
                               color: thinkBtn.on ? box.c.tintText : box.c.muted }
                        Text {
                            visible: box.roomy || thinkBtn.on
                            anchors.verticalCenter: parent.verticalCenter
                            text: app.t.think_chip
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.weight: thinkBtn.on ? Font.DemiBold : Font.Medium
                            color: thinkBtn.on ? box.c.tintText : box.c.muted
                        }
                    }
                }
            }
            AbstractButton {                 // the conversation's project (Work mode): its instructions and files go with it
                id: projectBtn
                readonly property bool set: chat.project !== ""
                visible: set || projects.items.length > 0 || box.roomy
                Layout.alignment: Qt.AlignVCenter
                Layout.maximumWidth: box.roomy ? 180 : 120
                implicitWidth: projectRow.implicitWidth + 16; implicitHeight: 28
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                onClicked: box.openProjects()
                Accessible.role: Accessible.ButtonMenu
                Accessible.name: set ? app.t.project_chip_tip.replace("%1", chat.projectName) : app.t.project_chip_none
                ToolTip.text: set ? app.t.project_chip_tip.replace("%1", chat.projectName) : app.t.project_chip_none
                ToolTip.delay: 500
                ToolTip.visible: hovered
                background: Rectangle {
                    radius: 14
                    color: projectBtn.set ? box.c.tint : projectBtn.hovered || projectMenu.opened ? box.c.hover : "transparent"
                    border.width: projectBtn.visualFocus ? 2 : projectBtn.set ? 1 : 0
                    border.color: projectBtn.visualFocus ? box.c.saffron : box.c.accentLine
                }
                contentItem: Item {
                    clip: true
                    RowLayout {
                        id: projectRow
                        anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                        spacing: 5
                        Icon { name: "folder"; size: 13; color: projectBtn.set ? box.c.tintText : box.c.muted }
                        Text {
                            Layout.fillWidth: true
                            visible: projectBtn.set || box.roomy
                            text: projectBtn.set ? chat.projectName : app.t.project_none
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.weight: projectBtn.set ? Font.DemiBold : Font.Medium
                            color: projectBtn.set ? box.c.tintText : box.c.muted
                        }
                    }
                }
            }
            Item { Layout.fillWidth: true }
            ToolbarChip {                    // what Ornis may do on its own (this computer, or the cloud only): on the right, as in Code
                id: envBtn
                readonly property bool local: !!app.prefs.local_tools
                readonly property string level: local ? app.computerMode : "cloud"
                Layout.alignment: Qt.AlignVCenter
                onClicked: box.openEnvironment()
                menuOpen: envMenu.opened
                iconName: level === "cloud" ? "cloud" : level === "full" ? "play" : level === "auto" ? "shieldCheck" : "hand"
                label: level === "cloud" ? app.t.perm_cloud : app.t["computer_" + level]
                showLabel: box.roomy || level === "full"
                tone: level === "full" ? "saffron" : level === "auto" ? "tint" : "plain"
                tip: local ? app.t.env_tip.replace("%1", app.computerEnvironment + " · " + app.t["computer_" + app.computerMode]) : app.t.cloud_only
            }
            ContextGauge { id: contextGauge; Layout.alignment: Qt.AlignVCenter; onCompactRequested: chat.compact() }
            AbstractButton {                 // dictation: what is said comes into the box (Voxtral, by the cloud)
                id: mic
                readonly property var v: chat.voice
                visible: v.available
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: v.recording ? micRow.implicitWidth + 20 : 32
                implicitHeight: 32
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                enabled: !v.busy
                onClicked: v.toggle()
                Accessible.name: v.recording ? app.t.dictate_stop : v.busy ? app.t.dictate_busy : app.t.dictate
                Accessible.role: Accessible.Button
                ToolTip.text: Accessible.name
                ToolTip.delay: 450
                ToolTip.visible: hovered
                background: Rectangle {
                    radius: height / 2
                    color: mic.v.recording ? box.c.danger : mic.hovered ? box.c.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 120; easing.type: Easing.OutCubic } }
                    Rectangle {
                        anchors.fill: parent; anchors.margins: -3
                        radius: height / 2; color: "transparent"
                        border.width: 2; border.color: box.c.saffron
                        visible: mic.visualFocus
                    }
                }
                contentItem: Item {
                    RowLayout {
                        id: micRow
                        anchors.centerIn: parent
                        spacing: 6
                        Rectangle {
                            visible: mic.v.recording
                            Layout.preferredWidth: 10; Layout.preferredHeight: 10; radius: 2
                            color: "white"
                        }
                        Icon {
                            visible: !mic.v.recording
                            name: "mic"; size: 18
                            color: mic.hovered ? box.c.text : box.c.muted
                            opacity: mic.v.busy ? pulse.value : 1
                        }
                        Text {
                            visible: mic.v.recording
                            text: Math.floor(mic.v.elapsed / 60) + ":" + String(mic.v.elapsed % 60).padStart(2, "0")
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            font.features: { "tnum": 1 }
                            color: "white"
                        }
                    }
                    QtObject { id: pulse; property real value: 1 }
                    SequentialAnimation {
                        running: mic.v.busy && Qt.styleHints.reduceMotion !== true
                        loops: Animation.Infinite
                        NumberAnimation { target: pulse; property: "value"; to: 0.35; duration: 500 }
                        NumberAnimation { target: pulse; property: "value"; to: 1; duration: 500 }
                    }
                }
                Connections {
                    target: chat.voice
                    function onText(said) { if (box.visible) box.insert(said) }   // Code has its own box
                }
            }
            AbstractButton {                 // send, or while Ornis writes, stop (a square, never a cross: it closes nothing)
                id: action
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: 34; implicitHeight: 34
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                enabled: chat.busy || box.canSend
                readonly property bool stopping: chat.busy && !box.queueing
                onClicked: stopping ? chat.stop() : box.send()
                Accessible.name: stopping ? app.t.stop : box.queueing ? app.t.send_later : app.t.send
                ToolTip.text: Accessible.name
                ToolTip.delay: 450
                ToolTip.visible: hovered
                background: Rectangle {
                    radius: width / 2
                    color: !action.enabled ? "transparent" : action.hovered ? box.c.actionHover : box.c.action
                    Behavior on color { ColorAnimation { duration: 120; easing.type: Easing.OutCubic } }
                    Rectangle {
                        anchors.fill: parent; anchors.margins: -3
                        radius: width / 2; color: "transparent"
                        border.width: 2; border.color: box.c.saffron
                        visible: action.visualFocus
                    }
                }
                contentItem: Item {
                    Rectangle {
                        anchors.centerIn: parent
                        visible: action.stopping
                        width: 11; height: 11; radius: 2
                        color: box.c.actionText
                    }
                    Icon {
                        anchors.centerIn: parent
                        visible: !action.stopping
                        name: box.queueing ? "clock" : "send"; size: 18
                        color: action.enabled ? box.c.actionText : box.c.muted
                    }
                }
            }
        }
    }

    Popup {
        id: mentionPopup
        parent: box
        x: 12
        y: -height - 8
        width: Math.min(440, box.width - 24)
        height: Math.min(310, mentionList.contentHeight + 12)
        padding: 6
        visible: chat.mentions.length > 0 && box.mentionStart >= 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: box.mentionStart = -1
        background: Rectangle {
            radius: 12
            color: box.c.card
            border.width: 1; border.color: box.c.line
        }
        contentItem: ListView {
            id: mentionList
            clip: true
            model: chat.mentions
            currentIndex: box.mentionIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: AbstractButton {
                id: mRow
                required property var modelData
                required property int index
                width: mentionList.width
                implicitHeight: 42
                hoverEnabled: true
                onHoveredChanged: if (hovered) box.mentionIndex = index
                onClicked: box.applyMention(modelData)
                background: Rectangle {
                    radius: 8
                    color: index === box.mentionIndex ? box.c.tint : mRow.hovered ? box.c.hover : "transparent"
                }
                contentItem: RowLayout {
                    spacing: 10
                    anchors.fill: parent
                    anchors.leftMargin: 10; anchors.rightMargin: 10
                    Icon {
                        name: mRow.modelData.icon || "file"
                        size: 16
                        color: mRow.index === box.mentionIndex ? box.c.tintText : box.c.muted
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: mRow.modelData.label || ""
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            color: mRow.index === box.mentionIndex ? box.c.tintText : box.c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: (mRow.modelData.sub || "") !== ""
                            text: mRow.modelData.sub || ""
                            elide: Text.ElideMiddle
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11
                            color: mRow.index === box.mentionIndex ? box.c.tintText : box.c.muted
                            opacity: 0.85
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: slashPopup
        parent: box
        x: 12
        y: -height - 8
        width: Math.min(440, box.width - 24)
        height: Math.min(310, slashList.contentHeight + 12)
        padding: 6
        visible: chat.slashes.length > 0 && box.slashStart >= 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: box.slashStart = -1
        background: Rectangle {
            radius: 12
            color: box.c.card
            border.width: 1; border.color: box.c.line
        }
        contentItem: ListView {
            id: slashList
            clip: true
            model: chat.slashes
            currentIndex: box.slashIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: AbstractButton {
                id: sRow
                required property var modelData
                required property int index
                width: slashList.width
                implicitHeight: 42
                hoverEnabled: true
                onHoveredChanged: if (hovered) box.slashIndex = index
                onClicked: box.applySlash(modelData)
                background: Rectangle {
                    radius: 8
                    color: index === box.slashIndex ? box.c.tint : sRow.hovered ? box.c.hover : "transparent"
                }
                contentItem: Item {
                    RowLayout {
                        spacing: 10
                        anchors.fill: parent
                        anchors.leftMargin: 10; anchors.rightMargin: 10
                        Icon {
                            name: sRow.modelData.icon || "sparkle"
                            size: 16
                            color: sRow.index === box.slashIndex ? box.c.tintText : box.c.famCommunicate
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                Layout.fillWidth: true
                                text: sRow.modelData.label || ""
                                elide: Text.ElideRight
                                font.family: "JetBrains Mono"; font.pixelSize: 13; font.weight: Font.DemiBold
                                color: sRow.index === box.slashIndex ? box.c.tintText : box.c.text
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: (sRow.modelData.sub || "") !== ""
                                text: sRow.modelData.sub || ""
                                elide: Text.ElideMiddle
                                font.family: "Schibsted Grotesk"; font.pixelSize: 11
                                color: sRow.index === box.slashIndex ? box.c.tintText : box.c.muted
                                opacity: 0.85
                            }
                        }
                    }
                }
            }
        }
    }

    OMenu {
        id: attachMenu
        OMenuItem { text: app.t.attach_computer; iconName: "devices"; onTriggered: box.attachFromComputer() }
        OMenuItem { text: app.t.attach_drive; iconName: "cloud"; onTriggered: box.attachFromDrive() }

        OMenuItem { visible: app.prefs.local_tools !== false; text: app.t.mention_pick_workspace; iconName: "folder"; onTriggered: box.workspacePickRequested() }
        OMenuItem { visible: app.prefs.local_tools !== false; text: app.t.mention_screenshot; iconName: "image"; onTriggered: chat.captureScreenshot() }
        // typed as well (« @ » anywhere, « / » at the start): offered here so that they are found
        Rectangle { width: parent ? parent.width : 0; height: 1; color: box.c.hairline }
        OMenuItem { text: app.t.mention_menu; iconName: "link"; onTriggered: box.openMentions() }
        OMenuItem { text: app.t.slash_menu; iconName: "terminal"; onTriggered: box.openSlashes() }
    }

    // one mode at a time: a title and what it does, the current one checked
    component ModeItem: AbstractButton {
        id: mi
        property string mode
        property string iconName
        property string sub
        property bool locked
        readonly property bool current: chat.uiMode === mode
        width: parent ? parent.width : implicitWidth
        implicitHeight: miRow.implicitHeight + 14
        hoverEnabled: true
        onClicked: { modeMenu.close(); box.pickMode(mode) }
        Accessible.role: Accessible.RadioButton
        Accessible.checked: current
        Accessible.name: text + ", " + sub
        background: Rectangle { radius: 8; color: mi.hovered || mi.visualFocus ? box.c.hover : "transparent" }
        contentItem: RowLayout {
            id: miRow
            spacing: 10
            Rectangle {
                Layout.alignment: Qt.AlignTop
                implicitWidth: 28; implicitHeight: 28; radius: 8
                color: mi.mode === "plan" ? box.c.saffronTint : mi.current ? box.c.tint : box.c.hover
                Icon { anchors.centerIn: parent; name: mi.locked ? "lock" : mi.iconName; size: 15
                       color: mi.mode === "plan" ? box.c.saffronInk : mi.current ? box.c.tintText : box.c.muted }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text { text: mi.text; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: box.c.text }
                Text {
                    Layout.fillWidth: true
                    text: mi.locked ? app.t.work_plus : mi.sub
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: box.c.muted
                }
            }
            Icon { visible: mi.current; Layout.alignment: Qt.AlignVCenter; name: "check"; size: 16; color: box.c.famCommunicate }
        }
    }
    OMenu {
        id: modeMenu
        implicitWidth: 320
        heading: app.t.mode_menu_title
        subheading: app.t.mode_cycle_tip
        ModeItem { mode: "agent"; iconName: "ornis"; text: app.t.mode_agent; sub: app.t.mode_agent_sub }
        ModeItem { mode: "plan"; iconName: "list"; text: app.t.mode_plan + " · " + app.t.plan_readonly; sub: app.t.mode_plan_sub }
        ModeItem { mode: "goal"; iconName: "flag"; text: app.t.mode_goal; sub: app.t.mode_goal_sub; locked: chat.workEstimate.allowed === false }
        ModeItem { mode: "research"; iconName: "search"; text: app.t.research_menu; sub: app.t.mode_research_sub; locked: chat.workEstimate.allowed === false }
    }
    OMenu {                                  // « Demander »: what Ornis may do on this computer, changed in one click
        id: envMenu
        implicitWidth: 340
        heading: app.t.settings_computer + " · " + app.computerEnvironment
        subheading: !app.prefs.local_tools ? app.t.cloud_only
                    : app.computerUntil ? app.t.computer_until.replace("%1", app.computerUntil) : ""
        OMenuItem {
            text: app.t.local_tools
            switchable: true
            on: !!app.prefs.local_tools
            onClicked: app.setPref("local_tools", !app.prefs.local_tools)
        }
        Repeater {
            model: app.prefs.local_tools ? [["ask", "hand"], ["auto", "shieldCheck"], ["full", "play"]] : []
            OMenuItem {
                required property var modelData
                text: app.t["computer_" + modelData[0]]
                iconName: app.computerMode === modelData[0] ? "check" : modelData[1]
                onTriggered: { app.setComputerMode(modelData[0]); input.forceActiveFocus() }
            }
        }
        Rectangle { width: parent ? parent.width : 0; height: 9; color: "transparent"
            Rectangle { anchors.centerIn: parent; width: parent.width - 12; height: 1; color: box.c.line } }
        OMenuItem { text: app.t.computer_open; iconName: "devices"; onTriggered: app.openComputer() }
        OMenuItem { text: app.t.extensions_open; iconName: "sparkle"; onTriggered: app.openExtensions() }
    }
    OMenu {                                  // the conversation's project: one of them, a new one, none
        id: projectMenu
        heading: app.t.menu_project
        Repeater {
            model: projects.items.slice(0, 10)
            OMenuItem {
                required property var modelData
                text: modelData.name
                iconName: modelData.id === chat.project ? "check" : "folder"
                onTriggered: { chat.setProject(modelData.id); input.forceActiveFocus() }
            }
        }
        Rectangle { visible: projects.items.length > 0; width: parent ? parent.width : 0; height: 9; color: "transparent"
            Rectangle { anchors.centerIn: parent; width: parent.width - 12; height: 1; color: box.c.line } }
        OMenuItem { text: app.t.project_new; iconName: "folderPlus"; onTriggered: box.projectCreateRequested() }
        OMenuItem { visible: chat.project !== ""; text: app.t.menu_no_project; iconName: "close"; onTriggered: { chat.setProject(""); input.forceActiveFocus() } }
    }
    FileDialog {
        id: picker
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.attach
        fileMode: FileDialog.OpenFiles
        onAccepted: { chat.addFiles(selectedFiles); input.forceActiveFocus() }
    }
    DrivePicker {
        id: drive
        onPicked: rows => { chat.addCloudFiles(rows); input.forceActiveFocus() }
    }
}
