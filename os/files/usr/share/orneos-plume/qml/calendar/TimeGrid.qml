// Day and week views: day headers, the band of all-day and multi-day events (one bar across the days they
// cover), then 24 hours that scroll. Overlapping events sit side by side. The saffron line is now.
// With the mouse: a click on an empty slot creates an event there, a drag over the slots creates one that long;
// an event of mine moves by dragging it (to another time or day) and lengthens by its lower edge. The change
// shows at once; a recurring event first asks which occurrences (moveRequested).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/dates.js" as D
import "../components/colors.js" as Colors

Rectangle {
    id: grid
    property date start: D.startOfWeek(new Date())
    property int days: 7
    property var items: []
    signal eventClicked(var occ, Item anchorItem)
    signal slotClicked(date when, bool allDay)
    signal rangeSelected(date from, date to)
    signal dayClicked(date day)
    signal moveRequested(var occ, date from, date to)

    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    readonly property real gutter: 56
    readonly property real hourH: 56
    readonly property real colW: (width - gutter) / days
    readonly property int snap: 15                 // minutes: what a drag moves by
    property date now: new Date()

    color: c.card

    Timer { interval: 60000; running: true; repeat: true; onTriggered: grid.now = new Date() }

    function dayStart(i) { return D.addDays(grid.start, i) }
    function dayIndex(d) { return Math.round((D.startOfDay(d) - D.startOfDay(grid.start)) / 86400000) }
    function long_(occ) { return occ.allDay || (new Date(occ.end) - new Date(occ.start)) >= 86400000 }

    // the band: all-day events and those of 24 hours or more, one bar each, in lanes
    readonly property var bars: {
        const list = items.filter(o => long_(o)).map(o => {
            const s = new Date(o.start), e = new Date(o.end)
            const last = new Date(+e === +s ? +e : e - 1)
            return { occ: o, from: Math.max(0, dayIndex(s)), to: Math.min(days - 1, dayIndex(last)),
                     cutLeft: dayIndex(s) < 0, cutRight: dayIndex(last) > days - 1 }
        }).filter(b => b.from <= days - 1 && b.to >= 0 && b.to >= b.from)
        list.sort((a, b) => a.from - b.from || (b.to - b.from) - (a.to - a.from))
        const lanes = []
        for (const b of list) {
            let lane = lanes.findIndex(end => end < b.from)
            if (lane < 0) { lane = lanes.length; lanes.push(-1) }
            lanes[lane] = b.to
            b.lane = lane
        }
        return list
    }
    readonly property int bandRows: Math.max(1, bars.reduce((m, b) => Math.max(m, b.lane + 1), 0))

    function timed(i) {
        const ds = dayStart(i), de = D.addDays(ds, 1)
        const out = []
        for (const occ of items) {
            if (long_(occ))
                continue
            const s = new Date(occ.start), e = new Date(occ.end)
            if (!(s < de && (e > ds || (+e === +s && s >= ds))))
                continue
            const top = Math.max(0, (s - ds) / 60000) * hourH / 60
            const bottom = Math.min(24 * 60, (e - ds) / 60000) * hourH / 60
            out.push({ occ: occ, top: top, height: Math.max(22, bottom - top), cutTop: s < ds, cutBottom: e > de })
        }
        return D.layoutDay(out)
    }

    function scrollToMorning() {
        let target = (plume.prefs.cal_day_start || 7) * hourH
        for (let i = 0; i < days; ++i)
            if (D.sameDay(dayStart(i), now))
                target = Math.max(0, (now.getHours() - 1.5) * hourH)
        flick.contentY = Math.min(target, Math.max(0, flick.contentHeight - flick.height))
    }
    onStartChanged: Qt.callLater(scrollToMorning)
    Component.onCompleted: Qt.callLater(scrollToMorning)

    // ---- dragging: one ghost for creating, moving or lengthening ------------------------------------------
    // ghost: {kind: "create"|"move"|"resize", col, from, to (minutes of that day), occ}
    property var ghost: null
    function minutesAt(y) { return Math.max(0, Math.min(24 * 60, Math.round(y / hourH * 60 / snap) * snap)) }
    function colAt(x) { return Math.max(0, Math.min(days - 1, Math.floor((x - gutter) / colW))) }
    function at(col, minutes) {
        const d = dayStart(col)
        return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, minutes)
    }
    function finish() {
        const g = ghost
        ghost = null
        if (!g)
            return
        if (g.kind === "create")
            rangeSelected(at(g.col, Math.min(g.from, g.to)), at(g.col, Math.max(g.from, g.to)))
        else if (g.from !== g.startFrom || g.to !== g.startTo || g.col !== g.startCol)
            moveRequested(g.occ, at(g.col, g.from), at(g.col, g.to))
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // day headers
        Row {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            Item { width: grid.gutter; height: 56 }
            Repeater {
                model: grid.days
                AbstractButton {
                    id: head
                    required property int index
                    readonly property date day: grid.dayStart(index)
                    readonly property bool today: D.sameDay(day, grid.now)
                    width: grid.colW; height: 56
                    hoverEnabled: true
                    Accessible.name: grid.loc.toString(day, Locale.LongFormat)
                    onClicked: grid.dayClicked(day)
                    background: Rectangle {
                        color: head.hovered ? grid.c.hover : (head.day.getDay() % 6 === 0 ? grid.c.bg : "transparent")
                        Rectangle { width: 1; height: parent.height; color: grid.c.hairline }
                    }
                    contentItem: Column {
                        leftPadding: 10; topPadding: 8
                        spacing: 0
                        Text {
                            text: grid.loc.dayName(head.day.getDay(), Locale.ShortFormat).toUpperCase().replace(".", "") + "."
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.7
                            color: head.today ? grid.c.accent : grid.c.muted
                        }
                        Row {
                            spacing: 6
                            Text {
                                text: head.day.getDate()
                                font.family: "JetBrains Mono"; font.pixelSize: 18; font.weight: head.today ? Font.Medium : Font.Normal
                                color: head.today ? grid.c.accent : grid.c.text
                            }
                            Rectangle {
                                visible: head.today
                                anchors.verticalCenter: parent.verticalCenter
                                width: 16; height: 3; color: grid.c.saffron
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: grid.c.line }

        // the band: a click on an empty day creates an all-day event there
        Item {
            id: band
            Layout.fillWidth: true
            Layout.preferredHeight: grid.bandRows * 26 + 6
            Text {
                width: grid.gutter - 8; height: parent.height
                horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter
                text: plume.t.all_day_short
                font.family: "JetBrains Mono"; font.pixelSize: 11
                color: grid.c.muted
            }
            Repeater {
                model: grid.days
                MouseArea {
                    required property int index
                    x: grid.gutter + index * grid.colW
                    width: grid.colW; height: band.height
                    cursorShape: Qt.PointingHandCursor
                    Accessible.role: Accessible.Button
                    Accessible.name: plume.t.new_all_day
                    onClicked: grid.slotClicked(grid.dayStart(index), true)
                    Rectangle { width: 1; height: parent.height; color: grid.c.hairline }
                }
            }
            Repeater {
                model: grid.bars
                AbstractButton {
                    id: chip
                    required property var modelData
                    x: grid.gutter + modelData.from * grid.colW + 4
                    y: 3 + modelData.lane * 26
                    width: (modelData.to - modelData.from + 1) * grid.colW - 8
                    height: 24
                    hoverEnabled: true
                    opacity: modelData.occ.myStatus === "DECLINED" ? 0.55 : 1
                    Accessible.name: (modelData.occ.title || plume.t.untitled)
                    onClicked: grid.eventClicked(modelData.occ, chip)
                    background: Rectangle {
                        radius: 5
                        // a task of Tâches: outlined, a ring before its title
                        color: chip.modelData.occ.task ? (chip.hovered ? grid.c.hover : "transparent")
                               : Colors.tint(Colors.display(chip.modelData.occ.color, theme.dark), (theme.dark ? 0.32 : 0.16) + (chip.hovered ? 0.06 : 0))
                        border.width: chip.modelData.occ.myStatus === "NEEDS-ACTION" || chip.modelData.occ.task ? 1.5 : 0
                        border.color: Colors.display(chip.modelData.occ.color, theme.dark)
                    }
                    contentItem: Text {
                        leftPadding: chip.modelData.cutLeft ? 4 : 8; rightPadding: 6
                        text: (chip.modelData.cutLeft ? "‹ " : "") + (chip.modelData.occ.task ? "○ " + (chip.modelData.occ.time ? chip.modelData.occ.time + " " : "") : "")
                              + (chip.modelData.occ.title || plume.t.untitled)
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                        font.strikeout: chip.modelData.occ.myStatus === "DECLINED"
                        color: grid.c.text
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: grid.c.line }

        // the hours
        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentHeight: 24 * grid.hourH
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: grid.ghost === null
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Item {
                id: hours
                width: flick.width; height: flick.contentHeight

                Repeater {
                    model: 24
                    Item {
                        required property int index
                        y: index * grid.hourH
                        width: parent.width; height: grid.hourH
                        Rectangle { x: grid.gutter; width: parent.width - grid.gutter; height: 1; color: grid.c.hairline; visible: index > 0 }
                        Text {
                            visible: index > 0
                            width: grid.gutter - 10; y: -7
                            horizontalAlignment: Text.AlignRight
                            text: String(index).padStart(2, "0") + ":00"
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: grid.c.muted
                        }
                    }
                }

                Repeater {
                    model: grid.days
                    Item {
                        id: column
                        required property int index
                        readonly property date day: grid.dayStart(index)
                        x: grid.gutter + index * grid.colW
                        width: grid.colW; height: parent.height
                        Rectangle { anchors.fill: parent; color: grid.c.bg; opacity: 0.55; visible: column.day.getDay() % 6 === 0 }
                        Rectangle { width: 1; height: parent.height; color: grid.c.hairline }
                        // a click: an event of the default length; a drag: one that long
                        MouseArea {
                            anchors.fill: parent
                            property real pressY: 0
                            property bool moved: false
                            preventStealing: true
                            onPressed: mouse => { pressY = mouse.y; moved = false }
                            onPositionChanged: mouse => {
                                if (!grid.ghost && Math.abs(mouse.y - pressY) < 6)
                                    return
                                moved = true
                                const a = Math.floor(pressY / grid.hourH * 60 / grid.snap) * grid.snap
                                grid.ghost = { kind: "create", col: column.index, from: a,
                                               to: Math.max(a + grid.snap, grid.minutesAt(mouse.y)) }
                                if (mouse.y < pressY)
                                    grid.ghost = { kind: "create", col: column.index, from: grid.minutesAt(mouse.y), to: a + grid.snap }
                            }
                            onReleased: grid.finish()
                            onCanceled: grid.ghost = null
                            onClicked: mouse => {
                                if (moved) return
                                const minutes = Math.floor(mouse.y / grid.hourH * 2) * 30
                                grid.slotClicked(grid.at(column.index, minutes), false)
                            }
                        }
                        Repeater {
                            model: grid.timed(column.index)
                            EventBlock {
                                id: block
                                required property var modelData
                                occ: modelData.occ
                                cutTop: modelData.cutTop
                                cutBottom: modelData.cutBottom
                                x: 3 + modelData.col * (column.width - 6) / modelData.cols
                                y: modelData.top + 1
                                width: (column.width - 6) / modelData.cols - 2
                                height: modelData.height - 2
                                opacity: grid.ghost && grid.ghost.occ && grid.ghost.occ.key === modelData.occ.key ? 0.35 : 1
                                onClicked: grid.eventClicked(modelData.occ, this)
                                // drag to move, lower edge to lengthen (only mine, and not cut by the day)
                                MouseArea {
                                    id: mover
                                    anchors.fill: parent
                                    enabled: block.occ.movable && !block.cutTop && !block.cutBottom
                                    cursorShape: pressed && moved ? Qt.ClosedHandCursor : resizing ? Qt.SizeVerCursor : Qt.PointingHandCursor
                                    preventStealing: true
                                    property point origin
                                    property bool resizing: false
                                    property bool moved: false
                                    hoverEnabled: true
                                    onPositionChanged: mouse => {
                                        if (!pressed) {
                                            resizing = mouse.y > height - 7 && height > 30
                                            return
                                        }
                                        const p = mapToItem(hours, mouse.x, mouse.y)
                                        if (!grid.ghost && Math.abs(p.x - origin.x) < 6 && Math.abs(p.y - origin.y) < 6)
                                            return
                                        moved = true
                                        const s = new Date(block.occ.start), e = new Date(block.occ.end)
                                        const from = D.minutes(s), length = Math.round((e - s) / 60000)
                                        if (resizing) {
                                            grid.ghost = { kind: "resize", occ: block.occ, col: column.index, from: from,
                                                           to: Math.max(from + grid.snap, grid.minutesAt(p.y)),
                                                           startCol: column.index, startFrom: from, startTo: from + length }
                                        } else {
                                            const delta = Math.round((p.y - origin.y) / grid.hourH * 60 / grid.snap) * grid.snap
                                            const f = Math.max(0, Math.min(24 * 60 - length, from + delta))
                                            grid.ghost = { kind: "move", occ: block.occ, col: grid.colAt(p.x), from: f, to: f + length,
                                                           startCol: column.index, startFrom: from, startTo: from + length }
                                        }
                                    }
                                    onPressed: mouse => { origin = mapToItem(hours, mouse.x, mouse.y); moved = false }
                                    onReleased: grid.finish()
                                    onCanceled: grid.ghost = null
                                    onExited: if (!pressed) resizing = false
                                    onClicked: if (!moved) grid.eventClicked(block.occ, block)
                                }
                            }
                        }
                        Rectangle {
                            visible: D.sameDay(column.day, grid.now)
                            y: D.minutes(grid.now) * grid.hourH / 60 - 1
                            width: parent.width; height: 2
                            color: grid.c.saffron
                            Rectangle { x: -4; y: -3; width: 8; height: 8; radius: 4; color: grid.c.saffron }
                        }
                    }
                }

                // the ghost of what the drag will make: where, and the hours
                Rectangle {
                    visible: grid.ghost !== null
                    readonly property var g: grid.ghost || { col: 0, from: 0, to: 0 }
                    readonly property color tone: g.occ ? Colors.display(g.occ.color, theme.dark) : grid.c.action
                    x: grid.gutter + g.col * grid.colW + 3
                    y: Math.min(g.from, g.to) * grid.hourH / 60 + 1
                    width: grid.colW - 6
                    height: Math.max(20, Math.abs(g.to - g.from) * grid.hourH / 60 - 2)
                    radius: 6
                    color: Qt.rgba(tone.r, tone.g, tone.b, theme.dark ? 0.38 : 0.22)
                    border.width: 1.5; border.color: tone
                    Text {
                        x: 8; y: 4
                        width: parent.width - 12
                        elide: Text.ElideRight
                        text: (parent.g.occ ? (parent.g.occ.title || plume.t.untitled) + "\n" : "")
                              + D.hm(grid.at(0, Math.min(parent.g.from, parent.g.to))) + " – " + D.hm(grid.at(0, Math.max(parent.g.from, parent.g.to)))
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        color: grid.c.text
                    }
                }
            }
        }
    }
}
