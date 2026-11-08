// Writing in the conversation, on a card that floats above the bottom: the text (Markdown as in Talk, Ctrl+B and
// Ctrl+I), @ for a person of the conversation, « : » for an emoji (« :fete »), « / » for a command (/gif,
// /sondage, /appel, /resumer…), emojis, GIFs (Giphy through the cloud), files (the button, pasted, dropped on
// the conversation: they wait above the field and leave with the text as their caption), a note, a task or a
// mail dropped from its app (its link), a poll, a voice message (the microphone, while the field is empty),
// « Envoyer plus tard », « Envoyer sans notifier » (for the next message); « Répondre » and « Modifier » show
// above the field. The others see that we write. « :) », « <3 »… become their emoji when the message leaves.
// The draft stays with each conversation (offline too). Entrée sends (Maj+Entrée: a new line), or Ctrl+Entrée
// in the settings.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"
import "emoji.js" as Emoji

Rectangle {
    id: composer
    readonly property var c: theme.c
    readonly property bool typing: field.activeFocus
    property bool compact: false
    property var reply: null
    property var editing: null
    property string token: meet.current
    property bool suggesting: false
    property var attachments: []          // files waiting to leave with the message: fileInfo maps
    property bool silent: false           // the next message leaves without notifying anyone
    readonly property bool pollsAllowed: meet.room.type === 2 || meet.room.type === 3   // Talk: group and public only
    signal laterWanted(string text)
    signal suggestWanted()
    signal command(string id, string arg)
    color: "transparent"
    implicitHeight: column.implicitHeight + 24

    function insertText(text) { field.text = text; focusText(); field.cursorPosition = field.length }

    function focusText() { field.forceActiveFocus() }
    function replyTo(message) { editing = null; reply = message; focusText() }
    function edit(message) { reply = null; editing = message; field.text = message.plain; focusText(); field.cursorPosition = field.length }
    function addFiles(links) {
        const list = attachments.slice()
        for (const link of links) {
            const info = meet.fileInfo(String(link))
            if (info.url && !list.some(a => a.url === info.url)) list.push(info)
        }
        attachments = list
        focusText()
    }
    function insertLinks(items) {
        const text = items.filter(i => i && i.url).map(i => "[" + (i.title || i.url) + "](" + i.url + ")").join("\n")
        if (text) { field.insert(field.cursorPosition, (field.text && !field.text.endsWith("\n") ? " " : "") + text); focusText() }
    }
    function wrap(mark) {
        const a = field.selectionStart, b = field.selectionEnd
        const inside = field.text.slice(a, b)
        field.remove(a, b)
        field.insert(a, mark + inside + mark)
        if (a === b) field.cursorPosition = a + mark.length
    }
    function send() {
        let text = field.text.trim()
        if (!text && !attachments.length) return
        if (!editing && !attachments.length && commands.run(text)) return
        text = Emoji.emoticons(text)
        if (editing) meet.edit(editing.id, text)
        else if (attachments.length) { meet.sendFiles(attachments.map(a => a.url), text, reply ? reply.id : 0); attachments = [] }
        else meet.send(text, reply ? reply.id : 0, silent)
        silent = false
        field.text = ""
        reply = null
        editing = null
        mentions.close()
        typingStop.stop()
        meet.setTyping(false)
    }

    // the draft of each conversation
    property string draftToken: ""
    Component.onCompleted: draftToken = token
    onTokenChanged: {
        // the last keys of the conversation left, not yet written: to its draft, not to the new one
        if (draftTimer.running && !editing && draftToken) {
            draftTimer.stop()
            meet.saveDraft(field.text, reply ? reply.id : 0, draftToken)
        }
        draftToken = token
        reply = null; editing = null; attachments = []; silent = false
        field.text = meet.room.draft || ""
    }
    Timer { id: draftTimer; interval: 600; onTriggered: if (!composer.editing) meet.saveDraft(field.text, composer.reply ? composer.reply.id : 0) }
    // « … écrit » for the others: on while keys come, off 4 s after the last one (or when sent)
    Timer { id: typingStop; interval: 4000; onTriggered: meet.setTyping(false) }

    // the floating card
    Surface {
        x: column.x - 8; y: column.y - 8
        width: column.width + 16; height: column.height + 16
        radius: 14
    }

    ColumnLayout {
        id: column
        x: composer.compact ? 14 : 24
        y: 12
        width: parent.width - 2 * x
        spacing: 8

        // answering / editing
        Rectangle {
            visible: composer.reply !== null || composer.editing !== null
            Layout.fillWidth: true
            implicitHeight: 44
            radius: 8
            color: composer.c.card
            border.width: 1; border.color: composer.c.hairline
            Rectangle { x: 6; y: 6; width: 3; height: parent.height - 12; radius: 1.5; color: composer.editing ? composer.c.saffron : composer.c.action }
            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 16; anchors.rightMargin: 40
                spacing: 0
                Text { textFormat: Text.PlainText;
                    Layout.fillWidth: true
                    text: composer.editing ? app.t.editing : app.t.replying_to.replace("%1", composer.reply ? composer.reply.name : "")
                    font.pixelSize: 12; font.weight: Font.DemiBold
                    color: composer.editing ? composer.c.saffronInk : composer.c.action
                }
                Text {
                    Layout.fillWidth: true
                    text: composer.reply ? composer.reply.plain : (composer.editing ? composer.editing.plain : "")
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                    font.pixelSize: 12; color: composer.c.muted
                }
            }
            OButton {
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; anchors.rightMargin: 4
                kind: "quiet"; iconName: "close"; height_: 28; tip: app.t.cancel
                onClicked: { if (composer.editing) field.text = ""; composer.reply = null; composer.editing = null }
            }
        }

        // « sans notifier » chosen for the next message
        Rectangle {
            visible: composer.silent
            Layout.preferredHeight: 28
            Layout.preferredWidth: silentRow.implicitWidth + 40
            radius: 14
            color: composer.c.saffronTint
            Row {
                id: silentRow
                x: 10; anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                Icon { name: "bell"; size: 13; color: composer.c.saffronInk; anchors.verticalCenter: parent.verticalCenter }
                Text { text: app.t.silent_next; font.pixelSize: 12; font.weight: Font.DemiBold; color: composer.c.saffronInk; anchors.verticalCenter: parent.verticalCenter }
            }
            AbstractButton {
                anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                width: 18; height: 18
                Accessible.name: app.t.cancel
                onClicked: composer.silent = false
                contentItem: Icon { name: "close"; size: 12; color: composer.c.saffronInk }
            }
        }

        // the files waiting to leave: a picture shows, the others by name; × takes one back
        Flow {
            visible: composer.attachments.length > 0
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: composer.attachments
                Rectangle {
                    id: chip
                    required property var modelData
                    required property int index
                    width: modelData.image ? 84 : Math.min(240, chipRow.implicitWidth + 44)
                    height: modelData.image ? 84 : 44
                    radius: 10
                    color: composer.c.card
                    border.width: 1; border.color: composer.c.hairline
                    clip: true
                    Image {
                        visible: chip.modelData.image
                        anchors.fill: parent; anchors.margins: 1
                        source: chip.modelData.image ? chip.modelData.url : ""
                        sourceSize: Qt.size(168, 168)
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }
                    Row {
                        id: chipRow
                        visible: !chip.modelData.image
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        Icon { name: String(chip.modelData.mime).indexOf("pdf") >= 0 ? "pdf" : "clip"; size: 16; color: composer.c.tintText; anchors.verticalCenter: parent.verticalCenter }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            Text { textFormat: Text.PlainText; text: chip.modelData.name; width: Math.min(implicitWidth, 150); elide: Text.ElideMiddle; font.pixelSize: 12; font.weight: Font.Medium; color: composer.c.text }
                            Text { textFormat: Text.PlainText; text: app.size(chip.modelData.size); font.pixelSize: 11; color: composer.c.muted }
                        }
                    }
                    AbstractButton {
                        anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 4
                        width: 22; height: 22
                        Accessible.name: app.t.remove
                        onClicked: { const l = composer.attachments.slice(); l.splice(chip.index, 1); composer.attachments = l }
                        background: Rectangle { radius: 11; color: Qt.alpha("#0A192F", 0.6) }
                        contentItem: Icon { name: "close"; size: 12; color: "white" }
                    }
                }
            }
        }

        // recording a voice message
        RowLayout {
            visible: voice.recording
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            spacing: 10
            OButton { kind: "quiet"; iconName: "trash"; tip: app.t.cancel; onClicked: voice.finish(false) }
            Rectangle {
                implicitWidth: 10; implicitHeight: 10; radius: 5
                color: composer.c.danger
                SequentialAnimation on opacity { running: voice.recording; loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 600 } NumberAnimation { to: 1; duration: 600 } }
            }
            Text { textFormat: Text.PlainText; text: app.duration(voice.elapsed); font.family: "JetBrains Mono"; font.pixelSize: 15; color: composer.c.text }
            Text { Layout.fillWidth: true; text: app.t.recording; font.pixelSize: 13; color: composer.c.muted; elide: Text.ElideRight }
            OButton { kind: "primary"; iconName: "send"; text: app.t.send; onClicked: voice.finish(true) }
        }

        RowLayout {
            visible: !voice.recording
            Layout.fillWidth: true
            spacing: 6
            OButton {
                id: addButton
                Layout.alignment: Qt.AlignBottom
                kind: "quiet"; iconName: "plus"; tip: app.t.add
                onClicked: addMenu.popupAt(addButton, true)
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: Math.min(180, Math.max(40, field.implicitHeight + 4))
                radius: 10
                color: composer.c.field
                border.width: field.activeFocus ? 2 : 1
                border.color: field.activeFocus ? composer.c.action : composer.c.line
                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 2
                    TextArea {
                        id: field
                        placeholderText: meet.room.name ? app.t.write_to.replace("%1", meet.room.name) : app.t.write
                        placeholderTextColor: composer.c.faint
                        wrapMode: TextArea.Wrap
                        font.pixelSize: 14
                        color: composer.c.text
                        selectionColor: composer.c.tint
                        selectedTextColor: composer.c.text
                        background: null
                        leftPadding: 10; rightPadding: 10; topPadding: 9; bottomPadding: 9
                        onTextChanged: {
                            draftTimer.restart(); mentions.update()
                            if (activeFocus && text !== "" && !composer.editing) { meet.setTyping(true); typingStop.restart() }
                            else if (text === "") { typingStop.stop(); meet.setTyping(false) }
                        }
                        Keys.onPressed: event => {
                            // a picture copied, or files copied in the file manager: attached; text: as usual
                            if (event.matches(StandardKey.Paste)) {
                                const image = meet.clipboardImage()
                                const files = image ? [image] : meet.clipboardFiles()
                                if (files.length) { composer.addFiles(files); event.accepted = true; return }
                            }
                            if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_B) { composer.wrap("**"); event.accepted = true; return }
                            if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_I) { composer.wrap("_"); event.accepted = true; return }
                            if (mentions.opened && (event.key === Qt.Key_Down || event.key === Qt.Key_Up)) {
                                mentions.move(event.key === Qt.Key_Down ? 1 : -1); event.accepted = true; return
                            }
                            if (mentions.opened && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Tab)) {
                                mentions.pick(); event.accepted = true; return
                            }
                            if (event.key === Qt.Key_Escape) {
                                if (mentions.opened) mentions.close()
                                else if (composer.reply || composer.editing) { if (composer.editing) field.text = ""; composer.reply = null; composer.editing = null }
                                event.accepted = true
                                return
                            }
                            if (event.key === Qt.Key_Up && field.text === "") {
                                // the last of ours, to change it (as in Talk)
                                const rows = meet.messages
                                for (let i = rows.rowCount() - 1; i >= 0 && i > rows.rowCount() - 40; i--) {
                                    const m = rows.get(i)
                                    if (m.self && !m.deleted && m.id > 0 && !m.files.length) { composer.edit(m); event.accepted = true; return }
                                }
                            }
                            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                const ctrl = event.modifiers & Qt.ControlModifier
                                const shift = event.modifiers & Qt.ShiftModifier
                                if ((app.prefs.enter_sends && !shift && !ctrl) || (!app.prefs.enter_sends && ctrl)) {
                                    composer.send(); event.accepted = true
                                }
                            }
                        }
                    }
                }
            }
            OButton {
                id: emojiButton
                Layout.alignment: Qt.AlignBottom
                kind: "quiet"; iconName: "smile"; tip: app.t.emoji
                onClicked: emoji.popupAt(emojiButton, true)
            }
            OButton {
                id: gifButton
                Layout.alignment: Qt.AlignBottom
                kind: "quiet"; text: "GIF"; tip: app.t.gif_tip
                onClicked: gifs.show(gifButton, "")
            }
            OButton {
                visible: voice.available && field.text.trim() === "" && !composer.editing && !composer.attachments.length
                Layout.alignment: Qt.AlignBottom
                kind: "quiet"; iconName: "mic"; tip: app.t.voice_message
                onClicked: voice.record()
            }
            OButton {
                visible: !(voice.available && field.text.trim() === "" && !composer.editing && !composer.attachments.length)
                Layout.alignment: Qt.AlignBottom
                kind: "primary"; iconName: composer.editing ? "check" : "send"
                tip: (composer.editing ? app.t.save : app.t.send) + (composer.editing ? "" : " · " + app.t.hold_for_later)
                enabled: field.text.trim() !== "" || composer.attachments.length > 0
                onClicked: composer.send()
                onPressAndHold: if (!composer.editing) { composer.laterWanted(field.text.trim()); field.text = "" }
            }
        }
    }

    EmojiPicker {
        id: emoji
        objectName: "composerEmoji"
        onPicked: e => { field.insert(field.cursorPosition, e); field.forceActiveFocus() }
    }

    MeetMenu {
        id: addMenu
        OMenuItem { text: app.t.share_file; iconName: "clip"; onTriggered: files.open() }
        OMenuItem { text: app.t.new_poll; iconName: "list"; visible: composer.pollsAllowed; onTriggered: pollDialog.start() }
        OMenuItem { text: app.t.send_later; iconName: "clock"; onTriggered: { composer.laterWanted(field.text.trim()); field.text = "" } }
        OMenuItem { text: app.t.suggest_replies; iconName: "ornis"; enabled: !composer.suggesting; onTriggered: composer.suggestWanted() }
        OMenuItem { text: app.t.new_thread; iconName: "chat"; visible: !!meet.room.threads; onTriggered: threadDialog.open() }
        // with a text: it leaves now, silently; without: the next message will (a chip above the field says so)
        OMenuItem { text: app.t.silent_send; iconName: "bell"
                    onTriggered: { if (field.text.trim()) { composer.silent = true; composer.send() } else { composer.silent = true; composer.focusText() } } }
    }

    FileDialog {
        id: files
        fileMode: FileDialog.OpenFiles
        title: app.t.share_file
        onAccepted: composer.addFiles(selectedFiles.map(u => String(u)))
    }

    PollDialog { id: pollDialog }

    GifPicker {
        id: gifs
        onPicked: url => { meet.send(url, composer.reply ? composer.reply.id : 0, false); composer.reply = null; composer.focusText() }
    }

    // a new thread: its title, then the message as its first one
    ODialog {
        id: threadDialog
        title: app.t.new_thread
        tint: composer.c.famCommunicate
        onOpened: {
            threadText.text = field.text.trim()
            threadTitle.text = threadText.text.split("\n")[0].slice(0, 60)
            threadTitle.forceActiveFocus(); threadTitle.selectAll()
        }
        Text { Layout.fillWidth: true; text: app.t.new_thread_lead; wrapMode: Text.WordWrap; font.pixelSize: 13; color: composer.c.muted }
        OTextField { id: threadTitle; Layout.fillWidth: true; placeholderText: app.t.thread_title; onAccepted: threadText.forceActiveFocus() }
        OTextArea { id: threadText; Layout.fillWidth: true; Layout.preferredHeight: 110; placeholderText: app.t.thread_first }
        footer: [
            OButton { text: app.t.cancel; onClicked: threadDialog.close() },
            OButton {
                id: startThread
                kind: "primary"; text: app.t.create
                enabled: threadText.text.trim() !== ""
                onClicked: { meet.startThread(threadTitle.text, Emoji.emoticons(threadText.text.trim()), true); field.text = ""; threadDialog.close() }
            }
        ]
    }

    // the commands: « / » at the start of the field. Their names in French, English and German all work.
    QtObject {
        id: commands
        readonly property var list: [
            { id: "gif", names: ["gif"], arg: true },
            { id: "poll", names: ["sondage", "poll", "umfrage"] },
            { id: "call", names: ["appel", "call", "anruf"] },
            { id: "video", names: ["visio", "video"] },
            { id: "file", names: ["fichier", "file", "datei"] },
            { id: "thread", names: ["fil", "thread"], arg: true },
            { id: "silent", names: ["silencieux", "silent", "leise"], arg: true },
            { id: "later", names: ["plus-tard", "later", "spaeter"], arg: true },
            { id: "meeting", names: ["reunion", "meeting", "besprechung"] },
            { id: "summary", names: ["resumer", "summary", "zusammenfassen"] },
            { id: "minutes", names: ["compte-rendu", "minutes", "protokoll"] },
            { id: "tasks", names: ["taches", "tasks", "aufgaben"] },
            { id: "ask", names: ["ornis", "ask", "fragen"], arg: true },
            { id: "search", names: ["chercher", "search", "suchen"], arg: true },
            { id: "code", names: ["code"] },
            { id: "shrug", names: ["shrug", "bof"], arg: true }
        ]
        function name(c) { return app.t["cmd_" + c.id] }
        function find(word) {
            const w = Emoji.fold(word)
            return list.find(c => c.names.indexOf(w) >= 0 || Emoji.fold(name(c)) === w)
        }
        // what this conversation can do: Talk takes polls in group and public conversations only, threads where it has them
        function usable(c) { return (c.id !== "poll" || composer.pollsAllowed) && (c.id !== "thread" || !!meet.room.threads) }
        function matching(q) {
            q = Emoji.fold(q)
            return list.filter(c => usable(c) && (c.names.some(n => n.indexOf(q) === 0) || Emoji.fold(name(c)).indexOf(q) === 0))
        }
        // the whole text is a command: done, true; anything else (a path, an unknown word) is a message
        function run(text) {
            const m = text.match(/^\/(\S+)(?:\s+([\s\S]*))?$/)
            const c = m ? find(m[1]) : null
            if (!c || !usable(c)) return false
            const arg = (m[2] || "").trim()
            field.text = ""
            if (c.id === "gif") gifs.show(gifButton, arg)
            else if (c.id === "poll") pollDialog.start()
            else if (c.id === "file") files.open()
            else if (c.id === "thread") { field.text = arg; threadDialog.open() }
            else if (c.id === "silent") { composer.silent = true; if (arg) { field.text = arg; composer.send() } }
            else if (c.id === "later") composer.laterWanted(arg)
            else if (c.id === "code") { field.text = "```\n\n```"; field.cursorPosition = 4 }
            else if (c.id === "shrug") { meet.send((arg ? arg + " " : "") + "¯\\_(ツ)_/¯", composer.reply ? composer.reply.id : 0, false); composer.reply = null }
            else composer.command(c.id, arg)
            return true
        }
    }

    // @ the people of the conversation (and « tout le monde »), « : » an emoji, « / » a command
    MeetMenu {
        id: mentions
        property var matches: []
        property string mode: "mention"
        property int chosen: 0
        property int start: -1
        implicitWidth: mode === "command" ? 360 : 264
        y: -implicitHeight - 4          // follows its height: fewer matches, still just above the field
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        focus: false
        function place() {
            chosen = 0
            if (!matches.length) { close(); return }
            const p = field.mapToItem(composer, field.cursorRectangle.x, 0)
            x = Math.max(8, Math.min(p.x, composer.width - implicitWidth - 8))
            if (!opened) open()
        }
        function update() {
            const before = field.text.slice(0, field.cursorPosition)
            const slash = before.match(/^\/(\S{0,20})$/)
            if (slash && !composer.editing) {
                mode = "command"; start = 0
                matches = commands.matching(slash[1]).map(c => ({ command: c }))
                place(); return
            }
            // « : » alone or followed by a word, a face (« :D », « ;) », « <3 »): their emojis
            const word = before.match(/(^|\s)(:[^\s:]{0,24}|[^\s:@\/][^\s]{1,2})$/)
            const faces = word ? Emoji.suggest(word[2], app.prefs.recent_emojis || [], 8) : []
            if (faces.length) {
                mode = "emoji"; start = field.cursorPosition - word[2].length
                matches = faces
                place(); return
            }
            const m = before.match(/(^|\s)@([^\s@]{0,30})$/)
            mode = "mention"
            if (!m) { close(); return }
            start = field.cursorPosition - m[2].length - 1
            const q = m[2].toLowerCase()
            const people = meet.participants.filter(p => !p.self && !p.group && (p.name.toLowerCase().indexOf(q) >= 0 || p.actorId.toLowerCase().indexOf(q) >= 0))
            const all = meet.room.type !== 1 && "all".indexOf(q) === 0 ? [{ actorId: "all", name: app.t.mention_all, actorType: "users", avatar: "" }] : []
            matches = all.concat(people).slice(0, 8)
            place()
        }
        function move(d) { chosen = (chosen + d + matches.length) % matches.length }
        function pick() {
            const p = matches[chosen]
            if (!p) return
            if (mode === "emoji") {
                field.remove(start, field.cursorPosition)
                field.insert(start, p.emoji)
                const recent = app.prefs.recent_emojis || []
                app.setPref("recent_emojis", [p.emoji].concat(recent.filter(r => r !== p.emoji)).slice(0, 16))
                close(); field.forceActiveFocus(); return
            }
            if (mode === "command") {
                close()
                if (p.command.arg) { field.text = "/" + commands.name(p.command) + " "; field.cursorPosition = field.length; field.forceActiveFocus() }
                else commands.run("/" + p.command.names[0])
                return
            }
            // Talk's mention: @id, quoted when it has spaces or is a guest
            const id = p.actorType === "guests" ? "guest/" + p.actorId : p.actorId
            const token = /[\s/]/.test(id) ? '@"' + id + '" ' : "@" + id + " "
            field.remove(start, field.cursorPosition)
            field.insert(start, token)
            close()
            field.forceActiveFocus()
        }
        Repeater {
            model: mentions.matches
            AbstractButton {
                id: who
                required property var modelData
                required property int index
                width: mentions.implicitWidth - 14
                implicitHeight: 40
                hoverEnabled: true
                onClicked: { mentions.chosen = index; mentions.pick() }
                background: Rectangle { radius: 8; color: who.index === mentions.chosen || who.hovered ? composer.c.hover : "transparent" }
                contentItem: RowLayout {
                    spacing: 10
                    RoomAvatar { visible: mentions.mode === "mention"; Layout.leftMargin: 8; size: 26; source: who.modelData.avatar || ""; name: who.modelData.name || "" }
                    Text { visible: mentions.mode === "emoji"; Layout.leftMargin: 8; textFormat: Text.PlainText; text: who.modelData.emoji || ""; font.pixelSize: 20 }
                    Text { visible: mentions.mode === "command"; Layout.leftMargin: 8; textFormat: Text.PlainText; text: who.modelData.command ? "/" + commands.name(who.modelData.command) : ""
                           font.family: "JetBrains Mono"; font.pixelSize: 13; font.weight: Font.Medium; color: composer.c.action }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: mentions.mode === "command" ? 12 : 14
                           color: mentions.mode === "mention" ? composer.c.text : composer.c.muted
                           text: mentions.mode === "mention" ? (who.modelData.name || "") : mentions.mode === "emoji" ? (who.modelData.face || (who.modelData.code ? ":" + who.modelData.code + ":" : ""))
                                 : (who.modelData.command ? app.t["cmd_" + who.modelData.command.id + "_d"] : "") }
                }
            }
        }
    }
}
