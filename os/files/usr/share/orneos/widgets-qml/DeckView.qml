// SPDX-License-Identifier: GPL-2.0-or-later
// Deck on the desktop: the cards with a due date, assigned to you or to nobody (the cloud's Upcoming page).
// Small: how many, and how many are late (vermilion: they ask for action). Wide or tall: the cards by when
// they are due, each with its board's colour. A click opens the card in the cloud.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    property int limit: 8
    readonly property var feed: bridge
    readonly property var cards: bridge.result.items || []
    readonly property var rows: cards.slice(0, Math.max(1, Math.min(20, limit)))
    readonly property int late: cards.filter(c => c.bucket === "overdue").length
    readonly property var titles: ({overdue: "overdueCards", today: "dueToday", tomorrow: "dueTomorrow", nextSevenDays: "dueWeek", later: "dueLater"})

    family: "organize"
    context: S.tr("deck")
    actionIcon: "view-kanban"
    actionText: S.tr("openDeck")
    onAction: bridge.launch("/usr/libexec/orneos-app deck")
    onOpened: bridge.launch("/usr/libexec/orneos-app deck")

    function open(card) { if (/^https:\/\//.test(card.url)) bridge.launch("xdg-open " + bridge.quote(card.url)); }
    function due(card) {
        const d = new Date(card.due * 1000);
        return card.bucket === "today" || card.bucket === "overdue" && d.toDateString() === new Date().toDateString()
            ? Qt.locale().toString(d, Qt.locale().timeFormat(Locale.ShortFormat)) : Qt.locale().toString(d, "ddd d MMM");
    }

    Bridge { id: bridge; command: "/usr/libexec/orneos-widget deck"; interval: 300000 }

    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: root.roomy ? 4 : 2
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        visible: text !== ""
        Layout.fillWidth: true
        text: ["signed_out", "error", "noDeck"].indexOf(bridge.result.state) >= 0 ? S.tr(bridge.result.state)
              : bridge.result.ready && root.cards.length === 0 ? S.tr("emptyDeck") : ""
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }

    // ── Small: the count ──
    ColumnLayout {
        visible: !root.roomy && root.cards.length > 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 0
        PC3.Label {
            text: String(root.cards.length)
            color: root.tint
            font.pixelSize: Kirigami.Units.gridUnit * 2.4
            font.weight: Font.Bold
            font.features: {"tnum": 1}
        }
        PC3.Label {
            Layout.fillWidth: true
            text: (root.cards.length === 1 ? S.tr("cardsOne") : S.fmt("cardsCount", "")).replace(/^\s*1?\s*/, "")
            wrapMode: Text.WordWrap
            opacity: 0.7
        }
        PC3.Label {
            visible: root.late > 0
            text: S.fmt("lateShort", root.late)
            color: Ornis.t.brand.vermillon
            font.weight: Font.DemiBold
        }
        Item { Layout.fillHeight: true }
        PC3.Label {
            Layout.fillWidth: true
            text: root.cards.length ? root.cards[0].title : ""
            textFormat: Text.PlainText
            elide: Text.ElideRight
            font.weight: Font.DemiBold
        }
    }

    // ── Wide or tall: by when they are due ──
    ListView {
        id: list
        visible: root.roomy
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: 3
        interactive: contentHeight > height
        model: root.rows
        delegate: Column {
            id: entry
            required property var modelData
            required property int index
            width: list.width
            spacing: 2
            // The group's title before its first card (a JS array has no sections).
            PC3.Label {
                visible: entry.index === 0 || root.rows[entry.index - 1].bucket !== entry.modelData.bucket
                width: parent.width
                topPadding: entry.index ? Kirigami.Units.smallSpacing : 0
                text: S.tr(root.titles[entry.modelData.bucket] || entry.modelData.bucket)
                color: entry.modelData.bucket === "overdue" ? Ornis.t.brand.vermillon : root.tint
                font.weight: Font.DemiBold
                font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.85
            }
            Item {
                id: row
                readonly property var modelData: entry.modelData
                width: list.width
                height: line.implicitHeight + Kirigami.Units.smallSpacing * 2
                Rectangle {
                    anchors.fill: parent
                    radius: Ornis.t.radius.control
                    color: area.containsMouse ? Qt.alpha(Kirigami.Theme.textColor, 0.09) : Qt.alpha(Kirigami.Theme.textColor, 0.04)
                }
                Rectangle {
                    width: 3
                    radius: 1.5
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 4 }
                    color: row.modelData.color || root.tint
                }
                RowLayout {
                    id: line
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 14; rightMargin: 6 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        PC3.Label {
                            Layout.fillWidth: true
                            text: row.modelData.title
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                        PC3.Label {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: row.modelData.board
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            opacity: 0.65
                            font: Kirigami.Theme.smallFont
                        }
                    }
                    PC3.Label {
                        text: root.due(row.modelData)
                        color: row.modelData.bucket === "overdue" ? Ornis.t.brand.vermillon : Kirigami.Theme.textColor
                        opacity: row.modelData.bucket === "overdue" ? 1 : 0.65
                        font: Kirigami.Theme.smallFont
                    }
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.open(row.modelData)
                    Accessible.role: Accessible.Link
                    Accessible.name: row.modelData.title + " · " + root.due(row.modelData)
                }
            }
        }
    }
}
