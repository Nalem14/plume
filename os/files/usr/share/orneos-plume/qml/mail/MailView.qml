// Mail module: folders on the side (Orneos, then each external mailbox), the list (one line per
// conversation, days, unread, search), the opened message or conversation.
// Keyboard: ↑ ↓ to move, Enter opens, E archives, Delete trashes, R / Shift+R / F reply, all, forward.
// After archiving or deleting the opened message, the next one opens (an option of the settings).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../contacts"

Rectangle {
    id: view
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    property int currentId: 0
    property alias composer: composer
    property alias reader: reader
    // a narrow window: the folders fold into a column of icons, the list gets slimmer
    readonly property bool compact: width < 1120
    color: c.bg

    // Ornis on the opened message (menu of the reader, command palette)
    function askOrnis(kind) {
        if (mail.current.messageId && !mail.current.loading)
            reader.ornisRun(kind)
    }

    function compose(mode, messageId) {
        // a reply needs the message itself (its text, its date): not while it is still loading
        if (mode !== "new" && (!mail.current.messageId || mail.current.loading))
            return
        view.openComposer(messageId ? mail.compose(mode, messageId) : mail.compose(mode))
    }
    // a composer for this message: the main one when it is free, else a new window (several can be open,
    // each closes on its own and keeps its draft)
    function openComposer(f) {
        if (!composer.visible) {
            composer.openWith(f)
            return composer
        }
        const extra = composerFactory.createObject(view)
        extra.closing.connect(() => Qt.callLater(() => extra.destroy()))
        extra.openWith(f)
        return extra
    }
    function composeUri(uri) {
        // mailto:a@b.c,d@e.f?subject=…&cc=…&body=…
        const f = mail.compose("new")
        const text = String(uri).replace(/^mailto:/i, "")
        const q = text.indexOf("?")
        const head = decodeURIComponent(q >= 0 ? text.slice(0, q) : text)
        f.to = head ? head.split(",").map(x => x.trim()).filter(x => x) : []
        if (q >= 0) {
            for (const pair of text.slice(q + 1).split("&")) {
                const eq = pair.indexOf("=")
                const key = decodeURIComponent(pair.slice(0, eq)).toLowerCase()
                const value = decodeURIComponent(pair.slice(eq + 1).replace(/\+/g, " "))
                if (key === "subject") f.subject = value
                else if (key === "body") f.body = value + f.body
                else if (key === "cc" || key === "bcc") f[key] = value.split(",").map(x => x.trim()).filter(x => x)
            }
        }
        view.openComposer(f)
    }
    // files given by Dolphin (« Send with Orneos Mail »): a new message with them attached
    function composeFiles(paths) {
        const f = mail.compose("new")
        f.subject = paths.map(p => String(p).split("/").pop()).join(", ").slice(0, 120)
        f.attachments = paths
        view.openComposer(f)
    }
    function openId(id) {
        currentId = id
        if (id)
            mail.open(id)
    }
    // a click on the line already opened closes it
    function toggle(id, index) {
        if (id === currentId) {
            currentId = 0
            list.currentIndex = -1
            mail.close()
        } else {
            list.currentIndex = index
            openId(id)
        }
    }

    // Several lines picked for one action: Ctrl+click adds or removes one (or the round box on the left of a
    // line), Shift+click takes a range, Ctrl+A all the lines loaded. The reader then shows what can be done
    // to all of them; the keys (E, Delete, S) and the right click act on all of them too.
    property var selection: []            // messageId of the lines (each stands for its conversation)
    property int anchorRow: -1
    function picked(id) { return selection.indexOf(id) >= 0 }
    function clickLine(id, index, key) {
        list.forceActiveFocus()
        if (key === "") {
            selection = []
            anchorRow = index
            toggle(id, index)
            return
        }
        let out
        if (key === "shift") {
            const from = anchorRow >= 0 ? anchorRow : (currentId ? mail.rowOf(currentId) : index)
            out = []
            for (let i = Math.min(from, index); i <= Math.max(from, index); i++)
                out.push(mail.idAt(i))
        } else {
            out = selection.length ? selection.slice() : (currentId && mail.rowOf(currentId) >= 0 ? [mail.idAt(mail.rowOf(currentId))] : [])
            const at = out.indexOf(id)
            if (at >= 0)
                out.splice(at, 1)
            else
                out.push(id)
            anchorRow = index
        }
        select(out.filter(x => x > 0))
    }
    function select(ids) {
        selection = ids
        if (ids.length && currentId) {
            // the reader shows the selection, not a message
            currentId = 0
            list.currentIndex = -1
            mail.close()
        }
    }
    function selectAll() {
        let out = []
        for (let i = 0; i < list.count; i++)
            out.push(mail.idAt(i))
        select(out)
    }
    function selectionMenu(anchor, px, py, lead) {
        messageMenu.openFor(Object.assign({ messageId: lead || selection[0], ids: selection }, mail.selectionInfo(selection)), anchor, px, py)
    }

    // Archive, bin, junk, another folder: the whole conversation of the line goes (of every line of the
    // selection when the line is one of them). Sending to the junk folder and deleting for good ask first
    // (option); the next message opens when the opened one left.
    function act(id, role) {
        const many = selection.length > 0 && (id === 0 || picked(id))
        if (!id && !many)
            return
        const forever = role === "trash" && mail.folderRole === "trash"
        const run = many ? () => view.applyMany(role) : () => view.apply(id, role)
        if (plume.prefs.mail_confirm && (role === "junk" || forever)) {
            confirm.ask(forever ? plume.t.confirm_delete_title : plume.t.confirm_spam_title,
                        forever ? plume.t.confirm_delete_text : plume.t.confirm_spam_text,
                        [{ id: "cancel", text: plume.t.cancel },
                         { id: "go", text: forever ? plume.t.delete_forever : plume.t.spam_report, kind: "danger" }],
                        run)
            return
        }
        run()
    }
    function applyMany(role) {
        const ids = mail.threadsIds(selection)
        selection = []
        anchorRow = -1
        mail.moveTo(ids, role)
    }
    function apply(id, role) {
        let next = 0
        if (id === currentId && plume.prefs.mail_advance) {
            const row = mail.rowOf(id)
            next = mail.idAt(row + 1) || mail.idAt(row - 1)
        }
        const ids = mail.threadIds(id)
        if (id === currentId)
            currentId = 0
        mail.moveTo(ids, role)
        if (next) {
            list.currentIndex = mail.rowOf(next)
            openId(next)
        }
    }

    // « Me le rappeler »: the lines go to « Plus tard » until then (at 0: a day and a time are asked first)
    function snooze(leads, at) {
        if (!at) {
            when.pickFor(plume.t.snooze, t => view.snooze(leads, t))
            return
        }
        if (leads.indexOf(currentId) >= 0)
            currentId = 0
        selection = []
        mail.snooze(leads, at)
    }
    // the next (1) or previous (-1) line opened, as ↓ and ↑ do in the list
    function step(delta) {
        const row = view.currentId ? mail.rowOf(view.currentId) : -1
        const next = Math.max(0, Math.min(list.count - 1, row + delta))
        if (next === row)
            return
        list.currentIndex = next
        list.positionViewAtIndex(next, ListView.Contain)
        openId(mail.idAt(next))
    }
    // « Déplacer vers » of the opened message or the selection, at the top of the reader
    function moveMenu() {
        if (selection.length)
            selectionMenu(reader, reader.width - 260, 56)
        else if (currentId)
            messageMenu.openFor({ messageId: currentId, seen: true, flagged: !!mail.current.flagged, tags: mail.current.tags || [],
                                  box: mail.current.box || "orneos", role: mail.current.role || "" }, reader, reader.width - 260, 56)
    }
    // lines dropped onto a folder: moved there (a folder of their own mailbox only)
    function dropOn(folder, drop) {
        if (drop.formats.indexOf("application/x-plume-messages") < 0)
            return
        const ids = JSON.parse(drop.getDataAsString("application/x-plume-messages") || "[]")
        if (!ids.length || folder.id <= 0)
            return
        const all = mail.threadsIds(ids)
        if (ids.indexOf(currentId) >= 0)
            currentId = 0
        selection = []
        mail.afterDrag("moveTo", [all, String(folder.id)])   // after the drag (dragguard.py: macOS)
        drop.accept()
    }

    function when(stamp) {
        const d = new Date(stamp * 1000), now = new Date()
        if (d.toDateString() === now.toDateString())
            return Qt.formatTime(d, "HH:mm")
        if (now - d < 6 * 86400000)
            return loc.dayName(d.getDay(), Locale.ShortFormat).replace(".", "") + " " + Qt.formatTime(d, "HH:mm")
        return Qt.formatDate(d, d.getFullYear() === now.getFullYear() ? "dd/MM" : "dd/MM/yy")
    }
    function folderName(f) { return f.role === "tag" ? plume.t["tag_" + f.tag] : f.role ? plume.t["folder_" + f.role] : f.name }
    function folderIcon(role) {
        return { inbox: "inbox", allinbox: "inbox", outbox: "clock", snoozed: "history", flagged: "star", drafts: "draft", sent: "send", archive: "archive", junk: "spam", trash: "trash" }[role] || "folder"
    }
    function boxUnseen(key) {
        const inbox = mail.folders.find(f => f.box === key && f.role === "inbox")
        return inbox ? inbox.unseen : 0
    }
    function boxStatus(key) {
        const box = mail.boxes.find(b => b.key === key)
        return box ? box.status : "ready"
    }

    Shortcut { enabled: plume.module === "mail" && mail.state === "ready"; sequence: "Ctrl+N"; onActivated: view.compose("new") }
    Shortcut { enabled: plume.module === "mail" && (view.currentId > 0 || view.selection.length > 0); sequences: ["E"]; onActivated: view.act(view.currentId, "archive") }
    Shortcut { enabled: plume.module === "mail" && (view.currentId > 0 || view.selection.length > 0); sequences: [StandardKey.Delete]; onActivated: view.act(view.currentId, "trash") }
    Shortcut { enabled: plume.module === "mail" && view.currentId > 0; sequence: "R"; onActivated: view.compose("reply") }
    Shortcut { enabled: plume.module === "mail" && view.currentId > 0; sequence: "Shift+R"; onActivated: view.compose("all") }
    Shortcut { enabled: plume.module === "mail" && view.currentId > 0; sequence: "F"; onActivated: view.compose("forward") }
    Shortcut { enabled: plume.module === "mail" && view.currentId > 0; sequence: "S"; onActivated: mail.setFlagged(view.currentId, !mail.current.flagged) }
    Shortcut { enabled: plume.module === "mail" && view.selection.length > 0; sequence: "S"; onActivated: mail.setFlaggedMany(view.selection, !mail.selectionInfo(view.selection).flagged) }
    Shortcut { enabled: plume.module === "mail" && view.currentId > 0 && !filter.activeFocus; sequence: "Escape"; onActivated: view.toggle(view.currentId, -1) }
    Shortcut { enabled: plume.module === "mail" && view.selection.length > 0 && !filter.activeFocus; sequence: "Escape"; onActivated: view.selection = [] }
    Shortcut { enabled: plume.module === "mail"; sequence: "Ctrl+F"; onActivated: filter.forceActiveFocus() }
    Shortcut { enabled: plume.module === "mail" && mail.state === "ready"; sequence: "F5"; onActivated: mail.refresh() }
    // U: read or unread; J / K: next and previous line; /: search; V: move to a folder; Ctrl+P: print
    Shortcut {
        enabled: plume.module === "mail" && !filter.activeFocus && (view.currentId > 0 || view.selection.length > 0)
        sequence: "U"
        onActivated: {
            if (view.selection.length)
                mail.setSeenMany(view.selection, !mail.selectionInfo(view.selection).seen)
            else {
                // the opened message is read: U leaves it unread, and closes it (opening it again would read it)
                mail.setSeen(view.currentId, false)
                view.toggle(view.currentId, -1)
            }
        }
    }
    Shortcut { enabled: plume.module === "mail" && !filter.activeFocus && list.count > 0; sequence: "J"; onActivated: view.step(1) }
    Shortcut { enabled: plume.module === "mail" && !filter.activeFocus && list.count > 0; sequence: "K"; onActivated: view.step(-1) }
    Shortcut { enabled: plume.module === "mail" && !filter.activeFocus; sequence: "/"; onActivated: filter.forceActiveFocus() }
    Shortcut { enabled: plume.module === "mail" && !filter.activeFocus && (view.currentId > 0 || view.selection.length > 0); sequence: "V"; onActivated: view.moveMenu() }
    Shortcut { enabled: plume.module === "mail" && view.currentId > 0; sequence: StandardKey.Print; onActivated: reader.printMessage() }
    // 1 … 5 put a tag on the opened message (or the selection), or take it off (like Thunderbird)
    Repeater {
        model: 5
        Item {
            required property int index
            Shortcut {
                enabled: plume.module === "mail" && (view.currentId > 0 || view.selection.length > 0) && !filter.activeFocus
                sequence: String(index + 1)
                onActivated: {
                    if (view.selection.length)
                        mail.setTagMany(view.selection, index + 1, Array.from(mail.selectionInfo(view.selection).tags || []).indexOf(index + 1) < 0)
                    else
                        mail.setTag(view.currentId, index + 1, Array.from(mail.current.tags || []).indexOf(index + 1) < 0)
                }
            }
        }
    }

    Connections {
        target: mail
        function onChanged() {
            if (view.selection.length) {
                // lines gone (moved, the folder changed) leave the selection; a line now led by a newer message follows it
                const kept = view.selection.map(id => mail.rowOf(id)).filter(row => row >= 0).map(row => mail.idAt(row))
                if (kept.length !== view.selection.length || kept.some((id, i) => id !== view.selection[i]))
                    view.selection = Array.from(new Set(kept))
            }
            if (!view.currentId)
                return
            const row = mail.rowOf(view.currentId)
            if (row < 0) {
                // the opened message left the list (archived, deleted elsewhere)
                view.currentId = 0
            } else if (mail.idAt(row) !== view.currentId) {
                // a newer message joined its conversation: the line now stands for that one
                view.currentId = mail.idAt(row)
            }
        }
        function onCurrentChanged() { if (!mail.current.messageId) view.currentId = 0 }
        // a message asked by its Message-ID (a task of Tâches): shown, its line chosen
        function onReveal(id) {
            view.openId(id)
            Qt.callLater(() => { list.currentIndex = mail.rowOf(id); list.positionViewAtIndex(Math.max(0, list.currentIndex), ListView.Center) })
        }
        // the message being written when Plume stopped, in the composer again
        function onComposeRecovered(f) { view.openComposer(f) }
        // a message cancelled (« Annuler »), refused by the server, or taken from the outbox: back in a composer
        function onSendCancelled(f) { view.openComposer(f) }
        // a move undone: the conversation comes back, opened again
        function onMoveCancelled(lead) {
            const row = mail.rowOf(lead)
            if (row >= 0) {
                list.currentIndex = row
                view.openId(mail.idAt(row))
            }
        }
    }

    MailSetup {
        anchors.fill: parent
        visible: mail.state === "setup"
    }

    RowLayout {
        anchors.fill: parent
        visible: mail.state === "ready" || mail.state === "loading"
        spacing: 0

        // ---- folders ----
        Rectangle {
            Layout.preferredWidth: view.compact ? 68 : 240
            Layout.fillHeight: true
            color: view.c.chrome
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: view.c.hairline }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: view.compact ? 10 : 12; anchors.topMargin: 14
                spacing: 2
                // the kicker: the app and its address
                RowLayout {
                    visible: !view.compact
                    Layout.fillWidth: true
                    Layout.leftMargin: 4; Layout.bottomMargin: 10
                    spacing: 8
                    Text {
                        text: plume.t.mail
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                        color: view.c.famCommunicate
                    }
                    Text {
                        Layout.fillWidth: true
                        text: mail.account.email || ""
                        font.family: "JetBrains Mono"; font.pixelSize: 11
                        color: view.c.muted
                        elide: Text.ElideRight
                    }
                }
                // the new-item line: opens a new message
                Capture {
                    visible: !view.compact
                    Layout.fillWidth: true
                    Layout.bottomMargin: 12
                    tint: view.c.famCommunicate
                    iconName: "compose"
                    text: plume.t.new_message
                    shortcut: "Ctrl N"
                    onClicked: view.compose("new")
                }
                OButton {
                    visible: view.compact
                    Layout.fillWidth: true
                    Layout.bottomMargin: 12
                    kind: "primary"; height_: 40
                    iconName: "compose"
                    tip: plume.t.new_message + "  (Ctrl+N)"
                    onClicked: view.compose("new")
                }
                Flickable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentHeight: folderColumn.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    ColumnLayout {
                        id: folderColumn
                        width: parent.width
                        spacing: 2
                        Repeater {
                            model: mail.folders
                            ColumnLayout {
                                id: entry
                                required property var modelData
                                required property int index
                                readonly property var previous: index > 0 ? mail.folders[index - 1] : null
                                readonly property bool firstOfBox: !previous || previous.box !== modelData.box
                                // a folded mailbox keeps only its name (the narrow column never folds)
                                readonly property bool hidden: entry.modelData.folded && !view.compact
                                Layout.fillWidth: true
                                spacing: 2
                                // a mailbox (when there are several): its address above its folders
                                Rectangle {
                                    visible: view.compact && entry.firstOfBox && (entry.modelData.boxLabel !== "" || entry.modelData.role === "tag")
                                    Layout.fillWidth: true; Layout.topMargin: 10; Layout.bottomMargin: 6
                                    implicitHeight: 1; color: view.c.line
                                }
                                AbstractButton {
                                    id: boxHead
                                    visible: !view.compact && entry.firstOfBox && entry.modelData.boxLabel !== ""
                                    Layout.fillWidth: true
                                    Layout.topMargin: 16; Layout.bottomMargin: 2
                                    implicitHeight: 30
                                    hoverEnabled: true
                                    Accessible.name: entry.modelData.boxLabel
                                    Accessible.description: entry.modelData.folded ? plume.t.box_expand : plume.t.box_collapse
                                    onClicked: mail.toggleBox(entry.modelData.box)
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: point => boxMenu.openFor(entry.modelData, boxHead, point.position.x, point.position.y) }
                                    background: Rectangle { radius: 6; color: boxHead.hovered ? view.c.hover : "transparent" }
                                    contentItem: RowLayout {
                                        spacing: 4
                                        Icon {
                                            Layout.leftMargin: 6
                                            name: entry.modelData.folded ? "chevronRight" : "chevronDown"; size: 14
                                            color: view.c.muted
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            text: entry.modelData.boxLabel
                                            elide: Text.ElideMiddle
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.4
                                            color: view.c.muted
                                        }
                                        // the inbox's unread count stays in sight when folded
                                        Text {
                                            visible: entry.modelData.folded && view.boxUnseen(entry.modelData.box) > 0
                                            text: view.boxUnseen(entry.modelData.box)
                                            font.family: "JetBrains Mono"; font.pixelSize: 12
                                            color: view.c.text
                                        }
                                        OButton {
                                            visible: view.boxStatus(entry.modelData.box) === "auth" || view.boxStatus(entry.modelData.box) === "offline"
                                            kind: "quiet"; height_: 22; implicitWidth: 22; iconName: "lock"; iconSize: 13
                                            tip: view.boxStatus(entry.modelData.box) !== "auth" ? plume.t.box_status_offline
                                                : (mail.boxes.find(b => b.key === entry.modelData.box) || {}).oauth ? plume.t.box_status_oauth : plume.t.box_status_auth
                                            onClicked: plume.openSettings("boxes")
                                        }
                                        OButton {
                                            visible: boxHead.hovered || hovered
                                            kind: "quiet"; height_: 22; implicitWidth: 22; iconName: "refresh"; iconSize: 13
                                            tip: plume.t.box_sync
                                            onClicked: mail.syncBox(entry.modelData.box)
                                        }
                                        Item { implicitWidth: 2 }
                                    }
                                }
                                Text {
                                    // a heading before the first folder of a mailbox that is not a special one
                                    visible: !view.compact && !entry.hidden && !entry.modelData.role && (entry.firstOfBox || !!entry.previous.role)
                                    Layout.leftMargin: 12; Layout.topMargin: 16; Layout.bottomMargin: 4
                                    text: plume.t.folders
                                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                                    font.capitalization: Font.AllUppercase
                                    color: view.c.muted
                                }
                                Text {
                                    visible: !view.compact && entry.modelData.role === "tag" && (!entry.previous || entry.previous.role !== "tag")
                                    Layout.leftMargin: 12; Layout.topMargin: 16; Layout.bottomMargin: 4
                                    text: plume.t.tags_heading
                                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                                    font.capitalization: Font.AllUppercase
                                    color: view.c.muted
                                }
                                AbstractButton {
                                    id: folder
                                    readonly property bool active: mail.folderId === entry.modelData.id
                                    visible: !entry.hidden
                                    Layout.fillWidth: true
                                    implicitHeight: 36
                                    hoverEnabled: true
                                    Accessible.name: view.folderName(entry.modelData)
                                    ToolTip.text: view.compact ? view.folderName(entry.modelData) + (entry.modelData.unseen > 0 && entry.modelData.role !== "drafts" ? "  (" + entry.modelData.unseen + ")" : "")
                                                  + (entry.modelData.boxLabel ? " · " + entry.modelData.boxLabel : "") : ""
                                    ToolTip.visible: hovered && view.compact
                                    ToolTip.delay: 300
                                    onClicked: { view.currentId = 0; view.selection = []; mail.selectFolder(entry.modelData.id) }
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: point => folderMenu.openFor(entry.modelData, folder, point.position.x, point.position.y) }
                                    // messages dragged from the list land here (a real folder only)
                                    DropArea {
                                        id: folderDrop
                                        anchors.fill: parent
                                        enabled: entry.modelData.id > 0
                                        onEntered: drag => { if (drag.formats.indexOf("application/x-plume-messages") < 0) drag.accepted = false }
                                        onDropped: drop => view.dropOn(entry.modelData, drop)
                                    }
                                    background: Rectangle {
                                        radius: 7
                                        border.width: folderDrop.containsDrag ? 2 : 0
                                        border.color: view.c.famCommunicate
                                        color: folderDrop.containsDrag ? view.c.tint : folder.active ? view.c.card : folder.hovered ? view.c.hover : "transparent"
                                        Band {
                                            visible: folder.active
                                            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                                            radius: 1.5
                                            color: view.c.famCommunicate
                                        }
                                    }
                                    contentItem: RowLayout {
                                        spacing: 12
                                        Item {
                                            Layout.leftMargin: view.compact ? 14 : 10 + Math.min(entry.modelData.depth, 3) * 14
                                            implicitWidth: 20; implicitHeight: 20
                                            Icon {
                                                anchors.centerIn: parent
                                                visible: entry.modelData.role !== "tag"
                                                name: view.folderIcon(entry.modelData.role); size: 20
                                                color: folder.active ? view.c.famCommunicate : view.c.muted
                                            }
                                            Rectangle {
                                                anchors.centerIn: parent
                                                visible: entry.modelData.role === "tag"
                                                width: 10; height: 10; radius: 5
                                                color: view.c["tag" + entry.modelData.tag] || "transparent"
                                            }
                                        }
                                        Text {
                                            visible: !view.compact
                                            Layout.fillWidth: true
                                            text: view.folderName(entry.modelData)
                                            elide: Text.ElideRight
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                            font.weight: folder.active ? Font.DemiBold : Font.Medium
                                            color: view.c.text
                                        }
                                        Item { visible: view.compact; Layout.fillWidth: true }
                                        Text {
                                            Layout.rightMargin: view.compact ? 4 : 10
                                            visible: !view.compact && (entry.modelData.role === "drafts" ? entry.modelData.total > 0 : entry.modelData.unseen > 0)
                                            text: entry.modelData.role === "drafts" ? entry.modelData.total : entry.modelData.unseen
                                            font.family: "JetBrains Mono"; font.pixelSize: 13
                                            font.weight: entry.modelData.role === "inbox" || entry.modelData.role === "allinbox" ? Font.Medium : Font.Normal
                                            color: folder.active ? view.c.famCommunicate : entry.modelData.role === "inbox" || entry.modelData.role === "allinbox" ? view.c.text : view.c.muted
                                        }
                                    }
                                }
                            }
                        }
                        OButton {
                            Layout.fillWidth: true
                            Layout.topMargin: 14
                            kind: "quiet"; height_: 32
                            iconName: "plus"; iconSize: 15
                            text: view.compact ? "" : plume.t.box_add_short
                            tip: view.compact ? plume.t.box_add_short : ""
                            onClicked: plume.openSettings("add_box")
                        }
                    }
                }
                AccountBar {
                    visible: !view.compact
                    Layout.fillWidth: true
                    Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
                    name: plume.profile.name || ""
                    email: plume.profile.email || ""
                    initials: plume.profile.initials || ""
                    onSettingsRequested: plume.openSettings("")
                    OMenuItem { text: plume.t.account_manage; iconName: "user"; onTriggered: plume.openAccount() }
                    OMenuItem { visible: !signin.canSignOut; height: visible ? implicitHeight : 0; text: plume.t.reconnect; iconName: "refresh"; onTriggered: plume.openConnect() }
                    OMenuItem { visible: signin.canSignOut; height: visible ? implicitHeight : 0; text: plume.t.sign_out; iconName: "lock"; onTriggered: plume.openSettings("") }
                }
                OButton {
                    visible: view.compact
                    Layout.alignment: Qt.AlignHCenter
                    kind: "quiet"; implicitWidth: 36; iconName: "settings"
                    tip: plume.t.settings + "  (Ctrl+,)"
                    onClicked: plume.openSettings("")
                }
            }
        }

        // ---- the list ----
        Rectangle {
            Layout.preferredWidth: view.compact ? 330 : 380
            Layout.fillHeight: true
            color: view.c.card
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: view.c.line; z: 2 }
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 14; Layout.topMargin: 16
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        readonly property var shownFolder: mail.folders.find(f => f.id === mail.folderId) || { role: "inbox" }
                        Text {
                            Layout.fillWidth: true
                            text: view.folderName(parent.shownFolder)
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.Bold; font.letterSpacing: -0.4
                            color: view.c.text
                            Accessible.role: Accessible.Heading
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (parent.shownFolder.unseen === 1 ? plume.t.unread_one + " · "
                                   : parent.shownFolder.unseen > 1 ? plume.t.unread.replace("%1", parent.shownFolder.unseen) + " · " : "")
                                  + plume.t.messages_count.replace("%1", parent.shownFolder.total || mail.count)
                            elide: Text.ElideRight
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: view.c.muted
                        }
                        // the only state of the sync ever shown: offline, with when the server last answered
                        Rectangle {
                            visible: !plume.connection.mail.online
                            Layout.topMargin: 4
                            implicitHeight: 20; radius: 5
                            implicitWidth: offRow.implicitWidth + 12
                            color: view.c.saffronTint
                            Row {
                                id: offRow
                                anchors.centerIn: parent
                                spacing: 5
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "offline"; size: 13; color: view.c.saffronInk }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: plume.connection.mail.online ? "" : plume.offlineLine("mail")
                                    font.family: "JetBrains Mono"; font.pixelSize: 12
                                    color: view.c.saffronInk
                                }
                            }
                        }
                    }
                    OButton {
                        kind: "quiet"; height_: 30; implicitWidth: 30; iconName: "refresh"; iconSize: 15
                        tip: plume.t.refresh + "  (F5)"
                        onClicked: mail.refresh()
                    }
                    Rectangle {
                        implicitWidth: segs.implicitWidth + 4; implicitHeight: 30; radius: 7
                        color: view.c.bg; border.width: 1; border.color: view.c.line
                        Row {
                            id: segs
                            anchors.centerIn: parent
                            Repeater {
                                model: [[false, plume.t.filter_all], [true, plume.t.filter_unread]]
                                AbstractButton {
                                    id: seg
                                    required property var modelData
                                    readonly property bool active: mail.unreadOnly === modelData[0]
                                    width: segLabel.implicitWidth + 20; height: 26
                                    hoverEnabled: true
                                    onClicked: mail.setUnreadOnly(modelData[0])
                                    background: Rectangle { radius: 5; color: seg.active ? view.c.card : "transparent"; border.width: seg.active ? 1 : 0; border.color: view.c.line }
                                    contentItem: Text {
                                        id: segLabel
                                        text: seg.modelData[1]
                                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: seg.active ? Font.DemiBold : Font.Medium
                                        color: seg.active || seg.hovered ? view.c.text : view.c.muted
                                    }
                                }
                            }
                        }
                    }
                }
                OTextField {
                    id: filter
                    Layout.fillWidth: true
                    Layout.margins: 12; Layout.leftMargin: 14; Layout.rightMargin: 14
                    iconName: "search"
                    placeholderText: plume.t.search_short
                    onTextChanged: debounce.restart()
                    onCleared: { debounce.stop(); mail.search("") }
                    Keys.onDownPressed: { list.forceActiveFocus(); list.currentIndex = 0 }
                    Timer { id: debounce; interval: 220; onTriggered: mail.search(filter.text) }
                }
                // while searching: here or everywhere; before typing, the filters the field understands
                RowLayout {
                    visible: filter.text.trim() !== "" || filter.activeFocus
                    Layout.fillWidth: true
                    Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: -4; Layout.bottomMargin: 8
                    spacing: 6
                    Text {
                        visible: filter.text.trim() === ""
                        Layout.fillWidth: true
                        text: plume.t.search_filters
                        wrapMode: Text.Wrap
                        font.family: "JetBrains Mono"; font.pixelSize: 11
                        color: view.c.muted
                    }
                    Repeater {
                        model: filter.text.trim() !== "" ? [[false, plume.t.search_here], [true, plume.t.search_everywhere]] : []
                        AbstractButton {
                            id: scope
                            required property var modelData
                            readonly property bool active: mail.everywhere === modelData[0]
                            implicitWidth: scopeLabel.implicitWidth + 20; implicitHeight: 26
                            hoverEnabled: true
                            onClicked: mail.setEverywhere(modelData[0])
                            background: Rectangle { radius: 13; color: scope.active ? view.c.tint : scope.hovered ? view.c.hover : "transparent"; border.width: scope.active ? 0 : 1; border.color: view.c.line }
                            contentItem: Text {
                                id: scopeLabel
                                text: scope.modelData[1]
                                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: scope.active ? Font.DemiBold : Font.Medium
                                color: scope.active ? view.c.tintText : view.c.muted
                            }
                        }
                    }
                    Item { visible: filter.text.trim() !== ""; Layout.fillWidth: true }
                }
                // lines picked: how many, and back to none
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 10; Layout.bottomMargin: 8
                    visible: view.selection.length > 0
                    spacing: 6
                    Text {
                        Layout.fillWidth: true
                        text: view.selection.length === 1 ? plume.t.selected_one : plume.t.selected_many.replace("%1", view.selection.length)
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                        color: view.c.text
                    }
                    OButton {
                        visible: view.selection.length < list.count
                        kind: "quiet"; height_: 26
                        text: plume.t.select_all
                        onClicked: view.selectAll()
                    }
                    OButton {
                        kind: "quiet"; height_: 26; implicitWidth: 26; iconName: "close"; iconSize: 13
                        tip: plume.t.select_clear + "  (Esc)"
                        onClicked: view.selection = []
                    }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.hairline }

                ListView {
                    id: list
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: mail.model
                    reuseItems: true
                    boundsBehavior: Flickable.StopAtBounds
                    keyNavigationEnabled: true
                    currentIndex: -1
                    ScrollBar.vertical: ScrollBar {}
                    onCurrentIndexChanged: if (activeFocus && currentIndex >= 0) view.openId(mail.idAt(currentIndex))
                    Keys.onReturnPressed: view.openId(mail.idAt(currentIndex))
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
                            view.selectAll()
                            event.accepted = true
                        }
                    }
                    section.property: "section"
                    section.delegate: Item {
                        required property string section
                        width: ListView.view.width; height: 32
                        Text {
                            x: 30; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                            text: plume.t["head_" + parent.section] || ""
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.8
                            color: view.c.muted
                        }
                    }
                    delegate: AbstractButton {
                        id: row
                        required property int messageId
                        required property string fromName
                        required property string subject
                        required property string preview
                        required property int date
                        required property bool seen
                        required property bool flagged
                        required property bool answered
                        required property bool attachments
                        required property int count
                        required property string boxLabel
                        required property var tags
                        required property string box
                        required property string where
                        required property int index
                        readonly property bool active: view.currentId === messageId
                        readonly property bool chosen: view.selection.length > 0 && view.picked(messageId)
                        width: ListView.view.width
                        height: 82
                        hoverEnabled: true
                        Accessible.name: fromName + ", " + subject
                        onClicked: view.clickLine(messageId, index, plume.modifier())
                        // dragged into a note or onto a task (Notes, Tâches): a link to the message (or to each
                        // line picked), with its subject; the data is ready from the moment the line is hovered
                        DragHandler { id: dragger; target: null }
                        Drag.active: dragger.active
                        Drag.dragType: Drag.Automatic
                        Drag.supportedActions: Qt.CopyAction | Qt.LinkAction
                        Drag.mimeData: row.hovered ? mail.dragData(row.chosen ? view.selection : [row.messageId]) : ({})
                        Drag.onDragStarted: mail.dragStarted()
                        Drag.onDragFinished: mail.dragEnded()
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: point => {
                                if (row.chosen && view.selection.length > 1)
                                    view.selectionMenu(row, point.position.x, point.position.y, row.messageId)
                                else
                                    messageMenu.openFor({ messageId: row.messageId, seen: row.seen, flagged: row.flagged,
                                                          tags: row.tags, box: row.box, role: row.where },
                                                        row, point.position.x, point.position.y)
                            }
                        }
                        // the opened line: a light wash of the family colour and its band (picked lines: the wash only)
                        background: Rectangle {
                            color: row.active || row.chosen ? Qt.tint(view.c.card, Qt.alpha(view.c.famCommunicate, theme.dark ? 0.14 : 0.07))
                                 : row.hovered ? view.c.bg : "transparent"
                            Rectangle { anchors.bottom: parent.bottom; x: 30; width: parent.width - 30; height: 1; color: view.c.hairline }
                            Band { visible: row.active; height: parent.height; color: view.c.famCommunicate }
                        }
                        contentItem: Item {
                            Rectangle {
                                visible: !row.seen && !pick.visible
                                x: 12; y: 19; width: 8; height: 8; radius: 4
                                color: view.c.action
                            }
                            // the round box to pick the line (on hover, or while lines are picked)
                            AbstractButton {
                                id: pick
                                visible: row.hovered || view.selection.length > 0
                                x: 5; y: 12; width: 22; height: 22
                                hoverEnabled: true
                                Accessible.name: plume.t.select
                                ToolTip.text: plume.t.select
                                ToolTip.visible: hovered && view.selection.length === 0
                                ToolTip.delay: 500
                                onClicked: view.clickLine(row.messageId, row.index, "ctrl")
                                background: Rectangle {
                                    anchors.centerIn: parent
                                    width: 16; height: 16; radius: 8
                                    color: row.chosen ? view.c.action : "transparent"
                                    border.width: row.chosen ? 0 : 1.5
                                    border.color: pick.hovered ? view.c.action : (!row.seen ? view.c.action : view.c.muted)
                                    Icon { anchors.centerIn: parent; visible: row.chosen; name: "check"; size: 12; color: view.c.actionText }
                                }
                            }
                            ColumnLayout {
                                x: 30; y: 12
                                width: parent.width - 30 - 16
                                spacing: 2
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text {
                                        Layout.fillWidth: true
                                        text: row.fromName
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: row.seen ? Font.Medium : Font.Bold
                                        color: view.c.text
                                    }
                                    // the number of messages of the conversation
                                    Rectangle {
                                        visible: row.count > 1
                                        implicitWidth: countLabel.implicitWidth + 10; implicitHeight: 18; radius: 9
                                        color: row.active ? view.c.card : view.c.hover
                                        Text {
                                            id: countLabel
                                            anchors.centerIn: parent
                                            text: row.count
                                            font.family: "JetBrains Mono"; font.pixelSize: 11
                                            color: view.c.muted
                                        }
                                    }
                                    // the unified inbox says which mailbox a message came to
                                    Text {
                                        visible: row.boxLabel !== ""
                                        Layout.maximumWidth: 110
                                        text: row.boxLabel
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                        color: view.c.muted
                                    }
                                    Row {
                                        visible: row.tags && row.tags.length > 0
                                        spacing: 3
                                        Repeater {
                                            model: row.tags
                                            Rectangle {
                                                required property int modelData
                                                width: 8; height: 8; radius: 4
                                                color: view.c["tag" + modelData]
                                            }
                                        }
                                    }
                                    Icon { visible: row.answered; name: "reply"; size: 14; color: view.c.muted }
                                    Icon { visible: row.attachments; name: "clip"; size: 14; color: view.c.muted }
                                    Icon { visible: row.flagged; name: "star"; size: 14; color: view.c.saffron }
                                    Text {
                                        text: view.when(row.date)
                                        font.family: "JetBrains Mono"; font.pixelSize: 12
                                        color: row.seen ? view.c.muted : view.c.text
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: row.subject || plume.t.subject_empty
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: row.seen ? Font.Normal : Font.DemiBold
                                    color: view.c.text
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: row.preview
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                    color: view.c.muted
                                }
                            }
                            // quick actions on hover (the opened line too), on a background that hides the preview
                            Rectangle {
                                visible: row.hovered
                                anchors.right: parent.right; anchors.rightMargin: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 7
                                width: quick.implicitWidth + 8; height: quick.implicitHeight + 6; radius: 8
                                color: row.active ? Qt.tint(view.c.card, Qt.alpha(view.c.famCommunicate, theme.dark ? 0.14 : 0.07)) : view.c.bg
                                Row {
                                    id: quick
                                    anchors.centerIn: parent
                                    spacing: 4
                                    OButton { kind: "secondary"; iconName: "archive"; iconSize: 15; height_: 26; implicitWidth: 28; tip: plume.t.archive; onClicked: view.act(row.messageId, "archive") }
                                    OButton { kind: "secondary"; iconName: "trash"; iconSize: 15; height_: 26; implicitWidth: 28; danger: true; tip: plume.t.delete; onClicked: view.act(row.messageId, "trash") }
                                    OButton { kind: "secondary"; iconName: "mail"; iconSize: 15; height_: 26; implicitWidth: 28; tip: row.seen ? plume.t.mark_unread : plume.t.mark_read; onClicked: mail.setSeen(row.messageId, !row.seen) }
                                }
                            }
                        }
                    }
                    footer: Item {
                        width: ListView.view.width
                        height: mail.hasMore ? 60 : 12
                        OButton {
                            visible: mail.hasMore
                            anchors.centerIn: parent
                            kind: "quiet"
                            text: plume.t.load_more
                            onClicked: mail.loadMore()
                        }
                    }
                    Skeleton { anchors.fill: parent; anchors.margins: 20; visible: list.count === 0 && mail.busy; tone: view.c.line; rows: 8; Accessible.name: plume.t.loading }
                    Text {
                        anchors.centerIn: parent
                        visible: list.count === 0 && !mail.busy
                        text: plume.t.empty_folder
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15
                        color: view.c.muted
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Reader {
                id: reader
                anchors.fill: parent
                onReplyRequested: (mode, messageId) => view.compose(mode, messageId)
                onDraftRequested: view.openComposer(mail.draftFields())
                onActionRequested: role => view.act(view.currentId, role)
                onCloseRequested: view.toggle(view.currentId, -1)
                onSnoozeRequested: anchor => snoozeMenu.openFor([view.currentId], anchor, 0, anchor.height + 6)
                onReplyWithText: text => {
                    const f = mail.compose("reply")
                    f.body = text
                    view.openComposer(f)
                }
            }
            // lines picked: what can be done to all of them
            Rectangle {
                id: picked
                anchors.fill: parent
                visible: view.selection.length > 0
                color: view.c.bg
                // mail.count: read again when the lines change (marked read, a tag)
                readonly property var info: visible ? (mail.count, mail.selectionInfo(view.selection)) : ({})
                MouseArea { anchors.fill: parent }          // nothing reaches the reader underneath
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(440, parent.width - 48)
                    spacing: 10
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        implicitWidth: 64; implicitHeight: 64; radius: 32
                        color: view.c.tint
                        Icon { anchors.centerIn: parent; name: "mail"; size: 28; color: view.c.tintText }
                    }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: view.selection.length === 1 ? plume.t.selected_one : plume.t.selected_many.replace("%1", view.selection.length)
                        font.family: "Schibsted Grotesk"; font.pixelSize: 20; font.weight: Font.DemiBold
                        color: view.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        text: plume.t.select_hint
                        lineHeight: 1.25
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: view.c.muted
                    }
                    Flow {
                        Layout.fillWidth: true
                        Layout.topMargin: 10
                        spacing: 8
                        // centred: Flow has no alignment of its own
                        leftPadding: Math.max(0, (width - pickedActions.implicitWidth) / 2)
                        Row {
                            id: pickedActions
                            spacing: 8
                            OButton {
                                visible: picked.info.role !== "archive"
                                iconName: "archive"; text: plume.t.archive
                                onClicked: view.act(0, "archive")
                            }
                            OButton {
                                iconName: "trash"; danger: true
                                text: picked.info.role === "trash" ? plume.t.delete_forever : plume.t.delete
                                onClicked: view.act(0, "trash")
                            }
                            OButton {
                                iconName: "mail"
                                text: picked.info.seen ? plume.t.mark_unread : plume.t.mark_read
                                onClicked: mail.setSeenMany(view.selection, !picked.info.seen)
                            }
                            OButton {
                                id: pickedMore
                                kind: "quiet"; implicitWidth: 34; iconName: "more"
                                tip: plume.t.more_actions
                                onClicked: view.selectionMenu(pickedMore, 0, pickedMore.height + 4)
                            }
                        }
                    }
                }
            }
        }
    }

    Composer { id: composer }
    Component { id: composerFactory; Composer {} }
    WhenPicker { id: when }
    // « Me le rappeler »: the usual moments, or a day and a time
    OMenu {
        id: snoozeMenu
        property var leads: []
        property var options: []
        heading: plume.t.snooze
        function openFor(ids, anchor, px, py) {
            leads = Array.from(ids)
            options = Array.from(mail.laterOptions("snooze"))
            parent = anchor; x = px; y = py
            open()
        }
        Repeater {
            model: snoozeMenu.options
            OMenuItem {
                required property var modelData
                text: modelData.label; iconName: "history"
                onTriggered: view.snooze(snoozeMenu.leads, modelData.at)
            }
        }
        OMenuItem { text: plume.t.later_pick; iconName: "calendar"; onTriggered: view.snooze(snoozeMenu.leads, 0) }
    }
    ChoiceDialog { id: confirm }
    MessageMenu {
        id: messageMenu
        onSnoozeRequested: leads => snoozeMenu.openFor(leads, messageMenu.parent, messageMenu.x, messageMenu.y)
        onActionRequested: role => view.act(messageMenu.messageId, role)
        onSeenToggled: seen => { if (!seen && messageMenu.messageId === view.currentId) view.toggle(view.currentId, -1) }
    }
    // a mailbox's name: sync it now, fold it, its settings
    OMenu {
        id: boxMenu
        property var f: ({})
        function openFor(entry, anchor, px, py) {
            f = entry; parent = anchor; x = px; y = py
            open()
        }
        heading: f.boxLabel || ""
        OMenuItem { text: plume.t.box_sync; iconName: "refresh"; onTriggered: mail.syncBox(boxMenu.f.box) }
        OMenuItem { text: boxMenu.f.folded ? plume.t.box_expand : plume.t.box_collapse; iconName: boxMenu.f.folded ? "chevronDown" : "chevronRight"; onTriggered: mail.toggleBox(boxMenu.f.box) }
        OMenuItem {
            text: plume.t.box_rename; iconName: "edit"
            onTriggered: renamePrompt.ask(plume.t.box_rename_title, plume.t.box_rename_text, "", boxMenu.f.boxLabel,
                                          plume.t.box_rename_go, value => mail.renameBox(boxMenu.f.box, value))
        }
        OMenuItem {
            text: plume.t.folder_new; iconName: "folderPlus"
            onTriggered: renamePrompt.ask(plume.t.folder_new_title, plume.t.folder_new_text, plume.t.folder_name_ph, "",
                                          plume.t.folder_create, value => mail.createFolder(boxMenu.f.box, 0, value))
        }
        OMenuItem { visible: boxMenu.f.box === "orneos"; text: plume.t.autoreply; iconName: "reply"; onTriggered: mail.openAutoreply() }
        OMenuItem { text: plume.t.box_manage; iconName: "settings"; onTriggered: plume.openSettings("boxes") }
    }
    PromptDialog { id: renamePrompt }
    // a folder: sync it now, everything read
    OMenu {
        id: folderMenu
        property var f: ({})
        function openFor(entry, anchor, px, py) {
            f = entry; parent = anchor; x = px; y = py
            open()
        }
        heading: view.folderName(f.role !== undefined ? f : { role: "inbox" })
        subheading: f.boxLabel || ""
        OMenuItem { text: plume.t.folder_sync; iconName: "refresh"; onTriggered: mail.syncFolder(folderMenu.f.id, view.folderName(folderMenu.f)) }
        // folders of a mailbox: a new one (inside this one, or at the top from the inbox), rename, delete
        OMenuItem {
            visible: folderMenu.f.id > 0
            text: folderMenu.f.role === "inbox" || folderMenu.f.role ? plume.t.folder_new : plume.t.folder_new_inside; iconName: "folderPlus"
            onTriggered: {
                const f = folderMenu.f
                renamePrompt.ask(plume.t.folder_new_title, plume.t.folder_new_text, plume.t.folder_name_ph, "", plume.t.folder_create,
                                 value => mail.createFolder(f.box, f.role ? 0 : f.id, value))
            }
        }
        OMenuItem {
            visible: folderMenu.f.id > 0 && !folderMenu.f.role
            text: plume.t.folder_rename; iconName: "edit"
            onTriggered: {
                const f = folderMenu.f
                renamePrompt.ask(plume.t.folder_rename_title, "", plume.t.folder_name_ph, f.name, plume.t.folder_rename_go,
                                 value => mail.renameFolder(f.id, value))
            }
        }
        OMenuItem {
            visible: folderMenu.f.id > 0 && !folderMenu.f.role
            text: plume.t.folder_delete; iconName: "trash"; danger: true
            onTriggered: {
                const f = folderMenu.f
                confirm.ask(plume.t.folder_delete_title.replace("%1", f.name),
                            f.total > 0 ? plume.t.folder_delete_text.replace("%1", f.total) : plume.t.folder_delete_empty,
                            [{ id: "cancel", text: plume.t.cancel }, { id: "go", text: plume.t.folder_delete, kind: "danger" }],
                            () => mail.deleteFolder(f.id))
            }
        }
        OMenuItem { visible: folderMenu.f.role !== "drafts" && folderMenu.f.role !== "sent"; text: plume.t.mark_all_read; iconName: "check"; onTriggered: mail.markAllRead(folderMenu.f.id) }
        // the trash, the junk and the archive only (not Gmail's « All Mail »); never undone, so always asked
        OMenuItem {
            visible: !!folderMenu.f.emptiable && folderMenu.f.total > 0
            text: plume.t["empty_" + folderMenu.f.role] || ""; iconName: "trash"; danger: true
            onTriggered: {
                const f = folderMenu.f
                confirm.ask(plume.t["empty_" + f.role + "_title"],
                            plume.t.empty_text.replace("%1", f.total) + (f.boxLabel ? " (" + f.boxLabel + ")" : ""),
                            [{ id: "cancel", text: plume.t.cancel }, { id: "go", text: plume.t.empty_go, kind: "danger" }],
                            () => mail.emptyFolder(f.id))
            }
        }
    }
}
