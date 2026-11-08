// SPDX-License-Identifier: GPL-2.0-or-later
// Meet on the desktop: what waits for you (one-to-one messages and mentions, like the dock's badge), a call
// in progress, the next meeting of the day. Small: the count, or the call to join. Wide or tall: the next
// meeting (Join ten minutes before), then the conversations. Read from Meet's copy on this computer.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    property int limit: 6
    readonly property var feed: bridge
    readonly property var rooms: (bridge.result.rooms || []).slice(0, Math.max(1, limit))
    readonly property var call: (bridge.result.rooms || []).find(r => r.call) || null
    readonly property int waiting: bridge.result.waiting || 0
    readonly property var meeting: (bridge.result.meetings || [])[0] || null
    property real nowTs: Date.now() / 1000

    family: "communicate"
    context: S.tr("meet") + (roomy && waiting ? " · " + S.fmt("waitingCount", waiting) : "")
    actionIcon: "camera-video"
    actionText: S.tr("newMeeting")
    onAction: bridge.launch("orneos-meet --new")
    onOpened: bridge.launch("orneos-meet")

    function joinable(e) { return !!e && e.startTs - nowTs < 600 && e.endTs > nowTs; }
    function time(ts) { return Qt.locale().toString(new Date(ts * 1000), Qt.locale().timeFormat(Locale.ShortFormat)); }
    function initials(name) {
        const parts = String(name || "?").trim().split(/\s+/);
        return ((parts[0] || "?")[0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
    }
    function color(name) {
        const keys = ["communicate", "docs", "organize", "media", "space"];
        let h = 0;
        for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 997;
        return Ornis.family(keys[h % keys.length], false);
    }

    Bridge { id: bridge; command: "/usr/libexec/orneos-widget meet"; interval: 15000 }
    Timer { interval: 30000; running: true; repeat: true; onTriggered: root.nowTs = Date.now() / 1000 }

    PC3.Label {
        visible: !bridge.result.ready && bridge.result.state !== "loading"
        Layout.fillWidth: true
        text: S.tr(bridge.result.state || "error")
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }
    PC3.Button {
        visible: !bridge.result.ready && bridge.result.state !== "loading"
        text: bridge.result.state === "signed_out" ? "Orneos Connect" : S.tr("open")
        onClicked: bridge.launch(bridge.result.state === "signed_out" ? "orneos-connect" : "orneos-meet")
    }

    // A call in progress (saffron: it asks for attention), or the next meeting with a link.
    Rectangle {
        visible: bridge.result.ready && (root.call !== null || (root.roomy && root.meeting !== null))
        Layout.fillWidth: true
        implicitHeight: banner.implicitHeight + Kirigami.Units.largeSpacing * 2
        radius: Ornis.t.radius.card
        color: root.call ? Qt.alpha(Ornis.t.brand.safran, 0.16) : Qt.alpha(root.tint, 0.1)
        RowLayout {
            id: banner
            anchors { fill: parent; margins: Kirigami.Units.largeSpacing }
            spacing: Kirigami.Units.largeSpacing
            Kirigami.Icon {
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                source: root.call ? "call-start" : "view-calendar-day"
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                PC3.Label {
                    Layout.fillWidth: true
                    text: root.call ? S.tr("callNow") : root.meeting ? S.fmt("meetingAt", root.time(root.meeting.startTs)) : ""
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                PC3.Label {
                    Layout.fillWidth: true
                    text: root.call ? root.call.name : root.meeting ? root.meeting.title : ""
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    opacity: 0.75
                    font: Kirigami.Theme.smallFont
                }
            }
            PC3.Button {
                visible: root.call !== null || root.joinable(root.meeting)
                text: root.roomy ? S.tr("joinCall") : ""
                icon.name: "call-start"
                Accessible.name: S.tr("joinCall")
                onClicked: root.call ? bridge.launch("orneos-meet --call=" + bridge.quote(root.call.token))
                                     : Qt.openUrlExternally(root.meeting.meet)
            }
        }
    }

    // ── Small: what waits ──
    ColumnLayout {
        visible: !root.roomy && bridge.result.ready && root.call === null
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 0
        PC3.Label {
            text: String(root.waiting)
            color: root.tint
            font.pixelSize: Kirigami.Units.gridUnit * 2.4
            font.weight: Font.Bold
            font.features: {"tnum": 1}
        }
        PC3.Label {
            Layout.fillWidth: true
            text: root.waiting ? S.fmt("waitingCount", "").trim() : S.tr("noneWaiting")
            opacity: 0.7
        }
        Item { Layout.fillHeight: true }
        PC3.Label {
            Layout.fillWidth: true
            visible: root.rooms.length > 0
            text: root.rooms.length ? root.rooms[0].name : ""
            textFormat: Text.PlainText
            elide: Text.ElideRight
            font.weight: Font.DemiBold
        }
    }

    // ── Wide or tall: the conversations ──
    PC3.Label {
        visible: root.roomy && bridge.result.ready && root.rooms.length === 0
        text: S.tr("emptyMeet")
        opacity: 0.65
    }
    ListView {
        id: list
        visible: root.roomy
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: 2
        interactive: contentHeight > height
        model: root.rooms
        delegate: Item {
            id: row
            required property var modelData
            width: list.width
            height: line.implicitHeight + Kirigami.Units.smallSpacing * 2
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
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 1.7
                    Layout.preferredHeight: Layout.preferredWidth
                    radius: row.modelData.one ? width / 2 : Ornis.t.radius.control
                    color: root.color(row.modelData.name)
                    PC3.Label {
                        anchors.centerIn: parent
                        text: root.initials(row.modelData.name)
                        color: "white"
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.85
                        font.weight: Font.Bold
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        Layout.fillWidth: true
                        text: row.modelData.name
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        font.weight: row.modelData.waiting ? Font.DemiBold : Font.Normal
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: (row.modelData.actor ? row.modelData.actor + " : " : "") + row.modelData.last
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        opacity: 0.7
                        font: Kirigami.Theme.smallFont
                    }
                }
                ColumnLayout {
                    spacing: 2
                    PC3.Label {
                        Layout.alignment: Qt.AlignRight
                        text: S.stamp(row.modelData.stamp)
                        opacity: 0.65
                        font: Kirigami.Theme.smallFont
                    }
                    Rectangle {
                        visible: row.modelData.unread > 0
                        Layout.alignment: Qt.AlignRight
                        implicitWidth: Math.max(height, count.implicitWidth + 10)
                        implicitHeight: count.implicitHeight + 2
                        radius: height / 2
                        color: row.modelData.waiting ? root.tint : Qt.alpha(Kirigami.Theme.textColor, 0.2)
                        PC3.Label {
                            id: count
                            anchors.centerIn: parent
                            text: row.modelData.mention ? "@" : String(row.modelData.unread)
                            color: row.modelData.waiting ? (root.dark ? Ornis.t.brand.nuit : "white") : Kirigami.Theme.textColor
                            font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.85
                            font.weight: Font.Bold
                        }
                    }
                }
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: bridge.launch("orneos-meet --room=" + bridge.quote(row.modelData.token))
                Accessible.role: Accessible.Button
                Accessible.name: row.modelData.name + (row.modelData.unread ? " · " + row.modelData.unread : "")
            }
        }
    }
}
