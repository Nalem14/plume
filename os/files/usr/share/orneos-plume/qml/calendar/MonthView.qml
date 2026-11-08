// Month view: five or six weeks. Each event is a line in its week, one bar across the days it covers; what does
// not fit becomes "+N" on its day (a click opens the day). A click on an empty part of a day creates an all-day
// event there; an event of mine moves to another day by dragging it.
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "../components"
import "../components/dates.js" as D
import "../components/colors.js" as Colors

Rectangle {
    id: month
    property date shown: new Date()
    property var items: []
    signal eventClicked(var occ, Item anchorItem)
    signal dayClicked(date day)
    signal slotClicked(date when, bool allDay)
    signal moveRequested(var occ, int days)

    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    readonly property date first: D.startOfWeek(D.startOfMonth(shown))
    readonly property int weeks: D.addDays(first, 35).getMonth() === shown.getMonth() ? 6 : 5
    readonly property real cellW: width / 7
    readonly property real rowH: (height - 33) / weeks
    readonly property int lineH: 22
    readonly property int fits: Math.max(0, Math.floor((rowH - 34) / lineH))
    property date now: new Date()
    Timer { interval: 60000; running: true; repeat: true; onTriggered: month.now = new Date() }
    color: c.card

    function dayIndex(d) { return Math.round((D.startOfDay(d) - D.startOfDay(first)) / 86400000) }

    // per week: the bars [{occ, from, to (0-6), lane}] and, per day, how many could not be shown
    readonly property var layout: {
        const out = []
        for (let w = 0; w < weeks; ++w) out.push({ bars: [], hidden: [0, 0, 0, 0, 0, 0, 0] })
        const spans = items.map(o => {
            const s = new Date(o.start), e = new Date(o.end)
            const last = +e === +s ? s : new Date(e - 1)
            return { occ: o, a: dayIndex(s), b: dayIndex(last), long: (dayIndex(last) > dayIndex(s) || o.allDay) && !o.task }
        })
        for (let w = 0; w < weeks; ++w) {
            const lo = w * 7, hi = lo + 6
            const here = spans.filter(x => x.a <= hi && x.b >= lo)
                              .map(x => ({ occ: x.occ, from: Math.max(0, x.a - lo), to: Math.min(6, x.b - lo), long: x.long,
                                           cutLeft: x.a < lo, cutRight: x.b > hi }))
            here.sort((p, q) => p.from - q.from || (q.long - p.long) || (q.to - q.from) - (p.to - p.from)
                                || p.occ.startTs - q.occ.startTs)
            const lanes = []           // per lane: the days taken
            for (const bar of here) {
                let lane = 0
                while (lanes[lane] && lanes[lane].some((taken, d) => taken && d >= bar.from && d <= bar.to)) ++lane
                if (!lanes[lane]) lanes[lane] = [false, false, false, false, false, false, false]
                for (let d = bar.from; d <= bar.to; ++d) lanes[lane][d] = true
                bar.lane = lane
            }
            // a day with more than fits keeps its last line for "+N"; a bar that does not fit is counted on each of its days
            const counts = [0, 1, 2, 3, 4, 5, 6].map(d => lanes.filter(l => l[d]).length)
            const shown = bar => {
                for (let d = bar.from; d <= bar.to; ++d)
                    if (counts[d] > fits ? bar.lane >= fits - 1 : bar.lane >= fits) return false
                return true
            }
            for (const bar of here) {
                if (shown(bar)) out[w].bars.push(bar)
                else for (let d = bar.from; d <= bar.to; ++d) out[w].hidden[d] += 1
            }
        }
        return out
    }

    // dragging an event: which day it would land on
    property var drag: null              // {occ, days, week, col}

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Row {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            Repeater {
                model: 7
                Text {
                    required property int index
                    width: month.cellW; height: 32
                    leftPadding: 10; verticalAlignment: Text.AlignVCenter
                    text: month.loc.dayName((index + 1) % 7, Locale.ShortFormat).toUpperCase().replace(".", "") + "."
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.7
                    color: month.c.muted
                }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: month.c.line }
        Item {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true

            Repeater {
                model: month.weeks
                Item {
                    id: week
                    required property int index
                    readonly property var info: month.layout[index] || { bars: [], hidden: [] }
                    y: index * month.rowH
                    width: body.width; height: month.rowH

                    // the days: background, number, empty part to create
                    Repeater {
                        model: 7
                        Rectangle {
                            id: cell
                            required property int index
                            readonly property date day: D.addDays(month.first, week.index * 7 + index)
                            readonly property bool inMonth: day.getMonth() === month.shown.getMonth()
                            readonly property bool today: D.sameDay(day, month.now)
                            readonly property bool target: month.drag !== null && month.drag.week === week.index && month.drag.col === index
                            x: index * month.cellW
                            width: month.cellW; height: week.height
                            color: target ? Colors.tint(month.c.action, 0.10) : inMonth ? "transparent" : month.c.bg
                            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: month.c.hairline }
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: month.c.hairline }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                Accessible.role: Accessible.Button
                                Accessible.name: plume.t.new_all_day + ", " + month.loc.toString(cell.day, Locale.LongFormat)
                                onClicked: month.slotClicked(cell.day, true)
                            }
                            AbstractButton {
                                id: number
                                x: 6; y: 5
                                implicitWidth: Math.max(26, label.implicitWidth + 10); implicitHeight: 24
                                hoverEnabled: true
                                Accessible.name: month.loc.toString(cell.day, Locale.LongFormat)
                                onClicked: month.dayClicked(cell.day)
                                background: Rectangle {
                                    radius: 12
                                    color: cell.today ? month.c.action : number.hovered ? month.c.hover : "transparent"
                                }
                                contentItem: Text {
                                    id: label
                                    text: cell.day.getDate() === 1 ? cell.day.getDate() + " " + month.loc.monthName(cell.day.getMonth(), Locale.ShortFormat) : cell.day.getDate()
                                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    font.family: "JetBrains Mono"; font.pixelSize: 12
                                    color: cell.today ? month.c.actionText : cell.inMonth ? month.c.text : month.c.faint
                                }
                            }
                            Text {
                                visible: (week.info.hidden[cell.index] || 0) > 0 && month.fits > 0
                                x: 10
                                y: 32 + (month.fits - 1) * month.lineH
                                height: month.lineH - 2
                                verticalAlignment: Text.AlignVCenter
                                text: plume.t.more_events.replace("%1", week.info.hidden[cell.index] || 0)
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                                color: month.c.accent
                                MouseArea { anchors.fill: parent; anchors.margins: -3; cursorShape: Qt.PointingHandCursor; onClicked: month.dayClicked(cell.day) }
                            }
                        }
                    }

                    // the events
                    Repeater {
                        model: week.info.bars
                        AbstractButton {
                            id: chip
                            required property var modelData
                            readonly property var occ: modelData.occ
                            readonly property bool bar: modelData.long
                            readonly property color tone: Colors.display(occ.color, theme.dark)
                            x: modelData.from * month.cellW + (modelData.cutLeft ? 0 : 4)
                            y: 32 + modelData.lane * month.lineH
                            width: (modelData.to - modelData.from + 1) * month.cellW - (modelData.cutLeft ? 0 : 4) - (modelData.cutRight ? 0 : 5)
                            height: month.lineH - 2
                            hoverEnabled: true
                            opacity: (month.drag && month.drag.occ.key === occ.key ? 0.4 : 1) * (occ.myStatus === "DECLINED" ? 0.6 : 1)
                            Accessible.name: (occ.title || plume.t.untitled)
                            onClicked: month.eventClicked(occ, chip)
                            background: Rectangle {
                                radius: 4
                                topLeftRadius: chip.modelData.cutLeft ? 0 : 4; bottomLeftRadius: chip.modelData.cutLeft ? 0 : 4
                                topRightRadius: chip.modelData.cutRight ? 0 : 4; bottomRightRadius: chip.modelData.cutRight ? 0 : 4
                                color: chip.bar ? Colors.tint(chip.tone, (theme.dark ? 0.32 : 0.16) + (chip.hovered ? 0.06 : 0))
                                                : chip.hovered ? month.c.hover : "transparent"
                                border.width: chip.occ.myStatus === "NEEDS-ACTION" ? 1.2 : 0
                                border.color: chip.tone
                            }
                            contentItem: Row {
                                spacing: 5
                                leftPadding: 4
                                clip: true
                                Rectangle {
                                    visible: !chip.bar
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7; height: 7; radius: chip.occ.task ? 2 : 3.5
                                    color: chip.occ.task ? "transparent" : chip.tone
                                    border.width: chip.occ.task ? 1.3 : 0; border.color: chip.tone
                                }
                                Text {
                                    visible: !chip.bar && (!chip.occ.allDay || !!chip.occ.time)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: chip.occ.task ? chip.occ.time : D.hm(new Date(chip.occ.start))
                                    font.family: "JetBrains Mono"; font.pixelSize: 11
                                    color: month.c.muted
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: chip.width - (chip.bar ? 10 : chip.occ.allDay && !chip.occ.time ? 20 : 58)
                                    text: (chip.modelData.cutLeft ? "‹ " : "") + (chip.occ.title || plume.t.untitled)
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                    font.weight: chip.bar ? Font.DemiBold : Font.Medium
                                    font.strikeout: chip.occ.myStatus === "DECLINED"
                                    color: month.c.text
                                }
                            }
                            // drag to another day (mine only)
                            MouseArea {
                                anchors.fill: parent
                                enabled: chip.occ.movable
                                cursorShape: moved ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                                preventStealing: true
                                property point origin
                                property bool moved: false
                                property int grab: 0            // the day of the bar under the mouse when it was taken
                                onPressed: mouse => {
                                    origin = mapToItem(body, mouse.x, mouse.y)
                                    grab = Math.floor(origin.x / month.cellW) - chip.modelData.from
                                    moved = false
                                }
                                onPositionChanged: mouse => {
                                    const p = mapToItem(body, mouse.x, mouse.y)
                                    if (!moved && Math.abs(p.x - origin.x) < 6 && Math.abs(p.y - origin.y) < 6)
                                        return
                                    moved = true
                                    const w = Math.max(0, Math.min(month.weeks - 1, Math.floor(p.y / month.rowH)))
                                    const col = Math.max(0, Math.min(6, Math.floor(p.x / month.cellW)))
                                    const from0 = week.index * 7 + Math.floor(origin.x / month.cellW)
                                    month.drag = { occ: chip.occ, week: w, col: col, days: w * 7 + col - from0 }
                                }
                                onReleased: {
                                    const d = month.drag
                                    month.drag = null
                                    if (moved && d && d.days !== 0)
                                        month.moveRequested(d.occ, d.days)
                                }
                                onCanceled: month.drag = null
                                onClicked: if (!moved) month.eventClicked(chip.occ, chip)
                            }
                        }
                    }
                }
            }
        }
    }
}
