// The open conversation: its head on a card of the family (picture, what it is, who is there, the calls, Ornis),
// the pinned message, the messages scheduled, the messages (older ones come when scrolling up), who is writing,
// the composer. Ornis sums up what was missed, writes the minutes (for Notes), finds the tasks (for Tâches),
// answers a question about the conversation, suggests replies. During a call it sits beside the call (compact).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    readonly property var c: theme.c
    readonly property var room: meet.room
    readonly property var extras: meet.extras
    readonly property bool typing: composer.typing
    property bool compact: false
    property bool infoOpen: false
    readonly property bool channel: room.type === 2 || room.type === 3
    // a group's tab: the chat, or in its place everything shared (FilesPane) or the people (PeoplePane)
    property string tab: "chat"
    readonly property string shownTab: channel && !compact ? tab : "chat"
    Connections { target: meet; function onRoomChanged() { if (meet.current !== pane.tabRoom) { pane.tabRoom = meet.current; pane.tab = "chat" } } }
    property string tabRoom: ""
    onShownTabChanged: {
        if (shownTab === "shared") filesPane.focusSearch()
        else if (shownTab === "people") peoplePane.focusSearch()
        else composer.focusText()
    }
    signal infoWanted()
    signal callWanted(bool video)
    signal newConversation()
    signal planWanted()
    signal laterWanted(string text)
    signal scheduledEdit(var message)
    signal breakoutWanted()
    signal roomSettingsWanted()
    color: c.bg

    function focusComposer() { composer.focusText() }
    function openSearch() {
        if (shownTab === "shared") filesPane.focusSearch()
        else if (shownTab === "people") peoplePane.focusSearch()
        else { searchBar.visible = true; searchField.forceActiveFocus() }
    }

    // ---- Ornis: one card above the messages (summary, minutes, a question, tasks), replies above the composer
    property int ornisRequest: -1
    property string ornisKind: ""
    property string ornisText: ""
    property var ornisTasks: []
    property var replies: []
    property int repliesRequest: -1
    property bool waitingReplies: false     // « Suggérer des réponses » asked: Ornis shows it works, above the field
    property var dismissed: ({})
    function askOrnis(kind, extra) {
        ornisKind = kind
        ornisText = ""
        ornisTasks = []
        ornisCard.token = meet.current
        ornisCard.visible = true
        const lines = kind === "summary" ? meet.summaryLines() : meet.recentLines(kind === "ask" ? 200 : 150)
        ornisRequest = ornis.ask(kind, Object.assign({ room: pane.room.name || "", lines: lines }, extra || {}))
        if (kind === "summary") { const d = Object.assign({}, dismissed); d[meet.current] = true; dismissed = d }
    }
    function openAsk() {
        ornisKind = "ask"; ornisText = ""; ornisTasks = []; ornisRequest = -1
        ornisCard.token = meet.current
        ornisCard.visible = true
        question.text = ""
        question.forceActiveFocus()
    }
    function suggest() {
        replies = []
        waitingReplies = true
        repliesRequest = ornis.ask("replies", { room: pane.room.name || "", lines: meet.recentLines(20), me: app.profile.name || "" })
    }
    Connections {
        target: ornis
        function onAnswered(request, kind, text) {
            if (request === pane.ornisRequest) {
                if (kind === "tasks") {
                    pane.ornisTasks = app.parseJson(text).map(t => ({ title: String(t.title || ""), due: String(t.due || ""), who: String(t.who || ""), on: true })).filter(t => t.title)
                    pane.ornisText = pane.ornisTasks.length ? " " : app.t.no_tasks_found
                } else {
                    pane.ornisText = text
                }
            } else if (request === pane.repliesRequest) {
                pane.waitingReplies = false
                pane.replies = app.parseJson(text).map(String).filter(r => r).slice(0, 3)
                if (!pane.replies.length) app.toast(app.t.ornis_failed)
            }
        }
        function onFailed(request, kind, message) {
            if (request === pane.ornisRequest) { ornisCard.visible = false; app.toast(message) }
            if (request === pane.repliesRequest) { pane.repliesRequest = -1; pane.waitingReplies = false; app.toast(message) }
        }
    }
    Connections {
        target: meet
        function onRoomChanged() {
            if (ornisCard.visible && meet.current !== ornisCard.token) ornisCard.visible = false
            if (pane.replies.length && meet.current !== repliesBar.token) pane.replies = []
        }
    }

    function kicker() {
        const r = pane.room
        if (!r.token) return ""
        if (r.breakout) return app.t.kind_breakout
        if (r.type === 1) return app.t.kind_one + (r.status === "online" ? " · " + app.t.status_online : "")
        if (r.type === 6) return app.t.kind_note
        if (r.event) return app.t.kind_event
        return (r.public ? app.t.kind_public : app.t.kind_group) + (r.participants ? " · " + app.plural("participants", r.participants) : "")
    }
    function subtitle() {
        const r = pane.room
        if (!r.token) return ""
        if (r.hasCall) return app.t.call_ongoing_since.replace("%1", r.callStart ? app.ago(r.callStart) : "")
        if (r.type === 1) {
            if (r.statusMessage) return r.statusMessage
            return r.status === "away" ? app.t.status_away : r.status === "dnd" ? app.t.status_dnd : r.status === "busy" ? app.t.status_busy : ""
        }
        return r.description || ""
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // the head
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: pane.compact ? 60 : 76
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.tint(pane.c.chrome, Qt.alpha(pane.room.hasCall ? pane.c.ok : pane.c.famCommunicate, theme.dark ? 0.18 : 0.09)) }
                GradientStop { position: 0.55; color: pane.c.chrome }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pane.c.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: pane.compact ? 12 : 20; anchors.rightMargin: 12
                spacing: 14
                Item {
                    visible: !pane.compact
                    implicitWidth: 48; implicitHeight: 48
                    Rectangle {
                        anchors.fill: parent; anchors.margins: -3
                        radius: width / 2
                        color: "transparent"
                        border.width: 2
                        border.color: pane.room.hasCall ? pane.c.ok : Qt.alpha(pane.c.famCommunicate, 0.35)
                    }
                    RoomAvatar { anchors.fill: parent; room: pane.room; size: 48 }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true
                        visible: !pane.compact
                        text: pane.kicker()
                        elide: Text.ElideRight
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                        color: pane.room.hasCall ? pane.c.okInk : pane.c.famCommunicate
                    }
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true
                        text: pane.room.name || ""
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: pane.compact ? 16 : 20; font.weight: Font.Bold
                        font.letterSpacing: -0.3
                        color: pane.c.text
                    }
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: pane.subtitle()
                        elide: Text.ElideRight
                        font.pixelSize: 12
                        color: pane.c.muted
                    }
                }
                OButton {
                    visible: !pane.compact && !calls.active
                    kind: pane.room.hasCall ? "primary" : "secondary"
                    iconName: "phone"
                    text: pane.room.hasCall ? app.t.join_call : ""
                    tip: app.t.call_audio
                    enabled: !!(pane.room.canCall || pane.room.hasCall)
                    onClicked: pane.callWanted(false)
                }
                OButton {
                    visible: !pane.compact && !calls.active
                    kind: pane.room.hasCall ? "secondary" : "primary"
                    iconName: "video"
                    tip: app.t.call_video
                    enabled: !!(pane.room.canCall || pane.room.hasCall)
                    onClicked: pane.callWanted(true)
                }
                OButton { id: ornisButton; kind: "quiet"; iconName: "ornis"; tip: app.t.ornis_menu; onClicked: ornisMenu.popupAt(ornisButton, true) }
                OButton { kind: "quiet"; iconName: "search"; tip: app.t.search_in_conversation + " (Ctrl+F)"; onClicked: pane.openSearch(); visible: !pane.compact }
                OButton { kind: pane.infoOpen ? "secondary" : "quiet"; iconName: "info"; tip: app.t.details + " (Ctrl+I)"; onClicked: pane.infoWanted(); visible: !pane.compact }
                OButton { id: moreButton; kind: "quiet"; iconName: "more"; tip: app.t.more; visible: !pane.compact; onClicked: moreMenu.popupAt(moreButton, true) }
            }
        }

        // a group: its tabs under the head, like a workspace (Slack): the chat, the threads, the files, the people
        Rectangle {
            id: tabsBar
            visible: pane.channel && !pane.compact
            Layout.fillWidth: true
            implicitHeight: 40
            color: pane.c.chrome
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pane.c.hairline }
            Row {
                id: tabs
                x: 14
                height: parent.height
                spacing: 2
                readonly property string current: pane.shownTab
                Repeater {
                    model: [{ id: "chat", icon: "chat", text: app.t.tab_chat },
                            { id: "threads", icon: "reply", text: app.t.tab_threads + ((pane.extras.threads || []).length ? " · " + pane.extras.threads.length : ""),
                              hidden: !(pane.extras.threads || []).length },
                            { id: "shared", icon: "folder", text: app.t.tab_files },
                            { id: "people", icon: "people", text: app.t.rs_tab_people + " · " + meet.participants.length }]
                    AbstractButton {
                        id: tab
                        required property var modelData
                        readonly property bool current: tabs.current === modelData.id
                        visible: !modelData.hidden
                        height: tabs.height
                        implicitWidth: tabRow.implicitWidth + 20
                        hoverEnabled: true
                        Accessible.name: modelData.text
                        onClicked: {
                            if (modelData.id === "threads") threadsMenu.popupAt(tab, true)
                            else pane.tab = modelData.id
                        }
                        background: Item {
                            Rectangle {
                                anchors.fill: parent; anchors.topMargin: 5; anchors.bottomMargin: 5
                                radius: 8
                                color: tab.hovered && !tab.current ? pane.c.hover : "transparent"
                            }
                            Rectangle {
                                visible: tab.current
                                anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                                width: parent.width - 12; height: 2; radius: 1
                                color: pane.c.famCommunicate
                            }
                        }
                        contentItem: Item {
                            Row {
                                id: tabRow
                                anchors.centerIn: parent
                                spacing: 6
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: tab.modelData.icon; size: 14
                                       color: tab.current ? pane.c.text : pane.c.muted }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    textFormat: Text.PlainText
                                    text: tab.modelData.text
                                    font.pixelSize: 13; font.weight: tab.current ? Font.DemiBold : Font.Normal
                                    color: tab.current ? pane.c.text : pane.c.muted
                                }
                            }
                        }
                    }
                }
            }
        }

        // search in the conversation
        Rectangle {
            id: searchBar
            visible: false
            Layout.fillWidth: true
            implicitHeight: visible ? searchColumn.implicitHeight + 16 : 0
            color: pane.c.chrome
            property var results: []
            Connections { target: meet; function onSearchDone(results) { searchBar.results = results } }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pane.c.hairline }
            ColumnLayout {
                id: searchColumn
                x: 16; y: 8
                width: parent.width - 32
                RowLayout {
                    Layout.fillWidth: true
                    OTextField {
                        id: searchField
                        Layout.fillWidth: true
                        iconName: "search"
                        placeholderText: app.t.search_in_conversation
                        onAccepted: meet.searchMessages(text)
                        Keys.onEscapePressed: searchBar.visible = false
                    }
                    OButton { kind: "quiet"; iconName: "close"; tip: app.t.close; onClicked: { searchBar.visible = false; searchBar.results = [] } }
                }
                Repeater {
                    model: searchBar.results.slice(0, 6)
                    AbstractButton {
                        id: hit
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 40
                        hoverEnabled: true
                        onClicked: meet.jumpTo(modelData.id)
                        background: Rectangle { radius: 8; color: hit.hovered ? pane.c.hover : "transparent" }
                        contentItem: ColumnLayout {
                            spacing: 0
                            Text { textFormat: Text.PlainText; Layout.leftMargin: 8; text: hit.modelData.title; font.pixelSize: 12; font.weight: Font.DemiBold; color: pane.c.text; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { textFormat: Text.PlainText; Layout.leftMargin: 8; text: hit.modelData.text; font.pixelSize: 12; color: pane.c.muted; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                    }
                }
                Text {
                    visible: searchField.text !== "" && searchBar.results.length === 0
                    text: app.t.search_hint
                    font.pixelSize: 12; color: pane.c.faint
                }
            }
        }

        // the pinned message
        AbstractButton {
            id: pinned
            visible: !!pane.extras.pinned && !!pane.extras.pinned.id
            Layout.fillWidth: true
            Layout.leftMargin: pane.compact ? 8 : 16; Layout.rightMargin: pane.compact ? 8 : 16; Layout.topMargin: 10
            implicitHeight: 52
            clip: true
            hoverEnabled: true
            onClicked: meet.jumpTo(pane.extras.pinned.id)
            background: Surface {
                radius: 10
                color: pinned.hovered ? Qt.tint(pane.c.card, Qt.alpha(pane.c.saffron, 0.06)) : pane.c.card
                Rectangle { width: 3; radius: 1.5; color: pane.c.saffron; anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 9; bottomMargin: 9 } }
            }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 10; name: "pushpin"; size: 16; color: pane.c.saffronInk }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text { textFormat: Text.PlainText; text: app.t.pinned_by.replace("%1", pane.extras.pinned ? pane.extras.pinned.name || "" : ""); font.pixelSize: 11; font.weight: Font.DemiBold; color: pane.c.saffronInk }
                    // one line, whatever the message (its lines joined): the whole of it is a click away
                    Text { Layout.fillWidth: true; text: pane.extras.pinned ? String(pane.extras.pinned.text || "").replace(/\s*\n\s*/g, " · ") : ""
                           elide: Text.ElideRight; maximumLineCount: 1; wrapMode: Text.NoWrap; clip: true
                           textFormat: Text.PlainText; font.pixelSize: 13; color: pane.c.body }
                }
                OButton {
                    Layout.rightMargin: 6
                    kind: "quiet"; iconName: "close"; height_: 28
                    tip: pane.room.moderator ? app.t.unpin : app.t.hide_pin
                    onClicked: pane.room.moderator ? meet.pin(pane.extras.pinned.id, false) : meet.hidePin(pane.extras.pinned.id)
                }
            }
        }

        // the messages scheduled (ours)
        ColumnLayout {
            visible: (pane.extras.scheduled || []).length > 0 && !pane.compact
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.topMargin: 10
            spacing: 4
            AbstractButton {
                id: scheduledHead
                property bool open: false
                Layout.fillWidth: true
                implicitHeight: 34
                hoverEnabled: true
                onClicked: open = !open
                background: Rectangle { radius: 8; color: scheduledHead.hovered ? pane.c.hover : pane.c.tint }
                contentItem: RowLayout {
                    spacing: 8
                    Icon { Layout.leftMargin: 10; name: "clock"; size: 15; color: pane.c.tintText }
                    Text {
                        Layout.fillWidth: true
                        text: app.plural("scheduled_count", (pane.extras.scheduled || []).length)
                              + ((pane.extras.scheduled || []).length ? " · " + app.t.next_at.replace("%1", app.when(pane.extras.scheduled[0].at)) : "")
                        font.pixelSize: 13; color: pane.c.tintText; elide: Text.ElideRight
                    }
                    Icon { Layout.rightMargin: 10; name: scheduledHead.open ? "collapse" : "expand"; size: 14; color: pane.c.tintText }
                }
            }
            Repeater {
                model: scheduledHead.open ? pane.extras.scheduled : []
                Surface {
                    id: later
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: 52
                    radius: 10
                    raised: false
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 14; anchors.rightMargin: 6
                        spacing: 8
                        Text { textFormat: Text.PlainText;
                            text: app.when(later.modelData.at)
                            font.family: "JetBrains Mono"; font.pixelSize: 12; color: pane.c.famCommunicate
                        }
                        Text { Layout.fillWidth: true; text: later.modelData.text; elide: Text.ElideRight; textFormat: Text.PlainText; font.pixelSize: 13; color: pane.c.body }
                        OButton { kind: "quiet"; iconName: "send"; height_: 30; tip: app.t.send_now; onClicked: meet.sendScheduledNow(later.modelData.id) }
                        OButton { kind: "quiet"; iconName: "edit"; height_: 30; tip: app.t.edit; onClicked: pane.scheduledEdit(later.modelData) }
                        OButton { kind: "quiet"; iconName: "trash"; height_: 30; tip: app.t.delete_message; onClicked: meet.deleteScheduled(later.modelData.id) }
                    }
                }
            }
        }

        // what was missed: Ornis offers to sum it up
        Surface {
            visible: meet.missed >= 5 && !pane.dismissed[meet.current] && !ornisCard.visible
            Layout.fillWidth: true
            Layout.leftMargin: pane.compact ? 8 : 16; Layout.rightMargin: pane.compact ? 8 : 16; Layout.topMargin: 10
            implicitHeight: 50
            radius: 10
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.tint(pane.c.card, Qt.alpha(pane.c.famCommunicate, theme.dark ? 0.2 : 0.1)) }
                GradientStop { position: 1; color: pane.c.card }
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14; anchors.rightMargin: 8
                spacing: 10
                Icon { name: "ornis"; size: 18; color: pane.c.famCommunicate }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: app.plural("missed_count", meet.missed); font.pixelSize: 13; color: pane.c.text; elide: Text.ElideRight }
                OButton { kind: "accent"; iconName: "ornis"; text: app.t.summarize; onClicked: pane.askOrnis("summary") }
                OButton { kind: "quiet"; iconName: "close"; tip: app.t.close
                          onClicked: { const d = Object.assign({}, pane.dismissed); d[meet.current] = true; pane.dismissed = d } }
            }
        }

        // Ornis's card
        Surface {
            id: ornisCard
            property string token
            visible: false
            Layout.fillWidth: true
            Layout.leftMargin: pane.compact ? 8 : 16; Layout.rightMargin: pane.compact ? 8 : 16; Layout.topMargin: 10
            Layout.preferredHeight: Math.min(pane.height * 0.45, ornisColumn.implicitHeight + 28)
            radius: 12
            ColumnLayout {
                id: ornisColumn
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    Icon { name: "ornis"; size: 16; color: pane.c.famCommunicate }
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true
                        text: ({ summary: app.t.summary_title, minutes: app.t.minutes_title, tasks: app.t.tasks_title, ask: app.t.ask_title })[pane.ornisKind] || ""
                        font.pixelSize: 13; font.weight: Font.DemiBold; color: pane.c.text
                    }
                    OButton { kind: "quiet"; iconName: "note"; height_: 30; tip: app.t.to_notes
                              visible: pane.ornisText.trim() !== "" && pane.ornisKind !== "tasks"
                              onClicked: pane.sendToNotes() }
                    OButton { kind: "quiet"; iconName: "copy"; height_: 30; tip: app.t.copy_text
                              visible: pane.ornisText.trim() !== "" && pane.ornisKind !== "tasks"
                              onClicked: { app.copy(pane.ornisText); app.toast(app.t.copied) } }
                    OButton { kind: "quiet"; iconName: "close"; height_: 30; tip: app.t.close; onClicked: ornisCard.visible = false }
                }
                // the question, for « Demander à cette conversation »
                OTextField {
                    id: question
                    visible: pane.ornisKind === "ask"
                    Layout.fillWidth: true
                    iconName: "ornis"
                    placeholderText: app.t.ask_placeholder
                    onAccepted: if (text.trim()) pane.askOrnis("ask", { question: text.trim() })
                }
                OrnisThinking { visible: pane.ornisText === "" && pane.ornisRequest >= 0 && !(pane.ornisKind === "ask" && question.text === ""); Layout.fillWidth: true }
                OrnisAnswer {
                    visible: pane.ornisText.trim() !== "" && pane.ornisKind !== "tasks"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentWidth: availableWidth
                        clip: true
                        Text {
                            width: parent.width
                            // Markdown, but no HTML of its own: an answer may repeat a message (an image from elsewhere)
                            text: pane.ornisText.replace(/</g, "&lt;")
                            textFormat: Text.MarkdownText
                            wrapMode: Text.WordWrap
                            lineHeight: 1.3
                            font.pixelSize: 14
                            color: pane.c.body
                        }
                    }
                }
                // the tasks found: chosen, then into Tâches
                Repeater {
                    model: pane.ornisKind === "tasks" ? pane.ornisTasks : []
                    CheckBox {
                        id: taskBox
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        checked: modelData.on
                        onToggled: { const l = pane.ornisTasks.slice(); l[index] = Object.assign({}, l[index], { on: checked }); pane.ornisTasks = l }
                        contentItem: Text { textFormat: Text.PlainText;
                            leftPadding: taskBox.indicator.width + 8
                            text: taskBox.modelData.title + (taskBox.modelData.who ? "  · " + taskBox.modelData.who : "") + (taskBox.modelData.due ? "  · " + taskBox.modelData.due : "")
                            wrapMode: Text.Wrap; font.pixelSize: 14; color: pane.c.body
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
                Text { visible: pane.ornisKind === "tasks" && pane.ornisText.trim() !== "" && !pane.ornisTasks.length; text: pane.ornisText; font.pixelSize: 13; color: pane.c.muted }
                OButton {
                    visible: pane.ornisKind === "tasks" && pane.ornisTasks.some(t => t.on)
                    Layout.alignment: Qt.AlignRight
                    kind: "primary"; iconName: "checklist"
                    text: app.plural("add_tasks", pane.ornisTasks.filter(t => t.on).length)
                    onClicked: {
                        if (app.toTasks(pane.ornisTasks.filter(t => t.on), pane.room.link || "")) { app.toast(app.t.tasks_added); ornisCard.visible = false }
                        else app.toast(app.t.tasks_unavailable)
                    }
                }
            }
        }

        // messages
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: meet.messages
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            cacheBuffer: 1200
            property bool stick: true
            topMargin: 8; bottomMargin: 12
            delegate: MessageRow {
                compact: pane.compact
                onReplyWanted: message => composer.replyTo(message)
                onEditWanted: message => composer.edit(message)
                onQuoteClicked: id => meet.jumpTo(id)
                onMentionClicked: (kind, id) => { if (kind === "user" && id !== app.profile.user) meet.openWith(id) }
                onImageWanted: (file, album) => viewer.show(file, album)
                onForwardWanted: message => forward.start(message)
                onThreadWanted: message => threadFrom.start(message)
            }
            onMovementEnded: stick = atYEnd && !meet.detached
            // messages of others that came while reading higher up: counted on « Aller aux derniers messages »
            property int unseen: 0
            onAtYEndChanged: if (atYEnd && !meet.detached) unseen = 0
            onContentYChanged: {
                if (contentY - originY < 400 && count > 0 && meet.current) meet.loadOlder()
                remember.restart()
            }
            // where each conversation was read: found again when it is opened again (this session)
            property var places: ({})
            Timer {
                id: remember
                interval: 400
                onTriggered: {
                    const room = list.shownRoom
                    if (!room || room !== meet.current || list.restoring) return
                    if (list.stick || meet.detached) { delete list.places[room]; return }
                    const i = list.indexAt(list.width / 2, list.contentY + list.topMargin + 1)
                    const item = i >= 0 ? list.itemAtIndex(i) : null
                    const id = i >= 0 ? meet.messages.idAt(i) : 0
                    if (!id || !item) return
                    list.places[room] = {id: id, offset: item.y - list.contentY}
                }
            }
            property bool restoring: false
            function restore() {
                const place = places[meet.current]
                if (!place) return false
                const i = meet.messages.indexOf(String(place.id))
                stick = false
                if (i < 0) { meet.jumpTo(place.id); return true }     // older than what is kept: loaded around it
                restoring = true
                const go = () => {
                    const j = meet.messages.indexOf(String(place.id))
                    if (j < 0) return
                    positionViewAtIndex(j, ListView.Beginning)
                    const item = itemAtIndex(j)
                    if (item) contentY = Math.max(originY - topMargin, item.y - place.offset)
                }
                Qt.callLater(go)
                restoreSettle.go = go
                restoreSettle.restart()
                return true
            }
            Timer {
                id: restoreSettle
                property var go: null
                interval: 160
                onTriggered: { if (go && !list.stick) go(); list.restoring = false }
            }
            onCountChanged: if (stick) toEnd()
            // a row that grows at the end (the line « Nouveaux messages », a preview): still the very end
            onContentHeightChanged: if (stick && !atYEnd) toEnd()
            onHeightChanged: if (stick) toEnd()
            // positionViewAtEnd stops short while the last rows learn their height (pictures, previews): then
            // the very end, once more when they have
            function toEnd() {
                Qt.callLater(() => {
                    positionViewAtEnd()
                    contentY = Math.max(originY - topMargin, originY + contentHeight + bottomMargin - height)
                    settle.restart()
                })
            }
            Timer { id: settle; interval: 120; onTriggered: if (list.stick) list.contentY = Math.max(list.originY - list.topMargin, list.originY + list.contentHeight + list.bottomMargin - list.height) }
            Connections {
                target: meet
                function onRoomChanged() {
                    if (meet.current === list.shownRoom) return
                    list.shownRoom = meet.current
                    list.unseen = 0
                    if (!list.restore()) { list.stick = true; list.toEnd() }
                }
                function onJumped(id) {
                    const i = meet.messages.indexOf(String(id))
                    if (i >= 0) { list.stick = false; list.positionViewAtIndex(i, ListView.Center); list.currentIndex = i }
                }
                // just opened with unread messages: from the first of them (the line « Nouveaux messages »),
                // unless they all fit with the newest
                function onUnreadAt(id) {
                    list.unreadIndex = meet.messages.indexOf(String(id))
                    if (list.unreadIndex < 0 || list.places[meet.current]) return     // back where it was read
                    list.stick = false
                    Qt.callLater(list.toUnread)
                    unreadSettle.restart()
                }
                function onArrivedHere(count) { if (!list.atYEnd || meet.detached) list.unseen += count }
                function onLatestShown() { list.unseen = 0; list.stick = true; list.toEnd() }
            }
            property string shownRoom: ""
            property int unreadIndex: -1
            function toUnread() {
                if (unreadIndex < 0 || unreadIndex >= count) return
                positionViewAtIndex(unreadIndex, ListView.Beginning)
                contentY = Math.max(originY - topMargin, contentY - 24)
                // everything unread fits under it: simply the end (and the list follows what comes)
                if (contentY >= originY + contentHeight + bottomMargin - height - 4) { stick = true; toEnd() }
            }
            Timer { id: unreadSettle; interval: 160; onTriggered: if (!list.stick) list.toUnread() }

            // the messages going away fade under the top edge (on the list itself, not in what scrolls)
            Rectangle {
                parent: list
                z: 2
                anchors.top: parent.top
                width: parent.width; height: 40
                opacity: list.contentY - list.originY > -list.topMargin + 2 ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 160 } }
                gradient: Gradient {
                    GradientStop { position: 0; color: pane.c.bg }
                    GradientStop { position: 1; color: Qt.alpha(pane.c.bg, 0) }
                }
            }

            // back to the newest (after a jump far up: loaded again), with what came meanwhile
            OButton {
                id: toLatest
                visible: (!list.atYEnd || meet.detached) && list.count > 0
                anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
                kind: "secondary"
                iconName: "chevronDown"
                tip: app.t.to_latest
                onClicked: { if (meet.detached) meet.toLatest(); else { list.unseen = 0; list.stick = true; list.toEnd() } }
                Rectangle {
                    visible: list.unseen > 0
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: -6
                    implicitWidth: Math.max(20, unseenText.implicitWidth + 10); implicitHeight: 20; radius: 10
                    color: pane.c.famCommunicate
                    Text { id: unseenText; anchors.centerIn: parent; text: list.unseen > 99 ? "99+" : list.unseen; font.pixelSize: 11; font.weight: Font.DemiBold; color: "white" }
                }
            }
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(360, parent.width - 40)
                visible: list.count === 0
                spacing: 10
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: 64; implicitHeight: 64; radius: 32
                    color: Qt.alpha(pane.c.famCommunicate, theme.dark ? 0.2 : 0.1)
                    Icon { anchors.centerIn: parent; name: "chat"; size: 28; color: pane.c.famCommunicate }
                }
                Text { textFormat: Text.PlainText;
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: meet.state === "offline" ? app.t.offline_no_messages : app.t.no_messages
                    wrapMode: Text.WordWrap
                    font.pixelSize: 14; color: pane.c.muted
                }
            }
        }

        // who writes, where one looks: above the field
        Item {
            Layout.fillWidth: true
            implicitHeight: meet.typing.length ? 26 : 0
            Behavior on implicitHeight { NumberAnimation { duration: 120 } }
            clip: true
            RowLayout {
                anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: pane.compact ? 12 : 22
                spacing: 8
                opacity: meet.typing.length ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
                Rectangle {
                    implicitWidth: 34; implicitHeight: 18; radius: 9
                    color: pane.c.card
                    border.width: 1; border.color: pane.c.hairline
                    Row {
                        anchors.centerIn: parent
                        spacing: 3
                        Repeater {
                            model: 3
                            Rectangle {
                                required property int index
                                width: 5; height: 5; radius: 2.5
                                color: pane.c.famCommunicate
                                SequentialAnimation on opacity {
                                    running: meet.typing.length > 0
                                    loops: Animation.Infinite
                                    PauseAnimation { duration: index * 160 }
                                    NumberAnimation { from: 0.25; to: 1; duration: 320 }
                                    NumberAnimation { from: 1; to: 0.25; duration: 320 }
                                    PauseAnimation { duration: (2 - index) * 160 }
                                }
                            }
                        }
                    }
                }
                Text { textFormat: Text.PlainText;
                    text: app.typingText(meet.typing)
                    elide: Text.ElideRight
                    font.pixelSize: 12; font.italic: true
                    color: pane.c.muted
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                }
            }
        }

        // the lobby: the conversation is closed until a moderator opens it
        Rectangle {
            visible: pane.room.lobby === 1 && !pane.room.moderator
            Layout.fillWidth: true
            implicitHeight: 44
            color: pane.c.saffronTint
            Text {
                anchors.centerIn: parent
                text: pane.room.lobbyTimer ? app.t.lobby_until.replace("%1", app.when(pane.room.lobbyTimer)) : app.t.lobby_waiting
                color: pane.c.saffronInk; font.pixelSize: 13
            }
        }

        // replies suggested by Ornis (while it thinks: says so at once)
        RowLayout {
            visible: pane.waitingReplies && pane.replies.length === 0 && pane.room.canPost !== false
            Layout.fillWidth: true
            Layout.leftMargin: pane.compact ? 8 : 16; Layout.rightMargin: 16; Layout.bottomMargin: 6
            spacing: 8
            Icon { name: "ornis"; size: 16; color: pane.c.famCommunicate }
            Text { text: app.t.replies_thinking; font.pixelSize: 13; color: pane.c.tintText }
            OrnisThinking { Layout.preferredWidth: 120 }
            Item { Layout.fillWidth: true }
            OButton { kind: "quiet"; iconName: "close"; height_: 28; tip: app.t.cancel; onClicked: { pane.waitingReplies = false; pane.repliesRequest = -1 } }
        }
        Flow {
            id: repliesBar
            property string token: meet.current
            visible: pane.replies.length > 0 && pane.room.canPost !== false
            Layout.fillWidth: true
            Layout.leftMargin: pane.compact ? 8 : 16; Layout.rightMargin: 16; Layout.bottomMargin: 6
            spacing: 6
            Icon { name: "ornis"; size: 16; color: pane.c.famCommunicate; height: 30 }
            Repeater {
                model: pane.replies
                AbstractButton {
                    id: reply
                    required property string modelData
                    implicitHeight: 30
                    implicitWidth: Math.min(320, replyText.implicitWidth + 24)
                    hoverEnabled: true
                    onClicked: { composer.insertText(modelData); pane.replies = [] }
                    background: Rectangle { radius: 15; color: reply.hovered ? pane.c.tint : pane.c.card; border.width: 1; border.color: pane.c.accentLine }
                    contentItem: Text { textFormat: Text.PlainText; id: replyText; text: reply.modelData; elide: Text.ElideRight; font.pixelSize: 13; color: pane.c.tintText; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
            OButton { kind: "quiet"; iconName: "close"; height_: 30; tip: app.t.close; onClicked: pane.replies = [] }
        }

        Composer {
            id: composer
            Layout.fillWidth: true
            visible: pane.room.canPost !== false
            compact: pane.compact
            onLaterWanted: text => pane.laterWanted(text)
            onSuggestWanted: pane.suggest()
            onCommand: (id, arg) => pane.runCommand(id, arg)
            suggesting: pane.repliesRequest >= 0 && pane.replies.length === 0 && ornis.busy
        }
        Rectangle {
            visible: pane.room.canPost === false
            Layout.fillWidth: true
            implicitHeight: 48
            color: pane.c.chrome
            Text { anchors.centerIn: parent; text: app.t.read_only; color: pane.c.muted; font.pixelSize: 13 }
        }
    }

    // the commands of the composer that act on the conversation
    function runCommand(id, arg) {
        if (id === "call") pane.callWanted(false)
        else if (id === "video") pane.callWanted(true)
        else if (id === "meeting") pane.planWanted()
        else if (id === "summary" || id === "minutes" || id === "tasks") pane.askOrnis(id)
        else if (id === "ask") { if (arg) { pane.openAsk(); question.text = arg; pane.askOrnis("ask", { question: arg }) } else pane.openAsk() }
        else if (id === "search") { pane.openSearch(); searchField.text = arg }
    }

    // files dropped anywhere on the conversation wait above the field; a note, a task, a mail: its link
    DropArea {
        anchors.fill: parent
        enabled: pane.room.canPost !== false && !!meet.current
        keys: ["text/uri-list", "application/x-orneos-link"]
        onDropped: drop => {
            if (drop.formats.indexOf("application/x-orneos-link") >= 0) {
                let items = []
                try { items = JSON.parse(drop.getDataAsString("application/x-orneos-link")) } catch (e) {}
                composer.insertLinks(items)
            } else if (drop.hasUrls) {
                composer.addFiles(drop.urls.map(u => String(u)))
            }
            drop.accept()
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 10
            visible: parent.containsDrag
            radius: 14
            color: Qt.alpha(pane.c.action, 0.08)
            border.width: 2; border.color: pane.c.action
            Column {
                anchors.centerIn: parent
                spacing: 8
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "clip"; size: 32; color: pane.c.action }
                Text { textFormat: Text.PlainText; text: app.t.drop_here.replace("%1", pane.room.name || ""); font.pixelSize: 16; font.weight: Font.DemiBold; color: pane.c.action }
            }
        }
    }

    ImageViewer { id: viewer; objectName: "imageViewer" }

    // « Transférer » a message: its text (and its files, shared again) to another conversation
    ODialog {
        id: forward
        property var message: null
        property string query: ""
        function start(m) { message = m; query = ""; forwardSearch.text = ""; open() }
        title: app.t.forward
        tint: pane.c.famCommunicate
        onOpened: forwardSearch.forceActiveFocus()
        OTextField { id: forwardSearch; Layout.fillWidth: true; Layout.preferredWidth: 380; iconName: "search"; placeholderText: app.t.search_conversations; onTextChanged: forward.query = text.toLowerCase() }
        ListView {
            Layout.fillWidth: true
            Layout.preferredHeight: 300
            clip: true
            model: meet.allRooms.filter(r => r.canPost !== false && (!forward.query || String(r.name).toLowerCase().indexOf(forward.query) >= 0))
            delegate: AbstractButton {
                id: target
                required property var modelData
                width: ListView.view.width
                implicitHeight: 48
                hoverEnabled: true
                onClicked: { meet.forward(forward.message.id, modelData.token); forward.close() }
                background: Rectangle { radius: 8; color: target.hovered ? pane.c.hover : "transparent" }
                contentItem: RowLayout {
                    spacing: 10
                    RoomAvatar { Layout.leftMargin: 6; room: target.modelData; size: 32 }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: target.modelData.name; elide: Text.ElideRight; font.pixelSize: 14; color: pane.c.text }
                }
            }
        }
        footer: [OButton { text: app.t.cancel; onClicked: forward.close() }]
    }

    // « Créer un fil » on a message: a new thread that quotes it (Talk starts threads with a new message only)
    ODialog {
        id: threadFrom
        property var message: null
        function start(m) { message = m; threadFromTitle.text = String(m.plain || "").split("\n")[0].slice(0, 60); open() }
        title: app.t.thread_from
        tint: pane.c.famCommunicate
        onOpened: { threadFromTitle.forceActiveFocus(); threadFromTitle.selectAll() }
        Text { Layout.fillWidth: true; Layout.preferredWidth: 380; text: app.t.thread_from_lead; wrapMode: Text.WordWrap; font.pixelSize: 13; color: pane.c.muted }
        OTextField { id: threadFromTitle; Layout.fillWidth: true; placeholderText: app.t.thread_title; onAccepted: threadFromGo.clicked() }
        footer: [
            OButton { text: app.t.cancel; onClicked: threadFrom.close() },
            OButton { id: threadFromGo; kind: "primary"; text: app.t.create
                      onClicked: { meet.threadFrom(threadFrom.message.id, threadFromTitle.text); threadFrom.close() } }
        ]
    }

    function sendToNotes() {
        const title = (pane.ornisKind === "minutes" ? app.t.minutes_note : app.t.summary_note).replace("%1", pane.room.name || "")
            .replace("%2", app.day(Math.round(Date.now() / 1000)))
        const body = pane.ornisText + "\n\n[" + (pane.room.name || "Meet") + "](" + (pane.room.link || "") + ")"
        if (app.toNotes(title, body)) app.toast(app.t.sent_to_notes)
        else app.toast(app.t.notes_unavailable)
    }

    MeetMenu {
        id: ornisMenu
        heading: "Ornis"
        OMenuItem { text: app.t.summarize; iconName: "ornis"; onTriggered: pane.askOrnis("summary") }
        OMenuItem { text: app.t.write_minutes; iconName: "note"; onTriggered: pane.askOrnis("minutes") }
        OMenuItem { text: app.t.find_tasks; iconName: "checklist"; onTriggered: pane.askOrnis("tasks") }
        OMenuItem { text: app.t.ask_conversation; iconName: "chat"; onTriggered: pane.openAsk() }
        OMenuItem { text: app.t.suggest_replies; iconName: "sparkle"; enabled: pane.room.canPost !== false; onTriggered: pane.suggest() }
    }
    // a group's other tabs, over the chat below the tabs (the chat keeps its place underneath)
    FilesPane {
        id: filesPane
        visible: pane.shownTab === "shared"
        x: 0; y: tabsBar.y + tabsBar.height
        width: pane.width; height: pane.height - y
        onShownInChat: id => { pane.tab = "chat"; meet.jumpTo(id) }
    }
    PeoplePane {
        id: peoplePane
        visible: pane.shownTab === "people"
        x: 0; y: tabsBar.y + tabsBar.height
        width: pane.width; height: pane.height - y
    }

    MeetMenu {
        id: moreMenu
        OMenuItem { text: app.t.plan_this_meeting; iconName: "calendar"; visible: pane.room.type !== 6; onTriggered: pane.planWanted() }
        OMenuItem { text: app.t.send_later; iconName: "clock"; visible: pane.room.canPost !== false; onTriggered: pane.laterWanted("") }
        OMenuItem { text: app.t.breakout_rooms; iconName: "grid"; visible: !!pane.room.moderator && pane.room.type !== 1 && pane.room.type !== 6 || (pane.room.breakoutMode || 0) > 0 || !!pane.room.breakout; onTriggered: pane.breakoutWanted() }
        OMenuItem { text: app.t.threads; iconName: "chat"; visible: (pane.extras.threads || []).length > 0; onTriggered: threadsMenu.popupAt(moreButton, true) }
        OMenuItem { text: app.t.mark_unread; iconName: "inbox"; onTriggered: meet.markUnread() }
        OMenuItem { text: app.t.copy_link; iconName: "link"; onTriggered: { app.copy(pane.room.link); app.toast(app.t.link_copied) } }
        OMenuItem { text: app.t.settings_conversation; iconName: "settings"; onTriggered: pane.roomSettingsWanted() }
    }
    MeetMenu {
        id: threadsMenu
        heading: app.t.threads
        Repeater {
            model: pane.extras.threads || []
            OMenuItem {
                required property var modelData
                text: modelData.title + "  · " + app.plural("replies_count", modelData.replies)
                iconName: "chat"
                onTriggered: meet.openThread(modelData.id, modelData.title)
            }
        }
    }
}
