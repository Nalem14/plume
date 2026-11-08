// The home of Meet, when no conversation is open: the day on a card of the family (who is waiting, what comes),
// three ways to meet (now, by a link, later), the meetings of the calendar that have a conversation, the
// reminders set on messages.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: home
    readonly property var c: theme.c
    readonly property var events: meet.home.events || []
    readonly property var reminders: meet.home.reminders || []
    readonly property int todayCount: events.filter(e => app.day(e.start) === app.t.today).length
    property double now: Date.now()
    signal newConversation()
    signal callRoom(string token, bool video)
    signal planWanted()
    color: c.bg

    Timer { interval: 30000; running: home.visible; repeat: true; onTriggered: home.now = Date.now() }
    onVisibleChanged: if (visible) meet.loadHome()

    function greeting() {
        const h = new Date().getHours()
        const first = String(app.profile.name || "").split(" ")[0]
        const word = h < 5 ? app.t.hello_night : (h < 18 ? app.t.hello_day : app.t.hello_evening)
        return first ? word + ", " + first : word
    }
    function soon(e) {
        const s = e.start * 1000
        return e.active || (s - home.now < 10 * 60000 && e.end * 1000 > home.now)
    }

    // a way to meet: a card with its glyph on a disc of its colour, two lines
    component Way: AbstractButton {
        id: way
        property string iconName
        property string lead
        property color tint: home.c.famCommunicate
        implicitHeight: 104
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: text
        background: Surface {
            raised: true
            radius: 12
            color: way.hovered ? Qt.tint(home.c.card, Qt.alpha(way.tint, theme.dark ? 0.10 : 0.05)) : home.c.card
            Rectangle {
                width: 3; radius: 1.5
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 14; bottomMargin: 14 }
                color: way.tint
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: -3
                radius: 15; color: "transparent"
                border.width: 2; border.color: home.c.saffron
                visible: way.visualFocus
            }
        }
        contentItem: RowLayout {
            spacing: 14
            Rectangle {
                Layout.leftMargin: 8
                implicitWidth: 44; implicitHeight: 44; radius: 22
                color: Qt.alpha(way.tint, theme.dark ? 0.22 : 0.12)
                Icon { anchors.centerIn: parent; name: way.iconName; size: 22; color: way.tint; hovered: way.hovered }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: way.text; font.pixelSize: 15; font.weight: Font.DemiBold; color: home.c.text; elide: Text.ElideRight }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: way.lead; font.pixelSize: 13; color: home.c.muted; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
            }
        }
        leftPadding: 14; rightPadding: 14
    }

    component Heading: Text {
        Layout.topMargin: 10
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
        color: home.c.faint
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight + 48
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: column
            x: Math.max(20, (parent.width - 920) / 2)
            y: 20
            width: Math.min(920, parent.width - 40)
            spacing: 14

            Hero {
                Layout.fillWidth: true
                tint: home.c.famCommunicate
                kicker: app.day(Math.round(home.now / 1000)) + " · " + app.clock(Math.round(home.now / 1000))
                title: home.greeting()
                meta: [home.todayCount ? app.plural("meetings_today", home.todayCount) : app.t.no_meeting_today,
                       (meet.counts.unread || 0) ? app.plural("waiting_count", meet.counts.unread) : ""].filter(x => x).join(" · ")
                offline: meet.state === "offline"
                offlineText: app.t.offline
                leading: Rectangle {
                    width: 56; height: 56; radius: 28
                    color: Qt.alpha(home.c.famCommunicate, theme.dark ? 0.22 : 0.12)
                    border.width: 2; border.color: Qt.alpha(home.c.famCommunicate, 0.35)
                    Icon { anchors.centerIn: parent; name: "video"; size: 24; color: home.c.famCommunicate }
                }
                OButton {
                    kind: "primary"; iconName: "video"; text: app.t.meet_now
                    onClicked: meet.meetNow(app.t.meeting_of.replace("%1", app.profile.name || ""))
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: home.width > 760 ? 3 : 1
                rowSpacing: 12; columnSpacing: 12
                Way {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    iconName: "video"; text: app.t.meet_now; lead: app.t.meet_now_lead
                    onClicked: meet.meetNow(app.t.meeting_of.replace("%1", app.profile.name || ""))
                }
                Way {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    iconName: "calendar"; text: app.t.plan_meeting; lead: app.t.plan_meeting_lead
                    tint: home.c.famOrganize
                    onClicked: home.planWanted()
                }
                Way {
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    iconName: "link"; text: app.t.join_link; lead: app.t.join_link_lead
                    tint: home.c.famDocs
                    onClicked: joinDialog.open()
                }
            }

            Heading { text: app.t.upcoming }
            Surface {
                visible: home.events.length === 0
                Layout.fillWidth: true
                implicitHeight: 76
                raised: false
                color: Qt.alpha(home.c.card, 0.6)
                RowLayout {
                    anchors.fill: parent; anchors.margins: 18
                    spacing: 14
                    Icon { name: "calendar"; size: 22; color: home.c.faint }
                    Text { Layout.fillWidth: true; text: app.t.no_upcoming; wrapMode: Text.WordWrap; font.pixelSize: 13; color: home.c.muted }
                }
            }
            Repeater {
                model: home.events
                Surface {
                    id: event
                    required property var modelData
                    readonly property bool now: home.soon(modelData)
                    Layout.fillWidth: true
                    implicitHeight: 84
                    gradient: now ? live : null
                    Gradient {
                        id: live
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.tint(home.c.card, Qt.alpha(home.c.ok, theme.dark ? 0.18 : 0.10)) }
                        GradientStop { position: 0.6; color: home.c.card }
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 18; anchors.rightMargin: 14
                        spacing: 16
                        ColumnLayout {
                            Layout.preferredWidth: 78
                            spacing: 0
                            Text { textFormat: Text.PlainText;
                                text: app.clock(event.modelData.start)
                                font.family: "JetBrains Mono"; font.pixelSize: 22; font.weight: Font.Medium; font.letterSpacing: -0.6
                                color: event.now ? home.c.ok : home.c.text
                            }
                            Text { textFormat: Text.PlainText;
                                text: app.day(event.modelData.start)
                                font.pixelSize: 12; color: home.c.muted
                                elide: Text.ElideRight; Layout.maximumWidth: 90
                            }
                        }
                        Rectangle { implicitWidth: 1; Layout.fillHeight: true; Layout.topMargin: 16; Layout.bottomMargin: 16; color: home.c.hairline }
                        RoomAvatar { size: 36; source: event.modelData.avatar; name: event.modelData.room }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: event.modelData.title; elide: Text.ElideRight; font.pixelSize: 15; font.weight: Font.DemiBold; color: home.c.text }
                            Text { textFormat: Text.PlainText;
                                Layout.fillWidth: true
                                text: event.now ? (event.modelData.active ? app.t.call_ongoing : app.t.starting_soon)
                                      : app.t.until.replace("%1", app.clock(event.modelData.end)) + (event.modelData.invited ? " · " + app.plural("invited_count", event.modelData.invited) : "")
                                elide: Text.ElideRight
                                font.pixelSize: 13
                                color: event.now ? home.c.okInk : home.c.muted
                            }
                        }
                        OButton {
                            text: app.t.open; kind: "quiet"
                            onClicked: meet.open(event.modelData.token)
                        }
                        OButton {
                            kind: event.now ? "primary" : "secondary"
                            iconName: "video"; text: app.t.join_call
                            onClicked: home.callRoom(event.modelData.token, true)
                        }
                    }
                }
            }

            Heading { text: app.t.reminders; visible: home.reminders.length > 0 }
            Repeater {
                model: home.reminders
                Surface {
                    id: reminder
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: 64
                    radius: 10
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16; anchors.rightMargin: 12
                        spacing: 12
                        Icon { name: "clock"; size: 18; color: home.c.saffronInk }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: reminder.modelData.name + " · " + app.when(reminder.modelData.at); font.pixelSize: 12; font.weight: Font.DemiBold; color: home.c.saffronInk; elide: Text.ElideRight }
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: reminder.modelData.text; font.pixelSize: 13; color: home.c.body; elide: Text.ElideRight }
                        }
                        OButton {
                            text: app.t.see; kind: "quiet"
                            onClicked: { meet.open(reminder.modelData.token); Qt.callLater(() => meet.jumpTo(reminder.modelData.id)) }
                        }
                    }
                }
            }
        }
    }

    ODialog {
        id: joinDialog
        title: app.t.join_link
        tint: home.c.famDocs
        onOpened: { link.text = ""; link.forceActiveFocus() }
        Text { Layout.fillWidth: true; text: app.t.join_link_help; wrapMode: Text.WordWrap; font.pixelSize: 13; color: home.c.muted }
        OTextField {
            id: link
            Layout.fillWidth: true
            iconName: "link"
            placeholderText: "https://app.orneos.eu/call/…"
            onAccepted: joinButton.clicked()
        }
        footer: [
            OButton { text: app.t.cancel; onClicked: joinDialog.close() },
            OButton {
                id: joinButton
                kind: "primary"; text: app.t.join_call
                enabled: /\/call\/[A-Za-z0-9]+/.test(link.text)
                onClicked: { app.openUrl(link.text.trim()); joinDialog.close() }
            }
        ]
    }
}
