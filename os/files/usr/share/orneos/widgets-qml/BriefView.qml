// SPDX-License-Identifier: GPL-2.0-or-later
// Ornis du jour on the desktop: what is left today, put together on this computer (calendar, tasks, unread
// mail, conversations waiting in Meet). Nothing is sent to Ornis by the widget: "Prepare my day" opens Ornis
// with the request, and Ornis reads what it needs with its own tools. Small: the greeting and two lines;
// wide or tall: every line (each opens its app) and the button.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    readonly property var feed: bridge
    readonly property var data: bridge.result
    readonly property var events: data.events || []
    readonly property var next: events.find(e => !e.allDay && e.startTs > Date.now() / 1000) || null
    property date now: new Date()

    family: "tools"
    ai: true
    context: S.tr("brief")
    onOpened: bridge.launch("ornis")

    function prepare() { bridge.launch("ornis --ask=" + bridge.quote(S.tr("preparePrompt"))); }
    function count(n, one, many) { return n === 1 ? S.tr(one) : S.fmt(many, n); }
    function time(ts) { return Qt.locale().toString(new Date(ts * 1000), Qt.locale().timeFormat(Locale.ShortFormat)); }
    readonly property var lines: {
        const out = [];
        out.push({icon: "view-calendar-day", app: "orneos-calendar", strong: events.length > 0,
                  text: events.length ? count(events.length, "eventsLeftOne", "eventsLeft") : S.tr("noEvents"),
                  detail: next ? S.fmt("nextAt", next.title, time(next.startTs)) : ""});
        if (data.tasks) out.push({icon: "checkmark", app: "orneos-tasks", strong: data.tasks.today > 0,
                  text: count(data.tasks.today, "tasksOne", "tasksLine"),
                  detail: data.tasks.late ? S.fmt("lateShort", data.tasks.late) : (data.tasks.first || []).join(" · "),
                  late: data.tasks.late > 0});
        if (data.mail) out.push({icon: "mail-unread", app: "orneos-mail", strong: data.mail.unread > 0,
                  text: count(data.mail.unread, "mailOne", "mailLine"), detail: (data.mail.from || []).join(", ")});
        if (data.waiting !== null && data.waiting !== undefined)
            out.push({icon: "dialog-messages", app: "orneos-meet", strong: data.waiting > 0,
                      text: count(data.waiting, "waitingOne", "waitingLine"), detail: ""});
        return out;
    }
    readonly property bool clear: lines.every(l => !l.strong)

    Bridge { id: bridge; command: "/usr/libexec/orneos-widget brief"; interval: 120000 }
    Timer { interval: 60000; running: true; repeat: true; onTriggered: root.now = new Date() }

    // The greeting and the date (wide but low: "Prepare my day" beside them).
    RowLayout {
        Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            PC3.Label {
                Layout.fillWidth: true
                text: S.tr(root.now.getHours() >= 18 ? "helloEvening" : "hello")
                font.weight: Font.Bold
                font.pointSize: Kirigami.Theme.defaultFont.pointSize * (root.roomy ? 1.5 : 1.25)
                elide: Text.ElideRight
            }
            PC3.Label {
                Layout.fillWidth: true
                text: Qt.locale().toString(root.now, "dddd d MMMM")
                opacity: 0.65
                elide: Text.ElideRight
            }
        }
        PrepareButton { visible: bridge.result.ready && root.wide && !root.tall; dark: root.dark; onClicked: root.prepare() }
    }
    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: root.roomy ? 3 : 2
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        visible: bridge.result.state === "signed_out" || bridge.result.state === "error"
        Layout.fillWidth: true
        text: S.tr(bridge.result.state || "error")
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }

    Repeater {
        model: !bridge.result.ready ? [] : root.tall ? root.lines
               : root.lines.filter(l => l.strong).concat(root.lines.filter(l => !l.strong)).slice(0, 2).filter(l => root.roomy || l.strong)
        delegate: Item {
            id: row
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: line.implicitHeight + Kirigami.Units.smallSpacing * 2
            Rectangle {
                anchors.fill: parent
                radius: Ornis.t.radius.control
                color: area.containsMouse ? Qt.alpha(Kirigami.Theme.textColor, 0.07) : "transparent"
            }
            RowLayout {
                id: line
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 4; rightMargin: 4 }
                spacing: Kirigami.Units.smallSpacing * 2
                Rectangle {
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 1.6
                    Layout.preferredHeight: Layout.preferredWidth
                    radius: Ornis.t.radius.control
                    color: Qt.alpha(row.modelData.late ? Ornis.t.brand.vermillon : root.tint, row.modelData.strong ? 0.14 : 0.06)
                    Kirigami.Icon {
                        anchors.centerIn: parent
                        width: Kirigami.Units.iconSizes.small
                        height: width
                        source: row.modelData.icon
                        opacity: row.modelData.strong ? 1 : 0.55
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        Layout.fillWidth: true
                        text: row.modelData.text
                        elide: Text.ElideRight
                        font.weight: row.modelData.strong ? Font.DemiBold : Font.Normal
                        opacity: row.modelData.strong ? 1 : 0.65
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        visible: root.roomy && text !== ""
                        text: row.modelData.detail
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        color: row.modelData.late ? Ornis.t.brand.vermillon : Kirigami.Theme.textColor
                        opacity: row.modelData.late ? 1 : 0.65
                        font: Kirigami.Theme.smallFont
                    }
                }
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: bridge.launch(row.modelData.app)
                Accessible.role: Accessible.Button
                Accessible.name: row.modelData.text
            }
        }
    }
    PC3.Label {
        visible: bridge.result.ready && root.clear && !root.roomy
        Layout.fillWidth: true
        text: S.tr("allClear")
        wrapMode: Text.WordWrap
        opacity: 0.7
    }
    Item { Layout.fillHeight: true }
    PrepareButton { visible: bridge.result.ready && root.tall; dark: root.dark; onClicked: root.prepare() }

    // Opens Ornis with the request: Ornis reads the calendar, tasks and mail with its own tools.
    component PrepareButton: PC3.Button {
        id: prepare
        property bool dark: false
        text: S.tr("prepareDay")
        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing
            OrnisStars {
                color: Ornis.family("communicate", prepare.dark)
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: Kirigami.Units.iconSizes.small
            }
            PC3.Label { text: prepare.text; font.weight: Font.DemiBold }
        }
    }
}
