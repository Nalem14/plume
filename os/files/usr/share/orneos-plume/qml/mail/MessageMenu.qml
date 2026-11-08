// What can be done to a message (or its conversation): read or unread, Favori, tags, then archive, junk,
// delete (full menu, the list's right click) and move to a folder of its mailbox. The reader's « ⋯ » uses it
// without the actions it already has as buttons. With ids (lines picked in the list), on all of them.
import QtQuick
import QtQuick.Controls
import "../components"

OMenu {
    id: root
    property int messageId
    property bool seen
    property bool flagged
    property var tags: []
    property string box: "orneos"
    property string role
    property bool full: true
    property int attachments: 0               // the reader: « Tout enregistrer » when there are some
    signal extraRequested(string kind)        // the reader's own: print, source, eml, attachments
    signal snoozeRequested(var leads)         // « Me le rappeler… »: its own small menu of moments
    property var ids: []                      // several lines: what the menu acts on
    readonly property bool many: ids.length > 1
    readonly property bool canSnooze: role !== "trash" && role !== "junk" && role !== "drafts" && role !== "outbox"
    heading: many ? plume.t.selected_many.replace("%1", ids.length) : ""
    signal actionRequested(string role)       // archive, trash, junk, inbox, or a folder id
    signal seenToggled(bool seen)
    readonly property var c: theme.c

    function openFor(info, anchor, px, py) {
        messageId = info.messageId; seen = !!info.seen; flagged = !!info.flagged
        tags = Array.from(info.tags || []); box = info.box === undefined ? "orneos" : info.box; role = info.role || ""
        ids = Array.from(info.ids || [])
        parent = anchor
        x = px; y = py
        open()
    }

    component Heading: Text {
        leftPadding: 10; topPadding: 10; bottomPadding: 4
        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.6
        color: root.c.muted
    }
    component Line_: Rectangle { width: parent ? parent.width : 0; height: 1; color: root.c.hairline }

    OMenuItem {
        text: root.seen ? plume.t.mark_unread : plume.t.mark_read; iconName: "mail"
        onTriggered: {
            if (root.many)
                mail.setSeenMany(root.ids, !root.seen)
            else {
                mail.setSeen(root.messageId, !root.seen)
                root.seenToggled(!root.seen)
            }
        }
    }
    OMenuItem {
        text: root.flagged ? plume.t.unstar : plume.t.star; iconName: "star"
        onTriggered: root.many ? mail.setFlaggedMany(root.ids, !root.flagged) : mail.setFlagged(root.messageId, !root.flagged)
    }
    Line_ {}
    Heading { text: plume.t.tags }
    Repeater {
        model: 5
        OMenuItem {
            required property int index
            readonly property int number: index + 1
            text: plume.t["tag_" + number]
            dot: root.c["tag" + number]
            switchable: true
            on: root.tags.indexOf(number) >= 0
            onTriggered: {
                const add = !on
                if (root.many)
                    mail.setTagMany(root.ids, number, add)
                else
                    mail.setTag(root.messageId, number, add)
                root.tags = add ? root.tags.concat([number]) : root.tags.filter(n => n !== number)
            }
        }
    }
    // « Me le rappeler »: put away until then, back in the inbox unread (not from the trash or the junk)
    OMenuItem {
        visible: root.canSnooze
        text: plume.t.snooze + "…"; iconName: "history"
        onTriggered: root.snoozeRequested(root.many ? root.ids : [root.messageId])
    }
    OMenuItem {
        text: plume.t.link_copy; iconName: "link"
        onTriggered: mail.copyLinks(root.many ? root.ids : [root.messageId])
    }
    // the reader's « ⋯ »: the message itself
    Line_ { visible: !root.full }
    OMenuItem { visible: !root.full; text: plume.t.print_message; iconName: "export"; onTriggered: root.extraRequested("print") }
    OMenuItem { visible: !root.full && root.attachments > 1; text: plume.t.attachments_save_all; iconName: "download"; onTriggered: root.extraRequested("attachments") }
    OMenuItem { visible: !root.full; text: plume.t.message_save; iconName: "import"; onTriggered: root.extraRequested("eml") }
    OMenuItem { visible: !root.full; text: plume.t.message_source; iconName: "code"; onTriggered: root.extraRequested("source") }
    Line_ { visible: root.full }
    OMenuItem { visible: root.full && root.role !== "archive"; text: plume.t.archive; iconName: "archive"; onTriggered: root.actionRequested("archive") }
    OMenuItem {
        visible: root.full
        text: root.role === "junk" ? plume.t.not_spam : plume.t.spam_report; iconName: "spam"
        onTriggered: root.actionRequested(root.role === "junk" ? "inbox" : "junk")
    }
    OMenuItem {
        visible: root.full
        text: root.role === "trash" ? plume.t.delete_forever : plume.t.delete; iconName: "trash"; danger: true
        onTriggered: root.actionRequested("trash")
    }
    Line_ { visible: root.box !== "" }
    Heading { visible: root.box !== ""; text: plume.t.move_to }
    Repeater {
        // folders of the same mailbox only
        model: mail.folders.filter(f => f.id > 0 && f.id !== mail.folderId && f.role !== "drafts" && f.box === root.box)
        OMenuItem {
            required property var modelData
            text: modelData.role ? plume.t["folder_" + modelData.role] : modelData.full
            iconName: ({ inbox: "inbox", sent: "send", archive: "archive", junk: "spam", trash: "trash" })[modelData.role] || "folder"
            onTriggered: root.actionRequested(String(modelData.id))
        }
    }
}
