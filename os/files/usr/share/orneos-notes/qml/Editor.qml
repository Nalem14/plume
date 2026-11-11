// The open note: its toolbar (the side columns, format, checklist, table, image, Ornis; contents, versions, pin,
// share), « Rechercher dans la note » (Ctrl+F) under it, the date and the words above the text, a banner when a
// sync kept another version, the text itself, then its images, its files and the notes that link to it.
// A note from « Récemment supprimées » shows read-only, with « Restaurer ».
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    readonly property var c: theme.c
    property string key
    property var d: ({})
    readonly property bool trashed: !!d.trashed
    readonly property bool editable: key !== "" && !d.readonly && !trashed
    signal deleteRequested(var keys)
    signal ornisRequested(string kind)
    signal askRequested()
    signal tasksRequested(string key)
    signal shareRequested(string key)
    signal openRequested(string key)
    signal focusToggled()
    signal versionsRequested(string key)
    signal conflictRequested(string copy)
    property bool focusMode: false
    property bool findOpen: false
    property bool replaceOpen: false
    color: c.bg

    function reload() { d = key ? notes.detail(key) : ({}) }
    function flush() { text.flush() }
    function focusText() { text.area.forceActiveFocus() }
    function focusStart() { text.area.cursorPosition = 0; focusText() }
    readonly property bool textFocused: text.area.activeFocus
    onKeyChanged: {
        text.flush()
        reload()
        text.key = key
        text.load(d.content || "")
        text.contentY = 0
        notes.setOpen(key)
        if (findOpen) text.refind(true)
        if (key && editable && (d.content || "") === "")
            Qt.callLater(focusText)
    }
    // Ctrl+F in the note (Ctrl+H: and replace); what is selected is what is looked for
    function openFind(withReplace) {
        if (!key) return
        const sel = text.area.selectedText
        if (sel && sel.indexOf("\n") < 0 && sel.indexOf("\u2029") < 0) findField.text = sel
        findOpen = true
        replaceOpen = withReplace && editable
        findField.forceActiveFocus()
        findField.selectAll()
        text.setFind(findField.text)
    }
    function findStep(back) { text.findStep(back) }
    function closeFind() {
        findOpen = false
        replaceOpen = false
        text.clearFind()
        focusText()
    }
    // the words of a search, shown in the note opened from its results
    function showWords(words) {
        if (!words) { if (!findOpen) text.clearFind(); return }
        text.setFind(words.split(/\s+/).sort((a, b) => b.length - a.length)[0] || "")
    }
    // the passage chosen, for Ornis ({start, end, text}; text "" when nothing is)
    function selection() {
        const a = text.area.selectionStart, b = text.area.selectionEnd
        return { start: a, end: b, text: text.area.text.slice(a, b) }
    }
    function cursor() { return text.area.cursorPosition }
    function replacePart(start, end, expected, content) {
        if (text.area.text.slice(start, end) !== expected) return false
        text.replaceRange(start, end, content)
        text.area.select(start, start + content.length)
        text.flush()
        return true
    }
    function insertAt(pos, content) {
        pos = Math.max(0, Math.min(pos, text.area.length))
        const lead = pos > 0 && text.area.text[pos - 1] !== "\n" ? "\n\n" : (pos > 0 ? "\n" : "")
        text.area.insert(pos, lead + content.trim() + "\n")
        text.flush()
    }
    // a picture or a file taken out of the note (its link; the file stays in the cloud's attachments)
    function removeAttachment(ref) {
        const t = text.area.text
        const esc = ref.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
        const re = new RegExp("!?\\[[^\\]]*\\]\\(" + esc + "(?:\\s+\"[^\"]*\")?\\)")
        const m = re.exec(t)
        if (!m) return
        let from = m.index, to = m.index + m[0].length
        const lineFrom = t.lastIndexOf("\n", from - 1) + 1
        let lineTo = t.indexOf("\n", to); if (lineTo < 0) lineTo = t.length
        if ((t.slice(lineFrom, from) + t.slice(to, lineTo)).trim() === "") { from = lineFrom; to = Math.min(t.length, lineTo + 1) }
        text.area.remove(from, to)
        text.flush()
        reload()
        toastRequest(app.t.attachment_removed)
    }
    // the headings of the note, for « Sommaire »: [{level, title, pos}]
    function headings() {
        const out = []
        let pos = 0, inside = false, first = true
        for (const line of text.area.text.split("\n")) {
            if (/^\s{0,3}(```|~~~)/.test(line)) inside = !inside
            else if (!inside) {
                const m = line.match(/^\s{0,3}(#{1,4})\s+(.+)$/)
                if (m && !(first && m[1].length === 1)) out.push({ level: m[1].length, title: m[2].replace(/[*_`~]/g, ""), pos: pos })
                if (line.trim()) first = false
            }
            pos += line.length + 1
        }
        return out
    }
    function goTo(pos) {
        text.area.cursorPosition = pos
        text.contentY = Math.max(0, Math.min(text.contentHeight - text.height, text.area.y + text.area.positionToRectangle(pos).y - 30))
        focusText()
    }
    Connections {
        target: notes
        function onNoteUpdated(k) { if (k === pane.key) { pane.reload(); text.takeRemote(pane.d.content || "") } }
        function onImagesChanged() { if (pane.key) pane.d = Object.assign({}, pane.d, { images: notes.detail(pane.key).images || [] }) }
        function onTrashChanged() { if (pane.trashed) { pane.reload(); text.load(pane.d.content || "") } }
        function onStateChanged() { if (pane.key && !pane.trashed) { const n = notes.detail(pane.key); pane.d = Object.assign({}, pane.d, { pending: n.pending, shared: n.shared }) } }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- toolbar -----------------------------------------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 56
            color: "transparent"
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10; anchors.rightMargin: 14
                spacing: 2

                OButton {
                    kind: "quiet"; implicitWidth: 36; iconName: "sidebar"
                    tip: (pane.focusMode ? app.t.focus_off : app.t.focus_on) + "  (Ctrl+Maj+E)"
                    onClicked: pane.focusToggled()
                }
                RowLayout {
                    visible: pane.editable
                    spacing: 2
                    OButton {
                        id: formatButton
                        kind: "quiet"; implicitWidth: 36; iconName: "format"; tip: app.t.format
                        onClicked: { formatMenu.tableHere = text.inTable(); formatMenu.open() }
                        OMenu {
                            id: formatMenu
                            property bool tableHere: false
                            y: formatButton.height + 6
                            implicitWidth: 280
                            OMenuItem { text: app.t.fmt_title; iconName: "format"; onTriggered: text.setBlock("title") }
                            OMenuItem { text: app.t.fmt_heading; iconName: "format"; onTriggered: text.setBlock("heading") }
                            OMenuItem { text: app.t.fmt_subheading; iconName: "format"; onTriggered: text.setBlock("subheading") }
                            OMenuItem { text: app.t.fmt_body; iconName: "note"; onTriggered: text.setBlock("body") }
                            Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                            OMenuItem { text: app.t.fmt_bold + "   Ctrl+B"; iconName: "bold"; onTriggered: text.wrap("**") }
                            OMenuItem { text: app.t.fmt_italic + "   Ctrl+I"; iconName: "italic"; onTriggered: text.wrap("*") }
                            OMenuItem { text: app.t.fmt_strike + "   Ctrl+Maj+X"; iconName: "strike"; onTriggered: text.wrap("~~") }
                            OMenuItem { text: app.t.fmt_code; iconName: "code"; onTriggered: text.wrap("`") }
                            OMenuItem { text: app.t.fmt_link + "   Ctrl+K"; iconName: "link"; onTriggered: text.insertLink() }
                            OMenuItem { text: app.t.link_to + "   Ctrl+Maj+K"; iconName: "note"; onTriggered: linkPicker.start() }
                            Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                            OMenuItem { text: app.t.fmt_bullets; iconName: "listBullet"; onTriggered: text.setBlock("bullet") }
                            OMenuItem { text: app.t.fmt_numbers; iconName: "listNumber"; onTriggered: text.setBlock("number") }
                            OMenuItem { text: app.t.fmt_quote; iconName: "quote"; onTriggered: text.setBlock("quote") }
                            OMenuItem { text: app.t.fmt_rule; iconName: "rule"; onTriggered: text.insertBlock("\n---\n") }
                            OMenuItem { text: app.t.fmt_codeblock; iconName: "code"; onTriggered: text.insertBlock("\n```\n\n```\n") }
                            Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                            OMenuItem { text: app.t.check_uncheck_all; iconName: "circle"; onTriggered: { if (!text.uncheckAll()) toastRequest(app.t.check_nothing) } }
                            OMenuItem { text: app.t.check_done_down; iconName: "done"; onTriggered: { if (!text.checkedDown()) toastRequest(app.t.check_nothing) } }
                            OMenuItem { text: app.t.move_line_hint; iconName: "drag"; enabled: false }
                            Rectangle { visible: formatMenu.tableHere; width: parent.width; height: 1; color: pane.c.hairline }
                            OMenuItem { visible: formatMenu.tableHere; text: app.t.table_add_row; iconName: "plus"; onTriggered: text.tableEdit("row") }
                            OMenuItem { visible: formatMenu.tableHere; text: app.t.table_add_column; iconName: "plus"; onTriggered: text.tableEdit("column") }
                            OMenuItem { visible: formatMenu.tableHere; text: app.t.table_delete_row; iconName: "trash"; onTriggered: text.tableEdit("deleteRow") }
                            OMenuItem { visible: formatMenu.tableHere; text: app.t.table_delete_column; iconName: "trash"; onTriggered: text.tableEdit("deleteColumn") }
                        }
                    }
                    OButton { kind: "quiet"; implicitWidth: 36; iconName: "checklist"; tip: app.t.checklist + "  (Ctrl+Maj+L)"; onClicked: { text.toggleChecklist(); pane.focusText() } }
                    OButton { kind: "quiet"; implicitWidth: 36; iconName: "table"; tip: app.t.table; onClicked: { text.insertTable(); pane.focusText() } }
                    OButton { kind: "quiet"; implicitWidth: 36; iconName: "image"; tip: app.t.attach; onClicked: filePicker.open() }
                    Rectangle { implicitWidth: 1; implicitHeight: 22; color: pane.c.line; Layout.leftMargin: 6; Layout.rightMargin: 6 }
                    OButton {
                        id: ornisButton
                        kind: "quiet"; iconName: "ornis"; text: pane.width > 640 ? "Ornis" : ""; tip: app.t.ornis_tip
                        onClicked: ornisMenu.open()
                        OMenu {
                            id: ornisMenu
                            y: ornisButton.height + 6
                            implicitWidth: 300
                            heading: app.t.ornis_menu
                            subheading: text.area.selectedText ? app.t.ornis_menu_part : app.t.ornis_menu_lead
                            OMenuItem { text: app.t.ornis_summary; iconName: "sparkle"; onTriggered: pane.ornisRequested("summary") }
                            OMenuItem { text: app.t.ornis_tidy; iconName: "sparkle"; onTriggered: pane.ornisRequested("tidy") }
                            OMenuItem { text: app.t.ornis_proofread; iconName: "check"; onTriggered: pane.ornisRequested("proofread") }
                            OMenuItem { text: app.t.ornis_concise; iconName: "sparkle"; onTriggered: pane.ornisRequested("concise") }
                            OMenuItem { text: app.t.ornis_checklist; iconName: "checklist"; onTriggered: pane.ornisRequested("checklist") }
                            OMenuItem { text: app.t.ornis_tasks; iconName: "bell"; onTriggered: pane.ornisRequested("tasks") }
                            OMenuItem { text: app.t.ornis_translate; iconName: "globe"; onTriggered: pane.ornisRequested("translate") }
                            OMenuItem { text: app.t.ornis_continue; iconName: "edit"; onTriggered: pane.ornisRequested("continue") }
                            Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                            OMenuItem { text: app.t.ornis_ask; iconName: "search"; onTriggered: pane.askRequested() }
                        }
                    }
                }

                RowLayout {
                    visible: pane.trashed
                    spacing: 6
                    Layout.leftMargin: 6
                    OButton { kind: "secondary"; iconName: "restore"; text: app.t.restore; onClicked: notes.restore([pane.key]) }
                    OButton { kind: "quiet"; iconName: "trash"; danger: true; text: app.t.delete_forever; onClicked: pane.deleteRequested([pane.key]) }
                }

                Item { Layout.fillWidth: true }

                OButton {
                    id: outlineButton
                    property var rows: []
                    visible: pane.key !== "" && !pane.trashed
                    kind: "quiet"; implicitWidth: 36; iconName: "list"; tip: app.t.outline
                    onClicked: { rows = pane.headings(); outlineMenu.open() }
                    OMenu {
                        id: outlineMenu
                        y: outlineButton.height + 6
                        x: outlineButton.width - width
                        implicitWidth: 300
                        heading: app.t.outline
                        subheading: outlineButton.rows.length ? "" : app.t.outline_none
                        Repeater {
                            model: outlineButton.rows
                            OMenuItem {
                                required property var modelData
                                text: "\u2003".repeat(Math.max(0, modelData.level - 1)) + modelData.title
                                onTriggered: pane.goTo(modelData.pos)
                            }
                        }
                    }
                }
                OButton {
                    visible: pane.key !== "" && !pane.trashed && (pane.d.rid || 0) > 0
                    kind: "quiet"; implicitWidth: 36; iconName: "history"; tip: app.t.versions
                    enabled: notes.online
                    onClicked: { text.flush(); pane.versionsRequested(pane.key) }
                }
                OButton {
                    visible: pane.key !== "" && !pane.trashed
                    kind: "quiet"; implicitWidth: 36
                    iconName: "pushpin"; tip: (pane.d.pinned ? app.t.unpin : app.t.pin) + "  (Ctrl+Maj+P)"
                    onClicked: { notes.togglePin(pane.key); pane.reload() }
                    Rectangle { visible: !!pane.d.pinned; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6; width: 7; height: 7; radius: 3.5; color: pane.c.saffron }
                }
                OButton {
                    id: shareButton
                    visible: pane.key !== "" && !pane.trashed
                    kind: "quiet"; implicitWidth: 36; iconName: "share"; tip: app.t.share
                    onClicked: shareMenu.open()
                    OMenu {
                        id: shareMenu
                        y: shareButton.height + 6
                        x: shareButton.width - width
                        implicitWidth: 290
                        OMenuItem { text: app.t.link_copy; iconName: "link"; onTriggered: notes.copyLinks([pane.key]) }
                        OMenuItem { text: app.t.share_people; iconName: "people"; enabled: notes.online; onTriggered: pane.shareRequested(pane.key) }
                        OMenuItem { text: app.t.share_link; iconName: "share"; enabled: notes.online; onTriggered: notes.shareLink(pane.key) }
                        OMenuItem { text: app.t.share_mail; iconName: "mail"; onTriggered: notes.mail(pane.key) }
                        OMenuItem { text: app.t.share_tasks; iconName: "bell"; onTriggered: pane.tasksRequested(pane.key) }
                        OMenuItem { text: app.t.copy_text; iconName: "copy"; onTriggered: { text.area.selectAll(); text.area.copy(); text.area.deselect(); toastRequest(app.t.copied) } }
                        Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                        OMenuItem { text: app.t.print + "   Ctrl+P"; iconName: "pdf"; onTriggered: { text.flush(); notes.printNote(pane.key) } }
                        OMenuItem { text: app.t.export_pdf; iconName: "pdf"; onTriggered: { exporter.kind = "pdf"; exporter.open() } }
                        OMenuItem { text: app.t.export_md; iconName: "export"; onTriggered: { exporter.kind = "md"; exporter.open() } }
                        OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: notes.openInCloud(pane.key) }
                    }
                }
                OButton {
                    visible: pane.key !== "" && !pane.trashed && !pane.d.readonly
                    kind: "quiet"; implicitWidth: 36; iconName: "trash"; danger: true; tip: app.t.delete_note + "  (Suppr)"
                    onClicked: pane.deleteRequested([pane.key])
                }
            }
        }

        // ---- find (and replace) in the note ---------------------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 8
            visible: pane.findOpen && pane.key !== ""
            implicitHeight: findColumn.implicitHeight + 16
            radius: 10
            color: pane.c.card
            border.width: 1; border.color: pane.c.line
            ColumnLayout {
                id: findColumn
                anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 8
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    OTextField {
                        id: findField
                        Layout.fillWidth: true
                        iconName: "search"
                        placeholderText: app.t.find_in_note
                        onTextChanged: text.setFind(findField.text)
                        Keys.onReturnPressed: event => text.findStep(!!(event.modifiers & Qt.ShiftModifier))
                        Keys.onEnterPressed: event => text.findStep(!!(event.modifiers & Qt.ShiftModifier))
                        Keys.onEscapePressed: pane.closeFind()
                    }
                    Text {
                        visible: findField.text !== ""
                        text: text.found.length ? (text.found.indexOf(text.foundAt) + 1) + "/" + text.found.length : app.t.find_none
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: text.found.length ? pane.c.muted : pane.c.danger
                        Layout.rightMargin: 4
                    }
                    OButton { kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "chevronLeft"; tip: app.t.find_previous + "  (Maj+Entrée)"; enabled: text.found.length > 0; onClicked: text.findStep(true) }
                    OButton { kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "chevronRight"; tip: app.t.find_next + "  (Entrée)"; enabled: text.found.length > 0; onClicked: text.findStep(false) }
                    OButton { visible: pane.editable; kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "repeat"; tip: app.t.replace + "  (Ctrl+H)"; onClicked: pane.replaceOpen = !pane.replaceOpen }
                    OButton { kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "close"; iconSize: 14; tip: app.t.close; onClicked: pane.closeFind() }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: pane.replaceOpen && pane.editable
                    spacing: 6
                    OTextField {
                        id: replaceField
                        Layout.fillWidth: true
                        iconName: "edit"
                        clearable: true
                        placeholderText: app.t.replace_with
                        Keys.onReturnPressed: text.replaceOne(replaceField.text)
                        Keys.onEscapePressed: pane.closeFind()
                    }
                    OButton { text: app.t.replace; enabled: text.foundAt >= 0; onClicked: text.replaceOne(replaceField.text) }
                    OButton {
                        text: app.t.replace_all; enabled: text.found.length > 0
                        onClicked: { const n = text.replaceAll(replaceField.text); if (n) toastRequest(app.plural("replaced_count", n)) }
                    }
                }
            }
        }

        // ---- the note -------------------------------------------------------------------------------------
        // the note: a sheet on the page, the family colour fading in at its top
        Surface {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 16
            visible: pane.key !== ""
            Rectangle {
                z: 2
                x: 12; width: Math.min(parent.width - 24, 260); height: 3; radius: 1.5
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: pane.c.famDocs }
                    GradientStop { position: 1; color: Qt.alpha(pane.c.famDocs, 0) }
                }
            }
        NoteText {
            id: text
            anchors.fill: parent
            visible: pane.key !== ""
            helper: editorHelper
            readOnly: !pane.editable
            header: Column {
                width: text.width
                topPadding: 18; bottomPadding: 10
                spacing: 10
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: pane.trashed ? app.t.deleted_on.replace("%1", app.long(pane.d.modified))
                                       : app.long(pane.d.modified) + (pane.d.words ? "  ·  " + app.plural("words_count", pane.d.words) : "")
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: pane.c.faint
                    HoverHandler { id: dateHover }
                    ToolTip.visible: dateHover.hovered && !pane.trashed && !!pane.d.created
                    ToolTip.delay: 500
                    ToolTip.text: app.t.created_on.replace("%1", app.long(pane.d.created || 0))
                                  + (pane.d.total ? "\n" + app.t.checks_done.replace("%1", pane.d.done).replace("%2", pane.d.total) : "")
                }
                // a sync kept two versions: which one is which, and a way to compare and choose
                Rectangle {
                    id: conflictBanner
                    readonly property bool isCopy: !!(pane.d.conflictOf || {}).key
                    readonly property var copies: pane.d.conflictCopies || []
                    visible: !pane.trashed && (isCopy || copies.length > 0)
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(parent.width - 56, conflictRow.implicitWidth + 24)
                    height: conflictRow.implicitHeight + 14
                    radius: 8
                    color: pane.c.saffronTint
                    RowLayout {
                        id: conflictRow
                        anchors.centerIn: parent
                        width: Math.min(implicitWidth, conflictBanner.width - 24)
                        spacing: 10
                        Icon { name: "warning"; size: 16; color: pane.c.saffronInk }
                        Text {
                            Layout.fillWidth: true
                            text: conflictBanner.isCopy ? app.t.conflict_copy_banner.replace("%1", (pane.d.conflictOf || {}).title || "")
                                                        : app.t.conflict_original_banner
                            wrapMode: Text.WordWrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: pane.c.saffronInk
                        }
                        OButton {
                            kind: "secondary"; height_: 28; text: app.t.conflict_compare
                            onClicked: pane.conflictRequested(conflictBanner.isCopy ? pane.key : conflictBanner.copies[0].key)
                        }
                    }
                }
                Rectangle {
                    visible: !!pane.d.readonly && !pane.trashed || pane.trashed
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(parent.width - 56, banner.implicitWidth + 28)
                    height: banner.implicitHeight + 16
                    radius: 8
                    color: pane.c.saffronTint
                    Row {
                        id: banner
                        anchors.centerIn: parent
                        spacing: 8
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: pane.trashed ? "trash" : "lock"; size: 16; color: pane.c.saffronInk }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: pane.trashed ? (pane.d.loading ? app.t.loading_deleted : app.t.trashed_banner) : app.t.readonly_banner
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: pane.c.saffronInk
                        }
                    }
                }
            }
            footer: Column {
                width: text.width
                bottomPadding: 40
                spacing: 18
            Flow {
                width: parent.width
                leftPadding: text.area.side; rightPadding: text.area.side
                spacing: 12
                visible: (pane.d.images || []).length > 0
                Repeater {
                    model: pane.d.images || []
                    AbstractButton {
                        id: shot
                        required property var modelData
                        width: Math.min(260, (text.width - 2 * text.area.side - 12) / 2)
                        height: width * 0.68
                        hoverEnabled: true
                        Accessible.name: modelData.alt || app.t.image
                        onClicked: notes.openAttachment(pane.key, modelData.ref)
                        ToolTip.text: app.t.image_open
                        ToolTip.visible: hovered
                        ToolTip.delay: 600
                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: attachmentMenu.openFor(shot.modelData.ref, true, shot) }
                        OButton {
                            id: shotMore
                            visible: shot.hovered || attachmentMenu.opened && attachmentMenu.ref === shot.modelData.ref
                            z: 3
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 6
                            kind: "secondary"; implicitWidth: 30; height_: 30; iconName: "more"; iconSize: 15; tip: app.t.more
                            onClicked: attachmentMenu.openFor(shot.modelData.ref, true, shotMore)
                        }
                        background: Rectangle {
                            radius: 10
                            color: pane.c.card
                            border.width: 1; border.color: shot.hovered ? pane.c.accentLine : pane.c.line
                            clip: true
                            Image {
                                id: picture
                                anchors.fill: parent; anchors.margins: 1
                                source: shot.modelData.url || ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                sourceSize.width: 520
                            }
                            Column {
                                anchors.centerIn: parent
                                visible: picture.status !== Image.Ready
                                spacing: 6
                                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "image"; size: 26; color: pane.c.faint }
                                Text {
                                    text: shot.modelData.url ? "" : (notes.online ? app.t.image_loading : app.t.image_offline)
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: pane.c.faint
                                }
                            }
                        }
                    }
                }
            }
            // the other files of the note (a PDF, a document): open, save, take out
            Flow {
                width: parent.width
                leftPadding: text.area.side; rightPadding: text.area.side
                spacing: 8
                visible: (pane.d.files || []).length > 0
                Repeater {
                    model: pane.d.files || []
                    AbstractButton {
                        id: fileChip
                        required property var modelData
                        implicitHeight: 34
                        implicitWidth: Math.min(300, fileRow.implicitWidth + 24)
                        hoverEnabled: true
                        onClicked: notes.openAttachment(pane.key, modelData.ref)
                        background: Rectangle { radius: 8; color: fileChip.hovered ? pane.c.hover : pane.c.card; border.width: 1; border.color: pane.c.line }
                        contentItem: Row {
                            id: fileRow
                            spacing: 8
                            leftPadding: 12
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: "clip"; size: 15; color: pane.c.muted }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(implicitWidth, 240)
                                text: fileChip.modelData.name
                                elide: Text.ElideMiddle
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                color: pane.c.text
                            }
                        }
                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: attachmentMenu.openFor(fileChip.modelData.ref, false, fileChip) }
                    }
                }
            }
            // the notes that link to this one
            Column {
                x: text.area.side
                width: parent.width - 2 * text.area.side
                spacing: 4
                visible: !pane.trashed && (pane.d.backlinks || []).length > 0
                Text {
                    text: app.t.backlinks
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                    font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                    color: pane.c.muted
                    bottomPadding: 2
                }
                Repeater {
                    model: pane.d.backlinks || []
                    AbstractButton {
                        id: back
                        required property var modelData
                        implicitHeight: 30
                        implicitWidth: backRow.implicitWidth + 16
                        hoverEnabled: true
                        onClicked: pane.openRequested(modelData.key)
                        background: Rectangle { radius: 7; color: back.hovered ? pane.c.hover : "transparent" }
                        contentItem: Row {
                            id: backRow
                            spacing: 8
                            leftPadding: 8
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: "note"; size: 15; color: pane.c.tintText }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: back.modelData.title
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                color: pane.c.tintText
                            }
                        }
                    }
                }
            }
            }
        }
        }

        EmptyState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: pane.key === ""
            iconName: "note"
            title: notes.items.length ? app.t.pick_note : app.t.no_note_title
            lead: notes.items.length ? "" : app.t.no_note_lead
            actionText: notes.folder === "trash" ? "" : app.t.new_note
            actionIcon: "compose"
            onActivated: newNoteRequested()
        }
    }
    signal newNoteRequested()
    signal toastRequest(string message)

    DropArea {
        anchors.fill: parent
        enabled: pane.editable
        onDropped: drop => {
            // a mail (Plume), a task (Tâches) or a note (the list): a link where it was dropped
            if (drop.formats.indexOf("application/x-orneos-link") >= 0) {
                const link = notes.linksMarkdown(drop.getDataAsString("application/x-orneos-link"), pane.key)
                if (link) {
                    const p = pane.mapToItem(text.area, drop.x, drop.y)
                    text.insertLinkAt(text.area.positionAt(p.x, p.y), link)
                    drop.acceptProposedAction()
                }
                return
            }
            if (!drop.hasUrls) return
            const md = notes.attach(pane.key, drop.urls)
            if (md) { text.insertAtCursor(md); pane.reload() }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 10
            visible: parent.containsDrag
            radius: 12; color: "transparent"
            border.width: 2; border.color: pane.c.accent
            Rectangle { anchors.fill: parent; radius: 12; color: pane.c.tint; opacity: 0.35 }
        }
    }

    // « Lier à… » (Ctrl+Maj+K): a note, a task or a mail, as a chip at the cursor
    LinkPicker {
        id: linkPicker
        search: q => notes.linkCandidates(q)
        onPicked: item => {
            text.insertLinkAt(text.area.cursorPosition, notes.linksMarkdown(JSON.stringify([item]), pane.key))
            pane.focusText()
        }
    }
    Connections {
        target: text
        function onLinkRequested() { if (pane.editable) linkPicker.start() }
    }

    FileDialog {
        id: filePicker
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.attach
        fileMode: FileDialog.OpenFiles
        onAccepted: {
            const md = notes.attach(pane.key, selectedFiles)
            if (md) { text.insertAtCursor(md); pane.reload() }
        }
    }
    FileDialog {
        id: exporter
        property string kind: "pdf"
        fileMode: FileDialog.SaveFile
        title: kind === "pdf" ? app.t.export_pdf : app.t.export_md
        nameFilters: kind === "pdf" ? ["PDF (*.pdf)"] : ["Markdown (*.md)"]
        defaultSuffix: kind === "pdf" ? "pdf" : "md"
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.DocumentsLocation)
        selectedFile: Std.StandardPaths.writableLocation(Std.StandardPaths.DocumentsLocation) + "/" + encodeURIComponent(notes.exportName(pane.key).split(/[\\/]/).pop() + (kind === "pdf" ? ".pdf" : ".md"))
        onAccepted: toastRequest(notes.exportFile(pane.key, selectedFile.toString()) ? app.t.exported : app.t.export_failed)
    }

    // a picture or a file of the note: open, save, copy, take out
    OMenu {
        id: attachmentMenu
        property string ref
        property bool image
        implicitWidth: 260
        function openFor(r, isImage, item) {
            ref = r
            image = isImage
            const p = item.mapToItem(pane, item.width / 2, item.height / 2)
            x = Math.min(p.x, pane.width - implicitWidth - 12); y = p.y
            open()
        }
        OMenuItem { text: app.t.image_open; iconName: "openExternal"; onTriggered: notes.openAttachment(pane.key, attachmentMenu.ref) }
        OMenuItem { text: app.t.save_as; iconName: "download"; onTriggered: { saver.ref = attachmentMenu.ref; saver.open() } }
        OMenuItem { visible: attachmentMenu.image; text: app.t.image_copy; iconName: "copy"; onTriggered: notes.copyImage(pane.key, attachmentMenu.ref) }
        OMenuItem { visible: pane.editable; text: app.t.attachment_remove; iconName: "trash"; danger: true; onTriggered: pane.removeAttachment(attachmentMenu.ref) }
    }
    FileDialog {
        id: saver
        property string ref
        fileMode: FileDialog.SaveFile
        title: app.t.save_as
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.DownloadLocation)
        selectedFile: Std.StandardPaths.writableLocation(Std.StandardPaths.DownloadLocation) + "/" + encodeURIComponent(notes.attachmentName(ref))
        onAccepted: notes.saveAttachment(pane.key, ref, selectedFile.toString())
    }

    // what Ornis wrote, to put in the note (QML calls these from OrnisPanel)
    function replaceText(content) {
        text.area.selectAll()
        text.area.remove(0, text.area.length)
        text.area.insert(0, content)
        text.flush()
    }
    function insertBelowTitle(content) {
        const t = text.area.text
        const first = t.indexOf("\n")
        const at = first < 0 ? t.length : first
        text.area.insert(at, "\n\n" + content.trim() + "\n")
        text.flush()
    }
    function currentText() { return text.area.text }
    function undo() { text.area.undo(); text.flush() }
}
