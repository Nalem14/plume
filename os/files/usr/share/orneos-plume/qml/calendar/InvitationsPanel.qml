// Invitations from other people: "New" waits for an answer, "History" keeps the answers given
// (accepted, maybe, declined) and lets them change. A click opens the event.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/colors.js" as Colors
import "../components/dates.js" as D
import "../contacts"

ColumnLayout {
    id: panel
    property string kind: "new"
    signal openRequested(var invite)
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    readonly property var list: { agenda.revision; return agenda.invitations(kind) }
    spacing: 10

    function when(invite) {
        const s = new Date(invite.start)
        const time = invite.allDay ? "" : D.hm(s)
        const today = new Date()
        if (D.sameDay(s, today))
            return invite.allDay ? plume.t.today : plume.t.today_at.replace("%1", time)
        if (D.sameDay(s, D.addDays(today, 1)))
            return invite.allDay ? plume.t.tomorrow : plume.t.tomorrow_at.replace("%1", time)
        const day = D.capitalize(loc.toString(s, "ddd d MMM").replace(".", ""))
        return invite.allDay ? day : plume.t.day_at.replace("%1", day).replace("%2", time)
    }

    // New / History
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 32
        radius: 7
        color: panel.c.bg
        border.width: 1; border.color: panel.c.line
        Row {
            anchors.fill: parent; anchors.margins: 2
            Repeater {
                model: [["new", plume.t.inv_new], ["history", plume.t.inv_history]]
                AbstractButton {
                    id: seg
                    required property var modelData
                    readonly property bool active: panel.kind === modelData[0]
                    width: parent.width / 2; height: parent.height
                    hoverEnabled: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.checked: active
                    onClicked: panel.kind = modelData[0]
                    background: Rectangle { radius: 5; color: seg.active ? panel.c.card : "transparent"; border.width: seg.active ? 1 : 0; border.color: panel.c.line }
                    // a control sizes and places its contentItem: the row is centred inside an Item
                    contentItem: Item {
                        Row {
                            spacing: 6
                            anchors.centerIn: parent
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: seg.modelData[1]
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: seg.active ? Font.DemiBold : Font.Medium
                                color: seg.active || seg.hovered ? panel.c.text : panel.c.muted
                            }
                            Rectangle {
                                visible: seg.modelData[0] === "new" && agenda.pending > 0
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(18, pendingCount.implicitWidth + 8); height: 18; radius: 9
                                color: panel.c.saffron
                                Text { id: pendingCount; anchors.centerIn: parent; text: agenda.pending; font.family: "JetBrains Mono"; font.pixelSize: 11; color: panel.c.saffronText }
                            }
                        }
                    }
                }
            }
        }
    }

    Text {
        visible: panel.list.length === 0
        Layout.fillWidth: true
        Layout.topMargin: 8
        text: panel.kind === "new" ? plume.t.inv_none_new : plume.t.inv_none_history
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: panel.c.muted
    }

    Repeater {
        model: panel.list
        ColumnLayout {
            id: invite
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: 8

            Rectangle { visible: invite.index > 0; Layout.fillWidth: true; Layout.preferredHeight: 1; color: panel.c.hairline }

            AbstractButton {
                id: head
                Layout.fillWidth: true
                implicitHeight: headRow.implicitHeight + 8
                hoverEnabled: true
                Accessible.name: invite.modelData.title
                onClicked: panel.openRequested(invite.modelData)
                background: Rectangle { radius: 6; color: head.hovered ? panel.c.hover : "transparent"; anchors.margins: -4 }
                contentItem: RowLayout {
                    id: headRow
                    spacing: 10
                    Avatar {
                        Layout.alignment: Qt.AlignTop
                        initials: invite.modelData.organizer.split(/[\s@.]+/).filter(x => x).slice(0, 2).map(x => x[0].toUpperCase()).join("")
                        tint: invite.index % 4
                        size: 34
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 2; color: Colors.display(invite.modelData.color, theme.dark) }
                            Text {
                                Layout.fillWidth: true
                                text: invite.modelData.title || plume.t.untitled
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                                color: panel.c.text
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: invite.modelData.organizer
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: panel.c.muted
                        }
                        Text {
                            Layout.fillWidth: true
                            text: panel.when(invite.modelData) + (invite.modelData.location ? " · " + invite.modelData.location : "")
                            wrapMode: Text.Wrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                            color: panel.c.text
                        }
                    }
                }
            }

            // the answer: the current one stands out (status colour in History)
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 44
                spacing: 4
                Repeater {
                    model: [["DECLINED", plume.t.decline], ["TENTATIVE", plume.t.maybe], ["ACCEPTED", plume.t.accept]]
                    AbstractButton {
                        id: answer
                        required property var modelData
                        readonly property bool current: invite.modelData.status === modelData[0]
                        readonly property color tone: modelData[0] === "ACCEPTED" ? panel.c.ok : modelData[0] === "DECLINED" ? panel.c.danger : panel.c.saffronInk
                        readonly property color toneTint: modelData[0] === "ACCEPTED" ? panel.c.okTint : modelData[0] === "DECLINED" ? panel.c.dangerTint : panel.c.saffronTint
                        Layout.fillWidth: true
                        implicitHeight: 28
                        hoverEnabled: true
                        Accessible.name: modelData[1]
                        Accessible.checked: current
                        onClicked: if (!current) agenda.respond(invite.modelData.eventId, modelData[0])
                        background: Rectangle {
                            radius: 6
                            color: answer.current ? answer.toneTint : answer.hovered ? panel.c.hover : panel.c.card
                            border.width: 1
                            border.color: answer.current ? answer.tone : panel.c.line
                        }
                        contentItem: Text {
                            text: answer.modelData[1]
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: answer.current ? Font.DemiBold : Font.Medium
                            color: answer.current ? answer.tone : panel.c.text
                        }
                    }
                }
            }
        }
    }
}
