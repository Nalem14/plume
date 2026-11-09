// A group of bots: one room, several bots and the person, as a messaging app (bubbles, faces, « is typing »).
// Each bot answers from its own durable conversation (its SOUL, memory, skills); the room is the shared journal
// (ornis_bots groups, delivered by ornis_core/bots.py). @name hands a message to a member; otherwise the lead answers,
// or everyone (the group's setting).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: view
    readonly property var c: theme.c
    readonly property var g: bots.group
    readonly property int column: Math.min(width - 48, 760)
    property bool stick: true
    signal editRequested(string id)
    signal botRequested(string id)

    function toEnd() { list.positionViewAtEnd() }
    function send() {
        const text = input.text.trim()
        if (!text) return
        if (bots.postGroup(text)) { input.text = ""; view.stick = true; Qt.callLater(view.toEnd) }
    }
    // « @ »: the members whose id or name starts with what follows it
    property var mentionRows: []
    property int mentionAt: -1
    function updateMention() {
        const before = input.text.slice(0, input.cursorPosition)
        const m = before.match(/(^|\s)@([\wÀ-ſ-]*)$/)
        if (!m) { mentionPopup.close(); mentionAt = -1; return }
        const q = m[2].toLowerCase()
        mentionAt = input.cursorPosition - m[2].length - 1
        mentionRows = (view.g.people || []).filter(p => !q || p.id.indexOf(q) === 0 || p.title.toLowerCase().indexOf(q) === 0)
        if (mentionRows.length) {
            const at = input.mapToItem(view, 0, 0)
            mentionPopup.x = at.x
            mentionPopup.y = at.y - mentionPopup.implicitHeight - 8
            mentionPopup.open()
        } else mentionPopup.close()
    }
    function applyMention(p) {
        const end = input.cursorPosition
        input.remove(mentionAt, end)
        input.insert(mentionAt, "@" + p.id + " ")
        mentionPopup.close()
        input.forceActiveFocus()
    }

    Rectangle { anchors.fill: parent; color: view.c.bg }
    // Where to stand when a room opens: the « Non lu » bar, else where you left it (scrolled up), else the end
    property string placedFor: ""
    function place() {
        if (!view.g.id || view.placedFor === view.g.id || list.count === 0 && bots.groupMessages.length > 0) return
        view.placedFor = view.g.id
        const at = bots.groupFirstUnread >= 0 ? bots.groupFirstUnread : bots.groupAnchor
        if (at >= 0) { view.stick = false; list.positionViewAtIndex(at, ListView.Beginning) }
        else { view.stick = true; view.toEnd() }
    }
    // the top reached: the page before comes in above, and the view stays on the same message
    property bool loadingOlder: false
    function loadOlder() {
        if (view.loadingOlder || !bots.groupHasMore) return
        view.loadingOlder = true
        const n = bots.loadOlderGroup()
        if (n > 0) list.positionViewAtIndex(n, ListView.Beginning)
        view.loadingOlder = false
    }
    function saveAnchor() {
        if (list.atYEnd) { bots.setGroupAnchor(""); return }
        const i = list.indexAt(10, list.contentY + 10)
        const rows = bots.groupMessages
        if (i >= 0 && i < rows.length) bots.setGroupAnchor(rows[i].id)
    }
    Connections {
        target: bots
        function onChanged() {
            if (view.placedFor !== view.g.id) Qt.callLater(view.place)
            else if (view.stick) Qt.callLater(view.toEnd)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- the head: the members' faces, the name, who is there --------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 60
            color: view.c.bg
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: view.c.hairline }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 12
                spacing: 12
                FaceStack { faces: (view.g.people || []).map(p => p.face); size: 26 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        Layout.fillWidth: true
                        text: view.g.title || ""
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                        color: view.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: bots.typing.length
                              ? app.t.groups_typing.replace("%1", bots.typing.map(t => t.title).join(", "))
                              : (view.g.people || []).map(p => p.title + (p.lead && view.g.reply === "lead" ? " (" + app.t.groups_lead.toLowerCase() + ")" : "")).join(" · ")
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        font.italic: bots.typing.length > 0
                        color: bots.typing.length ? view.c.accent : view.c.muted
                    }
                }
                OButton {                          // the shared folder: where they work on the same files
                    kind: "quiet"; iconName: "folder"; iconSize: 17; height_: 32
                    tip: app.t.groups_folder_open + (view.g.folder ? " — " + view.g.folder : "")
                    onClicked: if (view.g.folder) app.openFolder(view.g.folder)
                }
                OButton {
                    kind: "quiet"; iconName: "settings"; iconSize: 17; height_: 32
                    tip: app.t.groups_edit
                    onClicked: view.editRequested(view.g.id)
                }
            }
        }

        // ---- the room ------------------------------------------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {                         // empty room: who is here and how to talk to them
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 460)
                visible: list.count === 0
                spacing: 12
                FaceStack { Layout.alignment: Qt.AlignHCenter; faces: (view.g.people || []).map(p => p.face); size: 44 }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: view.g.description || app.t.groups_empty
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; color: view.c.text
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: app.t.groups_how
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: view.c.muted
                }
            }

            ListView {
                id: list
                anchors.fill: parent
                clip: true
                model: bots.groupMessages
                spacing: 2
                topMargin: 18; bottomMargin: 12
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                onMovementStarted: view.stick = false
                onMovementEnded: view.saveAnchor()
                onAtYEndChanged: if (atYEnd) { view.stick = true; if (view.placedFor === view.g.id) bots.setGroupAnchor("") }
                onAtYBeginningChanged: if (atYBeginning && view.placedFor === view.g.id && count > 0) Qt.callLater(view.loadOlder)
                header: Item {                     // older messages are there: a hint at the top (they load when reached)
                    width: list.width
                    height: bots.groupHasMore ? 30 : 0
                    visible: bots.groupHasMore
                    Text { anchors.centerIn: parent; text: app.t.groups_older; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: view.c.faint }
                }
                WheelHandler { target: null; blocking: false; onWheel: ev => { if (ev.angleDelta.y > 0) view.stick = false } }
                onCountChanged: if (view.stick) Qt.callLater(view.toEnd)
                delegate: Item {
                    id: row
                    required property var modelData
                    width: list.width
                    implicitHeight: col.implicitHeight + (modelData.first ? 10 : 0)
                    ColumnLayout {
                        id: col
                        x: (list.width - view.column) / 2; width: view.column
                        y: row.modelData.first ? 10 : 0
                        spacing: 4
                        RowLayout {                // what came since your last visit (as Slack's « Nouveau »)
                            visible: !!row.modelData.unreadStart
                            Layout.fillWidth: true
                            Layout.topMargin: 6; Layout.bottomMargin: 6
                            spacing: 10
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.danger }
                            Text { text: app.t.unread_bar; font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                   font.capitalization: Font.AllUppercase; font.letterSpacing: 0.6; color: view.c.danger }
                        }
                        RowLayout {                // a new day
                            visible: row.modelData.day !== ""
                            Layout.fillWidth: true
                            Layout.topMargin: 6; Layout.bottomMargin: 8
                            spacing: 10
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.hairline }
                            Text { text: row.modelData.day; font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                   font.capitalization: Font.AllUppercase; font.letterSpacing: 0.6; color: view.c.faint }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.hairline }
                        }
                        Text {                     // a line from Ornis (a bot could not answer): centred, quiet
                            visible: !!row.modelData.system
                            Layout.fillWidth: true
                            Layout.topMargin: 4; Layout.bottomMargin: 4
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            text: row.modelData.text || ""
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
                            color: view.c.muted
                        }
                        Bubble {
                            visible: !row.modelData.system
                            Layout.fillWidth: true
                            entry: row.modelData
                            maxWidth: view.column * 0.78
                            onFaceClicked: id => view.botRequested(id)
                        }
                    }
                }
            }
            AbstractButton {                       // back to the bottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom; anchors.bottomMargin: 10
                implicitWidth: 34; implicitHeight: 34
                visible: list.count > 0 && !list.atYEnd && list.contentHeight > list.height
                onClicked: { view.stick = true; view.toEnd() }
                Accessible.name: app.t.to_bottom || ""
                background: Rectangle { radius: 17; color: view.c.card; border.color: view.c.line }
                contentItem: Item { Icon { anchors.centerIn: parent; name: "chevronDown"; size: 16; color: view.c.text } }
            }
        }

        // « Orla écrit… »: the bots answering now, as typing bubbles under the last message
        Repeater {
            model: bots.typing
            Item {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: 40
                RowLayout {
                    x: (parent.width - view.column) / 2; width: view.column
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    BotFace { face: modelData.face; size: 28; busy: true }
                    TypingDots { }
                    Text { text: app.t.bots_status_writing.replace("%1", modelData.title)
                           font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true; color: view.c.muted }
                    Item { Layout.fillWidth: true }
                }
            }
        }

        // ---- the message box -----------------------------------------------------------------------------------
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: view.column
            Layout.bottomMargin: 16; Layout.topMargin: 6
            implicitHeight: Math.min(200, Math.max(44, input.implicitHeight)) + 50
            radius: 16
            color: view.c.card
            border.width: input.activeFocus ? 2 : 1
            border.color: input.activeFocus ? view.c.action : view.c.line
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    TextArea {
                        id: input
                        placeholderText: app.t.groups_placeholder.replace("%1", view.g.title || "")
                        wrapMode: TextArea.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: app.textSize
                        color: view.c.text
                        placeholderTextColor: view.c.faint
                        leftPadding: 16; rightPadding: 16; topPadding: 12
                        background: null
                        onTextChanged: view.updateMention()
                        onCursorPositionChanged: if (mentionPopup.opened) view.updateMention()
                        Keys.onPressed: event => {
                            if (mentionPopup.opened && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Tab)) {
                                if (view.mentionRows.length) view.applyMention(view.mentionRows[0])
                                event.accepted = true
                            } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                view.send(); event.accepted = true
                            } else if (event.key === Qt.Key_Escape && mentionPopup.opened) {
                                mentionPopup.close(); event.accepted = true
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.bottomMargin: 6
                    spacing: 4
                    AbstractButton {            // « @ »: name who should answer
                        id: atBtn
                        implicitWidth: 30; implicitHeight: 32
                        hoverEnabled: true
                        onClicked: { input.insert(input.cursorPosition, (input.cursorPosition > 0 && !/\s$/.test(input.text.slice(0, input.cursorPosition)) ? " @" : "@")); input.forceActiveFocus() }
                        Accessible.name: app.t.groups_mention_tip
                        ToolTip.text: app.t.groups_mention_tip; ToolTip.delay: 500; ToolTip.visible: hovered
                        background: Rectangle { radius: 14; color: atBtn.hovered ? view.c.hover : "transparent" }
                        contentItem: Text { horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: "@"
                                            font.family: "JetBrains Mono"; font.pixelSize: 15; font.weight: Font.DemiBold
                                            color: atBtn.hovered ? view.c.text : view.c.muted }
                    }
                    Repeater {                  // one click on a face: write to that member
                        model: view.g.people || []
                        AbstractButton {
                            id: faceBtn
                            required property var modelData
                            implicitWidth: 28; implicitHeight: 32
                            hoverEnabled: true
                            onClicked: { input.insert(input.cursorPosition, (input.cursorPosition > 0 && !/\s$/.test(input.text.slice(0, input.cursorPosition)) ? " " : "") + "@" + modelData.id + " "); input.forceActiveFocus() }
                            Accessible.name: "@" + modelData.title
                            ToolTip.text: modelData.title + (modelData.description ? " — " + modelData.description : ""); ToolTip.delay: 400; ToolTip.visible: hovered
                            contentItem: Item { BotFace { anchors.centerIn: parent; face: faceBtn.modelData.face; size: faceBtn.hovered ? 22 : 20; busy: faceBtn.modelData.typing } }
                            background: null
                        }
                    }
                    Item { Layout.fillWidth: true }
                    ToolbarChip {               // who answers a message that names nobody (the same chip as the modes)
                        iconName: view.g.reply === "all" ? "people" : "user"
                        label: view.g.reply === "all" ? app.t.groups_reply_all : app.t.groups_reply_lead
                        tone: view.g.reply === "all" ? "tint" : "plain"
                        showLabel: view.width >= 560
                        tip: view.g.reply === "all" ? app.t.groups_reply_all_sub : app.t.groups_reply_lead_sub
                        onClicked: bots.updateGroup(view.g.id, { reply: view.g.reply === "all" ? "lead" : "all" })
                        chevron: false
                    }
                    AbstractButton {            // dictation (the same recorder as Code and the Discussions)
                        id: groupMic
                        readonly property var v: chat.voice
                        visible: v.available
                        implicitWidth: 32; implicitHeight: 32
                        hoverEnabled: true
                        enabled: !v.busy
                        onClicked: v.toggle()
                        Accessible.name: v.recording ? app.t.dictate_stop : app.t.dictate
                        ToolTip.text: Accessible.name; ToolTip.delay: 450; ToolTip.visible: hovered
                        background: Rectangle { radius: 16; color: groupMic.v.recording ? view.c.danger : groupMic.hovered ? view.c.hover : "transparent" }
                        contentItem: Item {
                            Rectangle { visible: groupMic.v.recording; anchors.centerIn: parent; width: 10; height: 10; radius: 2; color: "white" }
                            Icon { visible: !groupMic.v.recording; anchors.centerIn: parent; name: "mic"; size: 18
                                   color: groupMic.hovered ? view.c.text : view.c.muted }
                        }
                    }
                    AbstractButton {            // send, or while bots answer, stop them
                        id: action
                        readonly property bool working: bots.typing.length > 0
                        implicitWidth: 34; implicitHeight: 34
                        hoverEnabled: true
                        enabled: working || input.text.trim() !== ""
                        onClicked: working && input.text.trim() === "" ? bots.stopGroup() : view.send()
                        Accessible.name: working && input.text.trim() === "" ? app.t.stop : app.t.send
                        ToolTip.text: Accessible.name; ToolTip.delay: 450; ToolTip.visible: hovered
                        background: Rectangle { radius: 17
                            color: action.working && input.text.trim() === "" ? view.c.text : action.enabled ? view.c.famCommunicate : view.c.hover }
                        contentItem: Item {
                            Rectangle { visible: action.working && input.text.trim() === ""; anchors.centerIn: parent; width: 11; height: 11; radius: 2; color: view.c.bg }
                            Icon { visible: !(action.working && input.text.trim() === ""); anchors.centerIn: parent; name: "send"; size: 16
                                   color: action.enabled ? "white" : view.c.muted }
                        }
                    }
                }
            }
        }
    }

    // Échap: the bots answering stop (as Code and the Discussions)
    Shortcut { sequence: "Esc"; enabled: view.visible && bots.typing.length > 0 && !mentionPopup.opened; onActivated: bots.stopGroup() }
    Connections {                           // dictation: what is said comes into the box
        target: chat.voice
        function onText(said) { if (view.visible) { input.insert(input.cursorPosition, said); input.forceActiveFocus() } }
    }

    Popup {
        id: mentionPopup
        padding: 4
        implicitWidth: 260
        implicitHeight: Math.min(240, mentionList.contentHeight + 8)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        focus: false
        background: Rectangle { radius: 10; color: view.c.card; border.color: view.c.line }
        ListView {
            id: mentionList
            anchors.fill: parent
            clip: true
            model: view.mentionRows
            delegate: AbstractButton {
                id: mrow
                required property var modelData
                width: mentionList.width; implicitHeight: 36
                hoverEnabled: true
                onClicked: view.applyMention(modelData)
                background: Rectangle { radius: 7; color: mrow.hovered ? view.c.hover : "transparent" }
                contentItem: RowLayout {
                    spacing: 8
                    Item { implicitWidth: 2 }
                    BotFace { face: mrow.modelData.face; size: 20 }
                    Text { text: mrow.modelData.title; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: view.c.text }
                    Text { Layout.fillWidth: true; text: "@" + mrow.modelData.id; elide: Text.ElideRight
                           font.family: "JetBrains Mono"; font.pixelSize: 11; color: view.c.muted }
                }
            }
        }
    }

    // ---- pieces ------------------------------------------------------------------------------------------------
    // A few faces overlapping (a group's avatar)
    component FaceStack: Item {
        id: fs
        property var faces: []
        property int size: 26
        readonly property int shown: Math.min(4, faces.length)
        implicitWidth: shown ? size + (shown - 1) * size * 0.55 : size
        implicitHeight: size
        Repeater {
            model: fs.faces.slice(0, 4)
            Rectangle {
                required property var modelData
                required property int index
                x: index * fs.size * 0.55
                width: fs.size; height: fs.size; radius: fs.size / 2
                color: theme.c.bg
                z: 10 - index
                BotFace { anchors.centerIn: parent; face: modelData; size: fs.size - 4 }
            }
        }
    }
    // Three dots that breathe: someone is writing
    component TypingDots: Rectangle {
        implicitWidth: 46; implicitHeight: 26; radius: 13
        color: theme.c.field
        border.width: 1; border.color: theme.c.line
        Row {
            anchors.centerIn: parent
            spacing: 4
            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    width: 6; height: 6; radius: 3
                    color: theme.c.muted
                    SequentialAnimation on opacity {
                        running: Qt.styleHints.reduceMotion !== true
                        loops: Animation.Infinite
                        PauseAnimation { duration: index * 160 }
                        NumberAnimation { from: 0.3; to: 1; duration: 320 }
                        NumberAnimation { from: 1; to: 0.3; duration: 320 }
                        PauseAnimation { duration: (2 - index) * 160 }
                    }
                }
            }
        }
    }
    // One message: mine on the right (tinted), a bot's on the left with its face and name at the start of a run
    component Bubble: Item {
        id: b
        property var entry: ({})
        property real maxWidth: 400
        signal faceClicked(string id)
        readonly property bool mine: !!entry.mine
        implicitHeight: Math.max(bubbleBox.height + (nameText.visible ? nameText.implicitHeight + 3 : 0)
                                 + (timeText.visible ? timeText.implicitHeight + 2 : 0), 10)
        Text {
            id: nameText
            visible: !b.mine && !!b.entry.first
            x: 40
            text: b.entry.title || ""
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            color: (b.entry.face && b.entry.face.color) || theme.c.muted
        }
        AbstractButton {
            visible: !b.mine && !!b.entry.last
            x: 0; y: bubbleBox.y + bubbleBox.height - 30
            width: 30; height: 30
            onClicked: b.faceClicked(b.entry.from)
            Accessible.name: b.entry.title || ""
            background: null
            contentItem: BotFace { face: b.entry.face; size: 30 }
        }
        Rectangle {
            id: bubbleBox
            x: b.mine ? b.width - width : 40
            y: nameText.visible ? nameText.implicitHeight + 3 : 0
            width: Math.min(Math.ceil(measure.implicitWidth) + 30, b.maxWidth)
            height: body.implicitHeight + 18
            // the corner next to the face (or the right edge for mine) is tighter: a speech bubble
            radius: 16
            color: b.mine ? theme.c.tint : theme.c.card
            border.width: b.mine ? 0 : 1
            border.color: theme.c.line
            Rectangle {                       // the tail corner
                visible: !!b.entry.last
                width: 16; height: 16
                color: parent.color
                border.width: 0
                anchors.bottom: parent.bottom
                anchors.left: b.mine ? undefined : parent.left
                anchors.right: b.mine ? parent.right : undefined
                radius: 4
                z: -1
            }
            // the text on one line without the Markdown marks, to fit a short message (**gras** is not wider)
            Text { id: measure; visible: false; text: String(b.entry.text || "").replace(/[*_`#>]/g, ""); textFormat: Text.PlainText; font: body.font }
            TextEdit {
                id: body
                anchors.fill: parent; anchors.margins: 9; anchors.leftMargin: 15; anchors.rightMargin: 15
                readOnly: true; selectByMouse: true
                textFormat: b.mine ? TextEdit.PlainText : TextEdit.RichText
                text: b.mine ? (b.entry.text || "") : app.markdown(b.entry.text || "", theme.c.accent, app.textSize, theme.c.line, theme.c.field)
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: app.textSize
                color: theme.c.text
                selectionColor: theme.c.accentLine
                onLinkActivated: link => app.openLink(link)
            }
        }
        Text {
            id: timeText
            visible: !!b.entry.last
            anchors.top: bubbleBox.bottom; anchors.topMargin: 2
            x: b.mine ? b.width - implicitWidth - 4 : 44
            text: b.entry.time || ""
            font.family: "Schibsted Grotesk"; font.pixelSize: 11
            color: theme.c.faint
        }
        HoverHandler { id: hov }
        OButton {
            visible: hov.hovered
            anchors.verticalCenter: bubbleBox.verticalCenter
            x: b.mine ? bubbleBox.x - width - 4 : bubbleBox.x + bubbleBox.width + 4
            kind: "quiet"; iconName: "copy"; iconSize: 14; height_: 26; tip: app.t.copy
            onClicked: app.copy(b.entry.text || "")
        }
    }
}
