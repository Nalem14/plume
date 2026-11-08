// The opened message: actions, subject, sender, what was blocked, attachments, then the body in
// Chromium without JavaScript (links open in the browser). HTML mail stays on white paper in the dark.
// A conversation shows all its messages on one page, newest first (older ones folded, a click unfolds
// them); each has its reply buttons and attachments, caught here as links to plume.invalid.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtWebEngine
import "../components"
import "../contacts"

Rectangle {
    id: reader
    readonly property var c: theme.c
    readonly property var m: mail.current
    readonly property var loc: Qt.locale(plume.locale)
    readonly property bool thread: (m.count || 1) > 1
    // many files (pictures sent again with each reply): the first ones, the rest behind « +N autres »
    readonly property var files: m.attachments || []
    property bool allFiles
    readonly property bool narrow: width < 560          // toolbar buttons keep their icon only
    signal replyRequested(string mode, int messageId)
    signal draftRequested()
    signal replyWithText(string text)
    signal actionRequested(string role)
    signal closeRequested()
    signal snoozeRequested(var anchor)
    property int shownId: 0
    property string shownMid
    property bool summarised
    // the letter sits on a card over the page; the actions above it, quiet but one (Répondre)
    color: c.bg

    function ornisRun(kind) { ornisPanel.run(kind) }
    // what is shown (the message or the whole conversation) as a PDF, opened by the computer to print it
    function printMessage() {
        if (!m.messageId || m.loading || !bodyLoader.item)
            return
        bodyLoader.item.printToPdf(mail.printFile())
    }

    // Leaving a mailing list: what will happen is said first, then the button follows (working, done).
    component UnsubscribeButton: OButton {
        readonly property var u: reader.m.unsubscribe || {}
        visible: !!(u.https || u.mailto)
        enabled: u.state !== "working" && u.state !== "done"
        height_: 28
        kind: u.state === "done" ? "quiet" : "accent"
        iconName: u.state === "done" ? "check" : ""
        text: u.state === "working" ? plume.t.unsub_working : u.state === "done" ? plume.t.unsub_done : plume.t.unsubscribe
        onClicked: {
            const sender = (reader.m.from || {}).name || (reader.m.from || {}).email || ""
            confirm.ask(plume.t.unsub_title.replace("%1", sender),
                        u.oneClick ? plume.t.unsub_oneclick : u.mailto ? plume.t.unsub_mailto : plume.t.unsub_page,
                        [{ id: "cancel", text: plume.t.cancel }, { id: "go", text: plume.t.unsubscribe, kind: "primary" }],
                        () => mail.unsubscribe())
        }
    }

    // Text of the heading that the mouse selects. People are mailto: links: a click offers to write to them
    // or copy their address; a right click also copies the selection, or all of it.
    component Selectable: TextEdit {
        id: selectable
        readOnly: true
        selectByMouse: true
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"
        color: reader.c.text
        selectionColor: reader.c.accentLine
        selectedTextColor: reader.c.text
        onLinkActivated: link => textMenu.openAt(selectable, hover.point.position.x, hover.point.position.y + 8, link, false)
        HoverHandler { id: hover; cursorShape: selectable.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor }
        TapHandler {
            acceptedButtons: Qt.RightButton
            onTapped: (point) => textMenu.openAt(selectable, point.position.x, point.position.y,
                                                 selectable.linkAt(point.position.x, point.position.y), true)
        }
    }

    // someone of the heading, as rich text: the name, then the address (muted), the whole a link
    function esc(text) {
        return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }
    function person(a, strong, withAddress) {
        const email = a.email || "", name = (a.name || "").trim()
        const label = esc(name || email)
        return "<a href=\"mailto:" + encodeURIComponent(email).replace(/%40/g, "@") + "\" style=\"color:" + c.text + "; text-decoration:none\">"
             + (strong ? "<b>" + label + "</b>" : label)
             + (withAddress && name && name !== email ? " <span style=\"color:" + c.muted + "\">&lt;" + esc(email) + "&gt;</span>" : "")
             + "</a>"
    }
    // « À  Anne <anne@…>, Paul <paul@…> »: addresses shown while the list is short
    function peopleLine(label, list) {
        const all = list || []
        return "<span style=\"color:" + c.muted + "\">" + esc(label) + "</span>&nbsp; "
             + all.map(a => person(a, false, all.length <= 3)).join(", ")
    }
    function nameOf(email) {
        const all = [m.from || {}].concat(m.to || [], m.cc || [], m.bcc || [], m.replyTo || [])
        const found = all.find(a => (a.email || "").toLowerCase() === email.toLowerCase())
        return found && found.name && found.name !== email ? found.name : ""
    }
    // the Reply-To of the message when it is not its sender (help desks, mailing lists)
    readonly property var replyTo: (m.replyTo || []).filter(a => (a.email || "").toLowerCase() !== ((m.from || {}).email || "").toLowerCase())

    // a new message: Ornis starts over. A summary already made this session comes back as is; with the
    // option on, a long message is summarised on its own, only the first time it is read (not when a
    // message already read is opened again).
    function messageChanged() {
        // another message, or another one under the same number (the cache reuses the number of a deleted one)
        if (m.messageId !== shownId || (m.mid && shownMid && m.mid !== shownMid)) {
            shownId = m.messageId || 0
            shownMid = m.mid || ""
            summarised = false
            allFiles = false
            head.contentY = 0
            ornisPanel.reset()
        }
        if (m.mid)
            shownMid = m.mid
        if (summarised || m.loading || m.failed || m.partial || !m.messageId)
            return
        summarised = true
        if (ornisPanel.showCached("summary"))
            return
        if (ornis.autoSummary && m.wasUnseen && m.role !== "drafts" && m.role !== "sent"
                && (m.threadText || m.text || "").length > 600)
            ornisPanel.run("summary")
    }

    function size(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1).replace(".", plume.lang === "en" ? "." : ",") + (plume.lang === "fr" ? " Mo" : " MB")
        return Math.max(1, Math.round(bytes / 1024)) + (plume.lang === "fr" ? " Ko" : " KB")
    }
    // a link of the conversation page: https://plume.invalid/<action>?m=<id>[&i=<attachment>]
    function pageAction(url) {
        const match = String(url).match(/^https:\/\/plume\.invalid\/(\w+)\?m=(\d+)(?:&i=(\d+))?/)
        if (!match)
            return null
        return { action: match[1], id: parseInt(match[2]), index: match[3] !== undefined ? parseInt(match[3]) : -1 }
    }
    function runPageAction(a) {
        if (a.action === "attachment")
            mail.openAttachment(a.index, a.id)
        else if (a.action === "reply" || a.action === "all" || a.action === "forward")
            reader.replyRequested(a.action, a.id)
    }

    Text {
        anchors.centerIn: parent
        visible: !reader.m.messageId
        text: plume.t.pick_message
        font.family: "Schibsted Grotesk"; font.pixelSize: 16
        color: reader.c.muted
    }

    ColumnLayout {
        anchors.fill: parent
        visible: !!reader.m.messageId
        spacing: 0

        // actions
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: "transparent"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: reader.narrow ? 12 : 16; anchors.rightMargin: 12
                spacing: reader.narrow ? 4 : 6
                OButton { visible: reader.m.role !== "drafts"; kind: "primary"; iconName: "reply"; text: reader.narrow ? "" : plume.t.reply; tip: plume.t.reply + "  (R)"; onClicked: reader.replyRequested("reply", 0) }
                OButton { visible: reader.m.role !== "drafts"; kind: "quiet"; iconName: "replyAll"; tip: plume.t.reply_all + "  (Maj+R)"; implicitWidth: 36; onClicked: reader.replyRequested("all", 0) }
                OButton { visible: reader.m.role !== "drafts"; kind: "quiet"; iconName: "forward"; tip: plume.t.forward + "  (F)"; implicitWidth: 36; onClicked: reader.replyRequested("forward", 0) }
                OButton { visible: reader.m.role === "drafts"; kind: "primary"; iconName: "draft"; text: plume.t.draft_continue; onClicked: reader.draftRequested() }
                OButton {
                    id: ornisButton
                    visible: reader.m.role !== "drafts"
                    kind: "accent"; iconName: "ornis"; text: reader.narrow ? "" : plume.t.ornis
                    tip: plume.t.ornis_on_message
                    onClicked: ornisMenu.open()
                    OMenu {
                        id: ornisMenu
                        y: ornisButton.height + 6
                        OMenuItem { text: reader.thread ? plume.t.ornis_summarize_thread : plume.t.ornis_summarize; iconName: "sparkle"; onTriggered: ornisPanel.run("summary") }
                        OMenuItem { text: plume.t.ornis_replies; iconName: "reply"; onTriggered: ornisPanel.run("replies") }
                        OMenuItem { text: plume.t.ornis_find_event; iconName: "calendar"; onTriggered: ornisPanel.run("mailEvent") }
                        // the conversation beside (Ctrl+J), with this message; without the Ornis module, the one question here
                        OMenuItem { visible: suite.ornisPanel; text: plume.t.ornis_chat_message; iconName: "chat"; onTriggered: win.toggleOrnis(true) }
                        OMenuItem { visible: !suite.ornisPanel; text: plume.t.ornis_ask; iconName: "ornis"; onTriggered: ornisPanel.run("question") }
                    }
                }
                Rectangle { implicitWidth: 1; implicitHeight: 22; color: reader.c.line; Layout.leftMargin: reader.narrow ? 0 : 4; Layout.rightMargin: reader.narrow ? 0 : 4 }
                OButton { visible: reader.m.role !== "archive"; kind: "quiet"; iconName: "archive"; tip: plume.t.archive + "  (E)"; implicitWidth: 36; onClicked: reader.actionRequested("archive") }
                OButton {
                    kind: "quiet"; iconName: "trash"; implicitWidth: 36; danger: true
                    tip: (reader.m.role === "trash" ? plume.t.delete_forever : plume.t.delete) + "  (" + plume.t.key_delete + ")"
                    onClicked: reader.actionRequested("trash")
                }
                OButton {
                    kind: "quiet"; iconName: "spam"; implicitWidth: 36; danger: reader.m.role !== "junk"
                    tip: reader.m.role === "junk" ? plume.t.not_spam : plume.t.spam_report
                    onClicked: reader.actionRequested(reader.m.role === "junk" ? "inbox" : "junk")
                }
                OButton {
                    id: snoozeButton
                    visible: ["trash", "junk", "drafts"].indexOf(reader.m.role) < 0
                    kind: "quiet"; iconName: "history"; implicitWidth: 36
                    tip: plume.t.snooze
                    onClicked: reader.snoozeRequested(snoozeButton)
                }
                OButton {
                    id: moreButton
                    kind: "quiet"; iconName: "more"; implicitWidth: 36
                    tip: plume.t.more_actions
                    onClicked: moreMenu.openFor({ messageId: reader.m.messageId, seen: true, flagged: reader.m.flagged,
                                                  tags: reader.m.tags, box: reader.m.box, role: reader.m.role },
                                                moreButton, 0, moreButton.height + 6)
                    MessageMenu {
                        id: moreMenu
                        full: false
                        attachments: (reader.m.attachments || []).length
                        onActionRequested: role => reader.actionRequested(role)
                        onSnoozeRequested: leads => reader.snoozeRequested(moreButton)
                        onSeenToggled: seen => { if (!seen) reader.closeRequested() }
                        onExtraRequested: kind => {
                            if (kind === "print")
                                reader.printMessage()
                            else if (kind === "source")
                                mail.showSource(reader.m.messageId)
                            else if (kind === "eml") {
                                emlDialog.selectedFile = "file:///" + mail.messageFileName(reader.m.messageId)
                                emlDialog.open()
                            } else if (kind === "attachments")
                                folderDialog.open()
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                AbstractButton {
                    id: star
                    implicitWidth: 36; implicitHeight: 34
                    hoverEnabled: true
                    Accessible.name: plume.t.star
                    Accessible.checked: !!reader.m.flagged
                    ToolTip.text: (reader.m.flagged ? plume.t.unstar : plume.t.star) + "  (S)"
                    ToolTip.delay: 450
                    ToolTip.visible: hovered
                    onClicked: mail.setFlagged(reader.m.messageId, !reader.m.flagged)
                    background: Rectangle { radius: 6; color: star.hovered ? reader.c.hover : "transparent" }
                    contentItem: Item {
                        Icon { anchors.centerIn: parent; name: "star"; size: 20; color: reader.m.flagged ? reader.c.saffron : reader.c.muted }
                    }
                }
                OButton {
                    kind: "quiet"; iconName: "close"; iconSize: 14; implicitWidth: 34
                    tip: plume.t.close_message + "  (" + plume.t.key_escape + ")"
                    onClicked: reader.closeRequested()
                }
            }
        }

        // One scroll for everything under the actions, as in a single page: the heading goes up first,
        // then the body (the size of the reader when it is long) scrolls in Chromium.
        Surface {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: reader.narrow ? 8 : 16; Layout.rightMargin: reader.narrow ? 8 : 16; Layout.bottomMargin: 16
            // the family colour fades in at the top of the letter
            Rectangle {
                z: 2
                x: 12; width: Math.min(parent.width - 24, 260); height: 3; radius: 1.5
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: reader.c.famCommunicate }
                    GradientStop { position: 1; color: Qt.alpha(reader.c.famCommunicate, 0) }
                }
            }

        Flickable {
            id: head
            readonly property int side: reader.narrow ? 20 : 32
            readonly property real maxY: Math.max(0, contentHeight - height)
            anchors.fill: parent
            contentHeight: bodyBox.y + bodyBox.height + bodyBox.gap
            interactive: false                  // a drag selects text; the wheel is handled below
            clip: true
            ScrollBar.vertical: ScrollBar {}
            // what Ornis just started is brought into view
            function showOrnis() {
                Qt.callLater(() => head.contentY = Math.max(0, Math.min(heading.y + ornisPanel.y - 12, head.maxY)))
            }

        ColumnLayout {
            id: heading
            x: head.side; y: 20
            width: head.width - 2 * head.side
            spacing: 14
            Selectable {
                Layout.fillWidth: true
                text: reader.m.subject || plume.t.subject_empty
                font.pixelSize: 24; font.weight: Font.Bold; font.letterSpacing: -0.3
            }
            // its tags (the « ⋯ » menu sets them); the cross takes one off
            Flow {
                visible: (reader.m.tags || []).length > 0
                Layout.fillWidth: true
                Layout.topMargin: -6
                spacing: 6
                Repeater {
                    model: reader.m.tags || []
                    Rectangle {
                        id: chip
                        required property int modelData
                        height: 24; radius: 12
                        width: chipRow.implicitWidth + 16
                        color: reader.c.bg
                        border.width: 1; border.color: reader.c.line
                        Row {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: reader.c["tag" + chip.modelData] }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: plume.t["tag_" + chip.modelData]; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium; color: reader.c.text }
                            AbstractButton {
                                id: untag
                                anchors.verticalCenter: parent.verticalCenter
                                width: 16; height: 16
                                hoverEnabled: true
                                Accessible.name: plume.t.tag_remove
                                ToolTip.text: plume.t.tag_remove; ToolTip.visible: hovered; ToolTip.delay: 450
                                onClicked: mail.setTag(reader.m.messageId, chip.modelData, false)
                                background: Rectangle { radius: 8; color: untag.hovered ? reader.c.hover : "transparent" }
                                contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 8; color: untag.hovered ? reader.c.text : reader.c.faint } }
                            }
                        }
                    }
                }
            }
            // a conversation: who writes in it and how many messages (each sender is on the page)
            RowLayout {
                visible: reader.thread
                Layout.fillWidth: true
                Layout.topMargin: -6
                spacing: 10
                Selectable {
                    Layout.fillWidth: true
                    text: (reader.m.participants || []).join(", ") + "  ·  " + plume.t.thread_count.replace("%1", reader.m.count || 0)
                    font.pixelSize: 14
                    color: reader.c.muted
                }
                UnsubscribeButton {}
            }
            RowLayout {
                visible: !reader.thread
                Layout.fillWidth: true
                spacing: 12
                Avatar {
                    Layout.alignment: Qt.AlignTop
                    initials: ((reader.m.from || {}).name || (reader.m.from || {}).email || "?").split(/[\s@.]+/).filter(x => x).slice(0, 2).map(x => x[0].toUpperCase()).join("")
                    tint: 1
                    size: 40
                }
                // who wrote it, to whom (To, Cc, and Bcc in my own copies) and where answers go when it is not the sender
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Selectable {
                        Layout.fillWidth: true
                        textFormat: TextEdit.RichText
                        text: reader.person(reader.m.from || {}, true, true)
                        font.pixelSize: 15
                    }
                    Selectable {
                        visible: (reader.m.to || []).length > 0
                        Layout.fillWidth: true
                        textFormat: TextEdit.RichText
                        text: reader.peopleLine(plume.t.to_label, reader.m.to)
                        font.pixelSize: 14
                    }
                    Selectable {
                        visible: (reader.m.cc || []).length > 0
                        Layout.fillWidth: true
                        textFormat: TextEdit.RichText
                        text: reader.peopleLine(plume.t.cc_label, reader.m.cc)
                        font.pixelSize: 14
                    }
                    Selectable {
                        visible: (reader.m.bcc || []).length > 0
                        Layout.fillWidth: true
                        textFormat: TextEdit.RichText
                        text: reader.peopleLine(plume.t.bcc_label, reader.m.bcc)
                        font.pixelSize: 14
                    }
                    Selectable {
                        visible: reader.replyTo.length > 0
                        Layout.fillWidth: true
                        textFormat: TextEdit.RichText
                        text: reader.peopleLine(plume.t.reply_to_label, reader.replyTo)
                        font.pixelSize: 14
                    }
                }
                UnsubscribeButton { Layout.alignment: Qt.AlignTop }
                Selectable {
                    visible: !!reader.m.date
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 3
                    wrapMode: Text.NoWrap
                    text: reader.m.date ? reader.loc.toString(new Date(reader.m.date), "ddd d MMM · HH:mm") : ""
                    font.family: "JetBrains Mono"; font.pixelSize: 12
                    color: reader.c.muted
                }
            }

            // a sender who may not be who they say (a mail server said so, or the name is another address)
            Rectangle {
                visible: !!reader.m.warning
                Layout.fillWidth: true
                implicitHeight: warnRow.implicitHeight + 16
                radius: 8
                color: reader.c.saffronTint
                RowLayout {
                    id: warnRow
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    spacing: 10
                    Icon { name: "warning"; size: 18; color: reader.c.saffronInk; Layout.alignment: Qt.AlignTop; Layout.topMargin: 1 }
                    Text {
                        Layout.fillWidth: true
                        text: reader.m.warning ? plume.t["sender_warning_" + reader.m.warning] || "" : ""
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: reader.c.saffronInk
                    }
                }
            }

            // an invitation (its calendar part): answer it, add it, see it in the calendar
            InvitationCard {
                Layout.fillWidth: true
                ics: reader.m.calendar || ""
            }

            // remote content blocked (trackers, mostly)
            Rectangle {
                visible: (reader.m.remote || 0) > 0 && !reader.m.imagesShown
                Layout.fillWidth: true
                implicitHeight: bar.implicitHeight + 14
                radius: 8
                color: reader.c.bg
                border.width: 1; border.color: reader.c.line
                RowLayout {
                    id: bar
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 8
                    spacing: 10
                    Icon { name: "lock"; size: 16; color: reader.c.ok }
                    Text {
                        Layout.fillWidth: true
                        text: plume.t.remote_blocked.replace("%1", reader.m.remote || 0)
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: reader.c.text
                    }
                    OButton { height_: 28; text: plume.t.show_images; onClicked: mail.showImages(false) }
                    OButton { height_: 28; kind: "quiet"; text: reader.thread ? plume.t.always_thread : plume.t.always_sender; onClicked: mail.showImages(true) }
                }
            }

            OrnisPanel {
                id: ornisPanel
                Layout.fillWidth: true
                message: reader.m
                onReplyWith: text => reader.replyWithText(text)
                onModeChanged: if (mode !== "") head.showOrnis()
                onResultChanged: if (result !== null) head.showOrnis()
            }

            // attachments (in a conversation, each message shows its own on the page)
            Flow {
                visible: !reader.thread && reader.files.length > 0
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: reader.thread ? [] : reader.allFiles || reader.files.length <= 5 ? reader.files : reader.files.slice(0, 4)
                    AbstractButton {
                        id: file
                        required property var modelData
                        implicitWidth: fileRow.implicitWidth + 24
                        implicitHeight: 52
                        hoverEnabled: true
                        Accessible.name: modelData.name
                        onClicked: attachmentMenu.openFor(reader.m.messageId, modelData.index, modelData.name, file)
                        background: Rectangle { radius: 10; color: file.hovered ? reader.c.hover : reader.c.card; border.width: 1; border.color: reader.c.line }
                        contentItem: Row {
                            id: fileRow
                            spacing: 10
                            leftPadding: 10
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 34; height: 34; radius: 6
                                color: file.modelData.type.indexOf("pdf") >= 0 ? reader.c.danger : file.modelData.type.indexOf("image") === 0 ? reader.c.saffron
                                     : (file.modelData.type.indexOf("sheet") >= 0 || file.modelData.type.indexOf("excel") >= 0) ? reader.c.ok : reader.c.action
                                Text {
                                    anchors.centerIn: parent
                                    text: (file.modelData.name.split(".").pop() || "").slice(0, 4).toUpperCase()
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 10; font.weight: Font.Bold
                                    color: "white"
                                }
                            }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                Text { text: file.modelData.name; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: reader.c.text; width: Math.min(implicitWidth, 260); elide: Text.ElideMiddle }
                                Text { text: reader.size(file.modelData.size); font.family: "JetBrains Mono"; font.pixelSize: 12; color: reader.c.muted }
                            }
                        }
                    }
                }
                OButton {
                    visible: !reader.thread && !reader.allFiles && reader.files.length > 5
                    kind: "quiet"; height_: 52
                    text: plume.t.files_more.replace("%1", reader.files.length - 4)
                    onClicked: reader.allFiles = true
                }
            }
        }

        // the body (or the conversation): the room left under the heading, or the whole reader once the
        // page is longer than that (the heading then scrolls away). Chromium's size of a page is never
        // smaller than its view, so it only tells "longer"; a new page starts short again.
        Rectangle {
            id: bodyBox
            readonly property int side: reader.thread ? 12 : 20
            readonly property int gap: reader.thread ? 12 : 20
            readonly property real full: head.height - (reader.thread ? 8 : 16) - gap
            property bool tall
            x: side
            y: heading.y + heading.height + (reader.thread ? 8 : 16)
            width: head.width - 2 * side
            height: Math.max(200, tall ? full : head.height - y - gap)
            radius: 10
            color: reader.thread ? reader.c.card : (reader.m.isHtml || !theme.dark ? "#FFFFFF" : reader.c.card)
            border.width: reader.thread || (reader.m.isHtml && theme.dark) ? 0 : 1
            border.color: reader.c.hairline
            clip: true

            // The body in Chromium. PLUME_NO_WEBENGINE=1 (tests in a container, where Chromium does not
            // start) leaves it out: the rest of the reader still renders.
            Loader {
                id: bodyLoader
                anchors.fill: parent
                anchors.margins: 1
                active: !plume.noWebEngine
                sourceComponent: Component {
                WebEngineView {
                    id: web
                    backgroundColor: "transparent"
                    settings.javascriptEnabled: false
                    settings.localContentCanAccessRemoteUrls: false
                    settings.localContentCanAccessFileUrls: false
                    settings.pluginsEnabled: false
                    settings.autoLoadImages: true
                    settings.focusOnNavigationEnabled: false
                    profile: WebEngineProfile { offTheRecord: true; httpCacheType: WebEngineProfile.MemoryHttpCache }
                    property string pageFile            // a large page, loaded from its private file
                    HoverHandler { id: webHover }       // where a click on someone happened, for their menu
                    onContentsSizeChanged: if (contentsSize.height > height + 2) bodyBox.tall = true
                    onPdfPrintingFinished: (path, ok) => { if (ok) mail.openFile(path) }
                    onNavigationRequested: request => {
                        const action = reader.pageAction(request.url)
                        const url = String(request.url)
                        if (action) {
                            request.reject()
                            if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation)
                                reader.runPageAction(action)
                        } else if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation) {
                            if (url.toLowerCase().indexOf("mailto:") === 0)
                                textMenu.openAt(web, webHover.point.position.x, webHover.point.position.y + 8, url, false)
                            else if (url.split("#")[0] !== pageFile)
                                Qt.openUrlExternally(request.url)
                            request.reject()
                        } else if (url.indexOf("data:") !== 0 && url !== "about:blank" && (pageFile === "" || url !== pageFile)) {
                            request.reject()
                        }
                    }
                    onNewWindowRequested: request => {
                        const action = reader.pageAction(request.requestedUrl)
                        if (action) reader.runPageAction(action)
                        else if (String(request.requestedUrl).toLowerCase().indexOf("mailto:") === 0) plume.compose(String(request.requestedUrl))
                        else Qt.openUrlExternally(request.requestedUrl)
                    }
                    onContextMenuRequested: request => {
                        request.accepted = true
                        const action = reader.pageAction(request.linkUrl || "")
                        if (action && action.action === "attachment") {
                            attachmentMenu.openAt(action.id, action.index, request.position.x, request.position.y, web)
                            return
                        }
                        const picture = request.mediaType === ContextMenuRequest.MediaTypeImage ? String(request.mediaUrl || "") : ""
                        textMenu.openAt(web, request.position.x, request.position.y, action ? "" : String(request.linkUrl || ""), true,
                                        picture, request.selectedText !== "")
                    }
                }
                }
            }
            Connections {
                target: mail
                property string shownHtml
                function onCurrentChanged() {
                    reader.messageChanged()
                    // a star, a tag or the unsubscribe button change the message, not its page: no reload
                    const page = mail.current.html || ""
                    if (bodyLoader.item && page !== shownHtml) {
                        shownHtml = page
                        bodyBox.tall = false
                        // past 2 MB, a data: URL shows nothing (a long thread with quotes and pictures)
                        const web = bodyLoader.item
                        web.pageFile = mail.pageUrl(page)
                        if (web.pageFile !== "")
                            web.url = web.pageFile
                        else
                            web.loadHtml(page, "about:blank")
                    }
                }
            }
            BusyIndicator { anchors.centerIn: parent; running: !!reader.m.loading; visible: running }
            // offline, or gone from the server: said, instead of waiting forever
            Column {
                anchors.centerIn: parent
                visible: !!reader.m.failed
                spacing: 12
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: plume.t.load_failed
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15
                    color: reader.c.muted
                }
                OButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    iconName: "refresh"; text: plume.t.retry
                    onClicked: mail.open(reader.m.messageId)
                }
            }
        }
        }

        // The wheel: the heading goes up before the body scrolls, and comes back once the body is back at
        // its top. Over the body otherwise, Chromium scrolls the page.
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            onWheel: wheel => {
                const web = bodyLoader.item
                const at = mapToItem(bodyBox, wheel.x, wheel.y)
                const overBody = !!web && at.x >= 0 && at.y >= 0 && at.x <= bodyBox.width && at.y <= bodyBox.height
                const step = wheel.pixelDelta.y !== 0 ? wheel.pixelDelta.y : wheel.angleDelta.y / 120 * 80
                const pageAtTop = !web || web.scrollPosition.y <= 0
                if (step < 0 && head.contentY < head.maxY - 0.5 || step > 0 && !(overBody && !pageAtTop))
                    head.contentY = Math.max(0, Math.min(head.maxY, head.contentY - step))
                else
                    wheel.accepted = !overBody
            }
        }
        }
    }

    // Someone (a mailto: link of the heading or the page): write to them, copy their address. A right click
    // also copies the selection (in the heading: all of it without one), or the link under the mouse.
    // « Ajouter aux contacts »: Contacts' own editor, the name and address of the message filled in (made on the
    // first use only: Courrier rarely needs it)
    Loader { id: newContact; active: false; sourceComponent: ContactEditor { onSaved: id => { if (id) plume.toast(plume.t.contact_added) } } }
    function addContact(name, email) {
        newContact.active = true
        newContact.item.openNew({ name: name, email: email })
    }

    OMenu {
        id: textMenu
        property var target: null
        property string address
        property string link
        property bool copying
        property string image          // the picture under the mouse (its data: URI or address)
        property bool selection: true  // in the page: something is selected
        property int known: 0          // the address's card in my address books (0: « Ajouter aux contacts »)
        readonly property bool web: !!target && target.triggerWebAction !== undefined
        heading: address !== "" ? reader.nameOf(address) || address : ""
        subheading: address !== "" && reader.nameOf(address) !== "" ? address : ""
        function openAt(item, px, py, url, copy, picture, selected) {
            url = String(url || "")
            image = String(picture || "")
            selection = selected === undefined ? true : selected
            const mailto = url.toLowerCase().indexOf("mailto:") === 0
            address = mailto ? decodeURIComponent(url.slice(7).split("?")[0]) : ""
            link = mailto ? "" : url
            copying = copy
            known = address !== "" ? people.idForEmail(address) : 0
            if (address === "" && !copying)
                return
            target = item
            parent = item
            x = px; y = py
            open()
        }
        OMenuItem { visible: textMenu.address !== ""; text: plume.t.write; iconName: "send"; onTriggered: plume.compose("mailto:" + textMenu.address) }
        OMenuItem { visible: textMenu.address !== ""; text: plume.t.contact_copy_email; iconName: "mail"; onTriggered: plume.copyText(textMenu.address) }
        OMenuItem { visible: textMenu.address !== "" && textMenu.known === 0; text: plume.t.add_to_contacts; iconName: "contacts"
                    onTriggered: reader.addContact(reader.nameOf(textMenu.address), textMenu.address) }
        OMenuItem { visible: textMenu.address !== ""; text: plume.t.chat_with; iconName: "chat"; onTriggered: plume.meetWith(textMenu.address, reader.nameOf(textMenu.address), false) }
        OMenuItem { visible: textMenu.address !== ""; text: plume.t.visio; iconName: "video"; onTriggered: plume.meetWith(textMenu.address, reader.nameOf(textMenu.address), true) }
        OMenuItem { visible: textMenu.image !== ""; text: plume.t.copy_image; iconName: "draft"; onTriggered: mail.copyImage(textMenu.image) }
        OMenuItem {
            visible: textMenu.image !== ""
            text: plume.t.save_image; iconName: "import"
            onTriggered: {
                imageSaveDialog.url = textMenu.image
                imageSaveDialog.selectedFile = "file:///" + mail.imageName(textMenu.image)
                imageSaveDialog.open()
            }
        }
        OMenuItem {
            visible: textMenu.copying && (textMenu.image === "" || textMenu.selection)
            text: plume.t.copy; iconName: "draft"
            onTriggered: {
                const t = textMenu.target
                if (textMenu.web)
                    t.triggerWebAction(WebEngineView.Copy)
                else
                    plume.copyText(t.selectedText !== "" ? t.selectedText : t.getText(0, t.length).replace(/\u00a0/g, " "))
            }
        }
        OMenuItem { visible: textMenu.copying && textMenu.link !== ""; text: plume.t.copy_link; iconName: "arrow"; onTriggered: plume.copyText(textMenu.link) }
    }

    // what to do with an attachment: open it, save it, or keep it in Orneos
    OMenu {
        id: attachmentMenu
        property int messageId
        property int index: -1
        property string name
        function openFor(id, at, label, anchor) {
            messageId = id; index = at; name = label
            parent = anchor
            x = 0; y = anchor.height + 6
            open()
        }
        function openAt(id, at, px, py, anchor) {
            messageId = id; index = at; name = mail.attachmentName(id, at)
            parent = anchor
            x = px; y = py
            open()
        }
        heading: name
        OMenuItem { text: plume.t.attachment_open; iconName: "arrow"; onTriggered: mail.openAttachment(attachmentMenu.index, attachmentMenu.messageId) }
        OMenuItem {
            text: plume.t.attachment_save; iconName: "import"
            onTriggered: {
                saveDialog.index = attachmentMenu.index
                saveDialog.messageId = attachmentMenu.messageId
                saveDialog.selectedFile = "file:///" + attachmentMenu.name
                saveDialog.open()
            }
        }
        OMenuItem { text: plume.t.attachment_orneos; iconName: "cloud"; onTriggered: mail.saveToOrneos(attachmentMenu.index, attachmentMenu.messageId) }
    }

    ChoiceDialog { id: confirm }

    FileDialog {
        id: imageSaveDialog
        property string url
        fileMode: FileDialog.SaveFile
        onAccepted: mail.saveImage(url, selectedFile.toString())
    }

    FileDialog {
        id: emlDialog
        fileMode: FileDialog.SaveFile
        onAccepted: mail.saveMessage(reader.m.messageId, selectedFile.toString())
    }
    FolderDialog {
        id: folderDialog
        onAccepted: mail.saveAllAttachments(reader.m.messageId, selectedFolder.toString())
    }

    FileDialog {
        id: saveDialog
        property int index: -1
        property int messageId: 0
        fileMode: FileDialog.SaveFile
        onAccepted: mail.saveAttachment(index, selectedFile.toString(), messageId)
    }
}
