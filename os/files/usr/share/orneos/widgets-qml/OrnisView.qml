// SPDX-License-Identifier: GPL-2.0-or-later
// Ornis on the desktop: an offer drawn from the day (prepare the next event), a field to ask anything, and,
// when there is room, the recent conversations. Not a shortcut to the app: it proposes something to do.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S

Frame {
    id: root
    property int limit: 8
    readonly property var feed: sessions
    readonly property var rows: (sessions.result.items || []).slice(0, Math.max(1, Math.min(20, limit)))
    // The next timed event of the coming three hours, if any.
    readonly property var nextEvent: {
        const now = Date.now() / 1000;
        return (day.result.events || []).find(e => !e.allDay && e.startTs > now && e.startTs - now < 3 * 3600) || null;
    }
    readonly property string offer: nextEvent ? S.fmt("suggestPrepare", nextEvent.title,
        Qt.locale().toString(new Date(nextEvent.startTs * 1000), Qt.locale().timeFormat(Locale.ShortFormat))) : ""

    family: "tools"
    context: "Ornis"
    ai: true
    actionIcon: "list-add"
    actionText: S.tr("newConversation")
    onAction: sessions.launch("ornis --new")
    onOpened: sessions.launch("ornis")

    function ask(text) {
        const q = text.trim();
        if (q) sessions.launch("ornis --ask=" + sessions.quote(q));
    }

    Bridge {
        id: sessions
        command: "/usr/libexec/orneos-widget assistant --folder=''"
        interval: 60000
    }
    Bridge {
        id: day
        command: "/usr/libexec/orneos-widget agenda --start=" + Qt.formatDate(new Date(), "yyyy-MM-dd") + " --days=1"
        interval: 300000
    }

    // The offer: a question Ornis can take right away.
    PC3.Label {
        visible: root.offer !== ""
        Layout.fillWidth: true
        text: root.offer
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        maximumLineCount: root.roomy ? 2 : 3
        elide: Text.ElideRight
        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.15
        font.weight: Font.DemiBold
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.ask(root.offer)
        }
        Accessible.role: Accessible.Button
        Accessible.name: text
    }
    Item { visible: !root.roomy; Layout.fillHeight: true }
    PC3.TextField {
        id: question
        Layout.fillWidth: true
        placeholderText: S.tr("askPlaceholder")
        Accessible.name: placeholderText
        onAccepted: { root.ask(text); clear(); }
    }

    PC3.Label {
        visible: root.roomy && root.rows.length > 0
        Layout.topMargin: Kirigami.Units.smallSpacing
        text: S.tr("recentConversations")
        opacity: 0.65
        font: Kirigami.Theme.smallFont
    }
    PC3.Label {
        visible: root.roomy && !sessions.result.ready && sessions.result.state !== "loading"
        Layout.fillWidth: true
        text: S.tr(sessions.result.state || "loading")
        wrapMode: Text.WordWrap
        opacity: 0.7
        font: Kirigami.Theme.smallFont
    }
    ListView {
        id: list
        visible: root.roomy
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        interactive: contentHeight > height
        model: root.rows
        delegate: Item {
            id: row
            required property var modelData
            width: list.width
            height: label.implicitHeight + Kirigami.Units.smallSpacing * 2
            Rectangle {
                anchors.fill: parent
                radius: 6
                color: mouse.containsMouse ? Qt.alpha(Kirigami.Theme.textColor, 0.07) : "transparent"
            }
            PC3.Label {
                id: label
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 4; rightMargin: 4 }
                text: row.modelData.title
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: sessions.launch("ornis --session=" + sessions.quote(row.modelData.id))
                Accessible.role: Accessible.Button
                Accessible.name: row.modelData.title
            }
        }
    }
}
