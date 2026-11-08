// The invitation of a mail (its calendar part, iMIP): the event as the calendar reads it, what the calendar
// already knows of it, and the answer in one click. An invitation waits in the calendar from its arrival;
// answering from here or from Invitations is the same thing. Cancellations and replies say so.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Rectangle {
    id: card
    property string ics
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    readonly property var info: { agenda.revision; return ics ? agenda.invitation(ics) : ({}) }
    readonly property bool shown: !!info.uid
    readonly property string kind: info.method === "CANCEL" ? "cancel" : info.method === "REPLY" ? "reply"
                                   : info.sequence > 0 && info.method === "REQUEST" ? "update" : info.canRespond ? "invite" : "info"
    readonly property date start: new Date(info.start || 0)

    visible: shown
    implicitHeight: shown ? body.implicitHeight + 28 : 0
    radius: 10
    color: c.bg
    border.width: 1; border.color: kind === "cancel" ? c.danger : c.line

    function when() {
        if (!info.start) return ""
        const s = start, e = new Date(info.end || info.start)
        if (info.allDay) {
            const last = new Date(e.getTime() - 86400000)
            return last > s ? loc.toString(s, "dddd d MMMM") + " – " + loc.toString(last, "dddd d MMMM") : loc.toString(s, "dddd d MMMM yyyy")
        }
        const sameDay = s.toDateString() === e.toDateString()
        return loc.toString(s, "dddd d MMMM yyyy · HH:mm") + " – " + (sameDay ? loc.toString(e, "HH:mm") : loc.toString(e, "d MMM HH:mm"))
    }

    ColumnLayout {
        id: body
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            // the day, as a small calendar sheet
            Rectangle {
                Layout.alignment: Qt.AlignTop
                implicitWidth: 52; implicitHeight: 56
                radius: 8
                color: card.c.card
                border.width: 1; border.color: card.c.line
                clip: true
                Rectangle {
                    width: parent.width; height: 18
                    color: card.kind === "cancel" ? card.c.danger : card.c.action
                    Text {
                        anchors.centerIn: parent
                        text: card.loc.toString(card.start, "MMM").replace(".", "").toUpperCase()
                        font.family: "Schibsted Grotesk"; font.pixelSize: 10; font.weight: Font.Bold; font.letterSpacing: 0.6
                        color: card.kind === "cancel" ? "white" : card.c.actionText
                    }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 20
                    text: card.start.getDate()
                    font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.DemiBold
                    font.strikeout: card.kind === "cancel"
                    color: card.c.text
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: card.kind === "cancel" ? plume.t.invite_cancel_title : card.kind === "reply" ? plume.t.invite_reply_title
                        : card.kind === "update" ? plume.t.invite_update : card.kind === "invite" ? plume.t.invite_title : plume.t.invite_info
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.3
                    color: card.kind === "cancel" ? card.c.danger : card.c.accent
                }
                Text {
                    Layout.fillWidth: true
                    text: card.info.title || plume.t.untitled
                    wrapMode: Text.Wrap
                    maximumLineCount: 2; elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                    font.strikeout: card.kind === "cancel"
                    color: card.c.text
                }
                Text {
                    Layout.fillWidth: true
                    text: card.when() + (card.info.recurring ? "  ·  " + plume.t.recurring : "")
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: card.c.text
                }
                Text {
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: [card.info.location && card.info.location !== card.info.meet ? card.info.location : "",
                           card.info.organizer && card.kind !== "reply" ? plume.t.organizer.replace("%1", card.info.organizerName || card.info.organizer) : ""]
                          .filter(x => x).join("  ·  ")
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: card.c.muted
                }
            }
        }

        // what to do
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            // the answer (current one stands out), as in Invitations
            Repeater {
                model: card.kind === "invite" || card.kind === "update"
                       ? (card.info.canRespond && !card.info.outdated ? [["ACCEPTED", plume.t.accept], ["TENTATIVE", plume.t.maybe], ["DECLINED", plume.t.decline]] : []) : []
                AbstractButton {
                    id: answer
                    required property var modelData
                    readonly property bool current: card.info.status === modelData[0]
                    readonly property color tone: modelData[0] === "ACCEPTED" ? card.c.ok : modelData[0] === "DECLINED" ? card.c.danger : card.c.saffronInk
                    readonly property color toneTint: modelData[0] === "ACCEPTED" ? card.c.okTint : modelData[0] === "DECLINED" ? card.c.dangerTint : card.c.saffronTint
                    implicitWidth: Math.max(92, label.implicitWidth + 28)
                    implicitHeight: 32
                    hoverEnabled: true
                    Accessible.name: modelData[1]
                    Accessible.checked: current
                    onClicked: if (!current) agenda.answerInvitation(card.ics, modelData[0])
                    background: Rectangle {
                        radius: 6
                        color: answer.current ? answer.toneTint : answer.hovered ? card.c.hover : card.c.card
                        border.width: 1
                        border.color: answer.current ? answer.tone : card.c.line
                    }
                    contentItem: Item {
                        Row {
                            anchors.centerIn: parent
                            spacing: 6
                            Icon { anchors.verticalCenter: parent.verticalCenter; visible: answer.current; name: "check"; size: 14; color: answer.tone }
                            Text {
                                id: label
                                anchors.verticalCenter: parent.verticalCenter
                                text: answer.modelData[1]
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: answer.current ? Font.DemiBold : Font.Medium
                                color: answer.current ? answer.tone : card.c.text
                            }
                        }
                    }
                }
            }
            Text {
                id: note
                Layout.fillWidth: true
                visible: text !== ""
                text: card.info.outdated ? plume.t.invite_outdated
                    : card.kind === "cancel" ? plume.t.invite_cancelled
                    : card.kind === "reply" && card.info.replier ? plume.t["invite_replied_" + (card.info.replier.status || "ACCEPTED")]
                          .replace("%1", card.info.replier.name || card.info.replier.email || "")
                    : card.info.mine ? plume.t.invite_mine
                    : card.kind === "info" && card.info.eventId ? plume.t.invite_in_calendar : ""
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: card.kind === "cancel" ? card.c.danger : card.c.muted
            }
            Item { Layout.fillWidth: true; visible: !note.visible }
            OButton {
                visible: card.kind === "info" && !card.info.eventId && !card.info.mine
                kind: "primary"; height_: 32; iconName: "plus"; text: plume.t.invite_add
                onClicked: if (agenda.addInvitation(card.ics)) plume.toast(plume.t.invite_added)
            }
            OButton {
                visible: card.kind === "cancel" && card.info.eventId > 0
                height_: 32; iconName: "trash"; text: plume.t.invite_remove
                onClicked: agenda.removeInvitation(card.ics)
            }
            OButton {
                visible: !!card.info.meet && card.kind !== "cancel"
                kind: "quiet"; height_: 32; iconName: "video"
                text: card.info.meetName ? plume.t.join_on.replace("%1", card.info.meetName) : plume.t.invite_join
                onClicked: plume.openUrl(card.info.meet)
            }
            OButton {
                visible: card.info.eventId > 0 && card.kind !== "cancel"
                kind: "quiet"; height_: 32; iconName: "calendar"; text: plume.t.invite_show
                onClicked: plume.showEvent(card.info.eventId, card.info.start)
            }
        }
    }
}
