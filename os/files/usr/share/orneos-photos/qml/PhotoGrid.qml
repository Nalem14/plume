// The photos of the view, each at its own proportions, every row the full width (laid out in Python,
// layout.py), under the heading of their day or month. A click opens the viewer; Ctrl+clic, Maj+clic or the
// round mark choose; a rectangle drawn from a gap (or, while choosing, from a photo not chosen) chooses what it
// covers, with Ctrl added to the choice; a drag carries the photos to an album of the sidebar, a note or a task.
// Dragging the scrollbar shows the date reached; Ctrl+wheel changes the size. A long view has its dates down the
// right edge instead of the scrollbar (the years, or the months of a single year): the pointer shows the month
// under it, a click or a drag goes there. From the keyboard: the arrows move a ring from photo to photo (Maj
// adds to the choice), Entrée opens, Espace chooses, Début / Fin.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ListView {
    id: list
    readonly property var c: theme.c
    property var menuFor: []
    property int cursor: -1              // the photo the keyboard is on (its index in photos.order)
    activeFocusOnTab: true
    signal albumWanted(var ids, var item)
    signal editWanted(int fileid)

    // the rail of dates takes its strip of the width; decided by the number of photos, never by the layout it changes
    readonly property bool railed: photos.order.length >= 80
    function relayout() { photos.setWidth(width - (railed ? rail.width + 8 : 0)) }
    onRailedChanged: relayout()
    // the first row of that day (or of the month that holds it)
    function showDay(dayid) {
        const rows = photos.rows
        for (let i = 0; i < rows.length; ++i)
            if (rows[i].kind === "head" && rows[i].dayid <= dayid) { positionViewAtIndex(i, ListView.Beginning); return }
    }
    function headTitle(index) {
        const rows = photos.rows
        for (let i = Math.min(index, rows.length - 1); i >= 0; --i)
            if (rows[i].kind === "head") return rows[i].title
        return ""
    }
    // ---- the rectangle that chooses (in the coordinates of the content: it follows the scrolling) ----
    property var band: null              // {x0, y0, x1, y1, base, tops}
    function rowHeight(r, i) { return r.kind === "head" ? (i === 0 ? 40 : 54) : r.h }
    // the top of every row, from one the ListView placed (it may not start at 0)
    function rowTops() {
        const rows = photos.rows, tops = new Array(rows.length)
        let y = 0
        for (let i = 0; i < rows.length; ++i) { tops[i] = y; y += rowHeight(rows[i], i) + spacing }
        const at = Math.max(0, indexAt(10, contentY + 10))
        const placed = itemAtIndex(at)
        const shift = placed ? placed.y - tops[at] : 0
        return tops.map(t => t + shift)
    }
    // the photo under that point of the content, or null
    function photoAt(x, y, tops) {
        const rows = photos.rows
        for (let i = 0; i < rows.length; ++i) {
            if (y < tops[i]) return null
            if (y >= tops[i] + rowHeight(rows[i], i) || rows[i].kind !== "row") continue
            let left = 0
            for (const it of rows[i].items) {
                if (x >= left && x < left + it.w) return it
                left += it.w + 4
            }
            return null
        }
        return null
    }
    function bandUpdate(point) {
        if (!band) return
        const b = Object.assign({}, band, { x1: point.x, y1: point.y })
        band = b
        const x0 = Math.min(b.x0, b.x1), x1 = Math.max(b.x0, b.x1)
        const y0 = Math.min(b.y0, b.y1), y1 = Math.max(b.y0, b.y1)
        const rows = photos.rows, next = b.base.slice()
        for (let i = 0; i < rows.length; ++i) {
            const top = b.tops[i], bottom = top + rowHeight(rows[i], i)
            if (top > y1) break
            if (bottom < y0 || rows[i].kind !== "row") continue
            let left = 0
            for (const it of rows[i].items) {
                if (left <= x1 && left + it.w >= x0 && next.indexOf(it.fileid) < 0) next.push(it.fileid)
                left += it.w + 4
            }
        }
        win.chosen = next
    }

    // ---- the keyboard ----
    // where each photo sits: its row in the list and the middle of its tile
    function placeOf(i) {
        const rows = photos.rows
        for (let r = 0; r < rows.length; ++r) {
            if (rows[r].kind !== "row") continue
            let left = 0
            for (const it of rows[r].items) {
                if (it.i === i) return { row: r, x: left + it.w / 2 }
                left += it.w + 4
            }
        }
        return null
    }
    function nearestIn(r, x) {
        const items = photos.rows[r].items
        let left = 0, best = items[0].i, gap = 1e9
        for (const it of items) {
            const d = Math.abs(left + it.w / 2 - x)
            if (d < gap) { gap = d; best = it.i }
            left += it.w + 4
        }
        return best
    }
    function moveCursor(to, extend) {
        const n = photos.order.length
        if (!n) return
        to = Math.max(0, Math.min(n - 1, to))
        if (extend) {
            if (win.anchorIndex < 0) win.anchorIndex = cursor >= 0 ? cursor : to
            const range = photos.between(win.anchorIndex, to)
            const next = win.chosen.slice()
            for (const id of range) if (next.indexOf(id) < 0) next.push(id)
            win.chosen = next
        }
        cursor = to
        const place = placeOf(to)
        if (place) positionViewAtIndex(place.row, ListView.Contain)
    }
    function vertical(step) {
        const place = placeOf(cursor)
        if (!place) { moveCursor(0, false); return }
        const rows = photos.rows
        for (let r = place.row + step; r >= 0 && r < rows.length; r += step)
            if (rows[r].kind === "row") return nearestIn(r, place.x)
        return cursor
    }
    Keys.onPressed: event => {
        const shift = (event.modifiers & Qt.ShiftModifier) !== 0
        if (event.modifiers & Qt.ControlModifier) return
        const start = cursor < 0
        if (event.key === Qt.Key_Right) moveCursor(start ? 0 : cursor + 1, shift)
        else if (event.key === Qt.Key_Left) moveCursor(start ? 0 : cursor - 1, shift)
        else if (event.key === Qt.Key_Down) moveCursor(start ? 0 : vertical(1), shift)
        else if (event.key === Qt.Key_Up) moveCursor(start ? 0 : vertical(-1), shift)
        else if (event.key === Qt.Key_Home) moveCursor(0, shift)
        else if (event.key === Qt.Key_End) moveCursor(photos.order.length - 1, shift)
        else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && cursor >= 0) viewer.open(photos.order[cursor])
        else if (event.key === Qt.Key_Space && cursor >= 0) win.clickPhoto(photos.order[cursor], cursor, true)
        else return
        event.accepted = true
    }
    Connections {
        target: photos
        function onViewChanged() { if (list.cursor >= photos.order.length) list.cursor = photos.order.length - 1 }
    }

    function groupIds(key) {
        const out = []
        for (const r of photos.rows)
            if (r.kind === "row" && r.key === key) for (const it of r.items) out.push(it.fileid)
        return out
    }

    // the rows are given by hand: a relayout of the same view (a favourite, a sync, a resize) keeps the photo at
    // the top of the view where it was, another view starts at its top
    model: []
    property string shownView: ""
    function anchorOf() {
        const i = Math.max(0, indexAt(10, contentY + 10))
        const item = itemAtIndex(i), row = model[i]
        if (!row || !item) return null
        return { key: row.kind === "row" ? "f" + row.items[0].fileid : "d" + row.dayid, offset: contentY - item.y }
    }
    function indexOfAnchor(a) {
        const rows = photos.rows
        for (let i = 0; i < rows.length; ++i) {
            const r = rows[i]
            if (a.key[0] === "d" ? r.kind === "head" && "d" + r.dayid === a.key
                                 : r.kind === "row" && r.items.some(it => "f" + it.fileid === a.key)) return i
        }
        return -1
    }
    function takeRows() {
        const same = shownView === photos.view && model.length > 0
        const a = same ? anchorOf() : null
        shownView = photos.view
        model = photos.rows
        if (!same) { positionViewAtBeginning(); return }
        if (!a) return
        const i = indexOfAnchor(a)
        if (i < 0) return
        forceLayout()
        positionViewAtIndex(i, ListView.Beginning)
        const item = itemAtIndex(i)
        if (item) contentY = Math.max(originY, Math.min(item.y + a.offset, originY + Math.max(0, contentHeight - height)))
    }
    Connections {
        target: photos
        function onViewChanged() { list.takeRows() }
    }
    clip: true
    acceptedButtons: Qt.NoButton         // the mouse draws the rectangle; the wheel and touch still scroll
    spacing: 4
    cacheBuffer: 1600
    boundsBehavior: Flickable.StopAtBounds
    reuseItems: true
    onWidthChanged: relayout()
    Component.onCompleted: { takeRows(); relayout(); measure() }

    ScrollBar.vertical: ScrollBar {
        id: bar
        policy: list.railed ? ScrollBar.AlwaysOff : ScrollBar.AsNeeded
        minimumSize: 0.04
    }
    // the date reached while the scrollbar is dragged
    Rectangle {
        visible: bar.pressed && bubbleText.text !== ""
        anchors.right: parent.right; anchors.rightMargin: 22
        y: Math.max(0, Math.min(list.height - height, bar.position * list.height + bar.size * list.height / 2 - height / 2))
        width: bubbleText.implicitWidth + 24; height: 32; radius: 8
        color: list.c.overlay
        border.width: 1; border.color: list.c.overlayLine
        Text {
            id: bubbleText
            anchors.centerIn: parent
            text: list.headTitle(list.indexAt(10, list.contentY + 10))
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
            color: list.c.text
        }
    }

    // ---- the dates down the right edge ----
    // the top of each row in the laid-out content, its total, and the marks of the rail (years, or months)
    property var spans: ({ tops: [], total: 1, marks: [] })
    onModelChanged: measure()
    function dateOf(dayid) { return new Date(dayid * 86400000) }        // a day id: days since 1970, read in UTC
    function monthName(d, brief) {   // not « short »: a reserved word for Qt 6.9 (Plume on Intel Macs)
        const n = Qt.locale().standaloneMonthName(d.getUTCMonth(), brief ? Locale.ShortFormat : Locale.LongFormat)
        return n.charAt(0).toUpperCase() + n.slice(1)
    }
    function measure() {
        const rows = photos.rows, tops = new Array(rows.length), heads = []
        let y = 0
        for (let i = 0; i < rows.length; ++i) {
            tops[i] = y
            if (rows[i].kind === "head" && rows[i].dayid !== undefined) heads.push({ d: dateOf(rows[i].dayid), top: y })
            y += rowHeight(rows[i], i) + spacing
        }
        const years = new Set(heads.map(h => h.d.getUTCFullYear()))
        const marks = []
        let last = ""
        for (const h of heads) {
            const key = years.size > 1 ? String(h.d.getUTCFullYear()) : String(h.d.getUTCMonth())
            if (key === last) continue
            last = key
            marks.push({ label: years.size > 1 ? key : monthName(h.d, true), top: h.top })
        }
        spans = { tops: tops, total: Math.max(1, y), marks: marks }
    }
    // the row at that height of the rail (0 … 1)
    function rowAtFraction(f) {
        const tops = spans.tops, at = Math.max(0, Math.min(1, f)) * spans.total
        let lo = 0, hi = tops.length - 1
        while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (tops[mid] <= at) lo = mid; else hi = mid - 1 }
        return lo
    }
    function monthAtRow(i) {
        const rows = photos.rows
        for (let k = Math.min(i, rows.length - 1); k >= 0; --k)
            if (rows[k].kind === "head" && rows[k].dayid !== undefined) {
                const d = dateOf(rows[k].dayid)
                return monthName(d, false) + " " + d.getUTCFullYear()
            }
        return ""
    }
    Item {
        id: rail
        parent: list                     // over the view, not in its scrolling content
        visible: list.railed && list.spans.marks.length > 0
        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.topMargin: 6; anchors.bottomMargin: 6
        width: 44
        z: 5
        readonly property real pointer: railMouse.containsMouse || railMouse.pressed ? railMouse.mouseY : -1
        // the marks, a label only where it does not touch the one above
        Repeater {
            model: {
                const out = [], h = rail.height
                let lastY = -100
                for (const m of list.spans.marks) {
                    const y = m.top / list.spans.total * h
                    if (y - lastY < 18 || y > h - 8) continue
                    out.push({ label: m.label, y: y })
                    lastY = y
                }
                return out
            }
            Text {
                required property var modelData
                anchors.right: parent.right; anchors.rightMargin: 9
                y: modelData.y - height / 2 + 6
                text: modelData.label
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                color: rail.pointer >= 0 ? list.c.text : list.c.muted
                Behavior on color { ColorAnimation { duration: 120 } }
            }
        }
        // where the view is
        Rectangle {
            anchors.right: parent.right
            width: 3; radius: 1.5
            // measured like the marks: from the row at the top of the view
            height: Math.max(16, list.height / list.spans.total * rail.height)
            y: {
                const i = Math.max(0, list.indexAt(10, list.contentY + 10))
                return Math.max(0, Math.min(rail.height - height, (list.spans.tops[i] || 0) / list.spans.total * rail.height))
            }
            color: list.c.famMedia
            opacity: rail.pointer >= 0 || list.moving ? 0.9 : 0.45
            Behavior on opacity { NumberAnimation { duration: 120 } }
        }
        // under the pointer: a line and the month it leads to
        Rectangle {
            visible: rail.pointer >= 0
            anchors.right: parent.right
            y: rail.pointer
            width: parent.width; height: 2; radius: 1
            color: list.c.action
        }
        Rectangle {
            visible: rail.pointer >= 0 && railMonth.text !== ""
            anchors.right: parent.left; anchors.rightMargin: 6
            y: Math.max(0, Math.min(rail.height - height, rail.pointer - height / 2))
            width: railMonth.implicitWidth + 22; height: 30; radius: 8
            color: list.c.overlay
            border.width: 1; border.color: list.c.overlayLine
            Text {
                id: railMonth
                anchors.centerIn: parent
                text: rail.pointer >= 0 ? list.monthAtRow(list.rowAtFraction(rail.pointer / rail.height)) : ""
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: list.c.text
            }
        }
        MouseArea {
            id: railMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            function go(y) { list.positionViewAtIndex(list.rowAtFraction(y / height), ListView.Beginning) }
            onPressed: mouse => go(mouse.y)
            onPositionChanged: mouse => { if (pressed) go(mouse.y) }
            onWheel: wheel => wheel.accepted = false
        }
    }

    WheelHandler {
        acceptedModifiers: Qt.ControlModifier
        property real turned: 0          // a notch is 120; fine wheels and touchpads send it in pieces
        onWheel: event => {
            turned += event.angleDelta.y
            if (Math.abs(turned) < 120) return
            win.zoomBy(turned > 0 ? 1 : -1)
            turned = 0
        }
    }
    DragHandler {
        id: bandDrag
        target: null
        acceptedDevices: PointerDevice.Mouse
        acceptedButtons: Qt.LeftButton
        dragThreshold: 14                // past the one of a photo's own drag, which wins when it is allowed
        onActiveChanged: {
            if (!active) { list.band = null; return }
            const at = centroid.pressPosition
            const tops = list.rowTops()
            const hit = list.photoAt(at.x, at.y, tops)
            if (hit && (win.chosen.length === 0 || win.isChosen(hit.fileid))) return
            const keep = (centroid.modifiers & Qt.ControlModifier) !== 0
            if (!keep) win.anchorIndex = -1
            list.band = { x0: at.x, y0: at.y, x1: at.x, y1: at.y, base: keep ? win.chosen.slice() : [], tops: tops }
            list.bandUpdate(centroid.position)
        }
        onCentroidChanged: if (active && list.band) list.bandUpdate(centroid.position)
    }
    // near the top or the bottom edge, the view scrolls on and the rectangle with it
    Timer {
        interval: 30; repeat: true
        running: list.band !== null
        onTriggered: {
            const p = list.mapFromItem(null, bandDrag.centroid.scenePosition)
            const step = p.y < 40 ? -Math.min(40, 40 - p.y) : p.y > list.height - 40 ? Math.min(40, p.y - list.height + 40) : 0
            if (!step) return
            const top = list.originY, bottom = list.originY + Math.max(0, list.contentHeight - list.height)
            list.contentY = Math.max(top, Math.min(bottom, list.contentY + step))
            list.bandUpdate(list.contentItem.mapFromItem(null, bandDrag.centroid.scenePosition))
        }
    }
    Rectangle {
        visible: list.band !== null
        x: list.band ? Math.min(list.band.x0, list.band.x1) : 0
        y: list.band ? Math.min(list.band.y0, list.band.y1) : 0
        width: list.band ? Math.abs(list.band.x1 - list.band.x0) : 0
        height: list.band ? Math.abs(list.band.y1 - list.band.y0) : 0
        z: 10
        radius: 3
        color: Qt.alpha(list.c.action, 0.12)
        border.width: 1; border.color: list.c.action
    }
    PinchHandler {
        target: null
        onActiveChanged: if (!active && Math.abs(activeScale - 1) > 0.2) win.zoomBy(activeScale > 1 ? 1 : -1)
    }

    delegate: Loader {
        id: rowLoader
        required property var modelData
        required property int index
        width: list.width
        height: modelData.kind === "head" ? (index === 0 ? 40 : 54) : modelData.h
        sourceComponent: modelData.kind === "head" ? headRow : photoRow

        Component {
            id: headRow
            Item {
                id: headItem
                readonly property var row: rowLoader.modelData
                HoverHandler { id: headHover }
                // every photo of the day (or month) already chosen: the button takes them out again
                readonly property bool allChosen: {
                    const ids = list.groupIds(row.key)
                    return ids.length > 0 && ids.every(id => win.chosen.indexOf(id) >= 0)
                }
                RowLayout {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.rightMargin: list.railed ? rail.width + 8 : 0     // clear of the dates on the right
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                    spacing: 10
                    Rectangle { implicitWidth: 3; implicitHeight: 18; radius: 1.5; color: list.c.famMedia }
                    Text {
                        text: headItem.row.title
                        font.family: "Schibsted Grotesk"; font.pixelSize: 17; font.weight: Font.Bold
                        font.letterSpacing: -0.2
                        color: list.c.text
                        Accessible.role: Accessible.Heading
                    }
                    // how many, on a chip of the media family
                    Rectangle {
                        visible: headItem.row.sub !== ""
                        implicitWidth: subText.implicitWidth + 14; implicitHeight: 20; radius: 10
                        color: Qt.alpha(list.c.famMedia, theme.dark ? 0.22 : 0.10)
                        Text {
                            id: subText
                            anchors.centerIn: parent
                            text: app.plural("count_items", Number(headItem.row.sub))
                            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                            color: theme.dark ? Qt.lighter(list.c.famMedia, 1.9) : list.c.famMedia
                        }
                    }
                    Item { Layout.fillWidth: true }
                    OButton {
                        visible: headHover.hovered || win.chosen.length > 0
                        kind: "quiet"; height_: 28; text: headItem.allChosen ? app.t.choose_none : app.t.choose_all
                        onClicked: {
                            const ids = list.groupIds(headItem.row.key)
                            if (headItem.allChosen) { win.chosen = win.chosen.filter(id => ids.indexOf(id) < 0); return }
                            const next = win.chosen.slice()
                            for (const id of ids) if (next.indexOf(id) < 0) next.push(id)
                            win.chosen = next
                        }
                    }
                }
            }
        }

        Component {
            id: photoRow
            Row {
                spacing: 4
                Repeater {
                    model: rowLoader.modelData.items
                    Item {
                        id: tile
                        required property var modelData
                        readonly property bool chosen: win.chosen.indexOf(modelData.fileid) >= 0
                        width: modelData.w
                        height: rowLoader.height
                        Accessible.role: Accessible.Graphic
                        Accessible.name: app.t.photo + (modelData.video ? ", " + app.t.video : "")

                        Rectangle {
                            anchors.fill: parent
                            radius: 4
                            color: Qt.tint(list.c.line, Qt.alpha(list.c.famMedia, 0.08))
                            clip: true
                            Thumb {
                                id: img
                                // a rotation on its way: the picture turned in its tile (whose sides are swapped)
                                readonly property bool sideways: (tile.modelData.turn || 0) % 180 !== 0
                                property real m: tile.chosen ? 6 : 0
                                anchors.centerIn: parent
                                width: (sideways ? parent.height : parent.width) - 2 * m
                                height: (sideways ? parent.width : parent.height) - 2 * m
                                rotation: tile.modelData.turn || 0
                                address: "t/" + (rowLoader.height > 200 || tile.width > 300 ? 512 : 256) + "/"
                                        + tile.modelData.fileid + "/" + tile.modelData.etag
                                sourceSize: Qt.size(rowLoader.height > 200 || tile.width > 300 ? 512 : 256, rowLoader.height > 200 || tile.width > 300 ? 512 : 256)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                cache: true
                                opacity: status === Image.Ready ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 140 } }
                                Behavior on m { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                            }
                            Rectangle {
                                anchors.fill: parent
                                color: "transparent"
                                radius: 4
                                border.width: tile.chosen ? 3 : 0
                                border.color: list.c.action
                            }
                            Rectangle {
                                anchors.fill: parent
                                color: "transparent"
                                radius: 4
                                visible: list.activeFocus && list.cursor === tile.modelData.i
                                border.width: 3; border.color: list.c.saffron
                            }
                            Rectangle {
                                anchors.fill: parent
                                color: "transparent"
                                radius: 4
                                visible: !tile.chosen && photoMenu.opened && photoMenu.ids.length === 1
                                         && photoMenu.ids[0] === tile.modelData.fileid
                                border.width: 2; border.color: list.c.action
                            }
                            Rectangle {
                                anchors.fill: parent
                                visible: hover.hovered && !tile.chosen
                                color: Qt.rgba(0, 0, 0, 0.12)
                            }
                        }
                        // a video: its length, bottom right
                        Rectangle {
                            visible: tile.modelData.video
                            anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 6
                            height: 20; radius: 5; width: vidRow.implicitWidth + 10
                            color: Qt.rgba(0, 0, 0, 0.55)
                            Row {
                                id: vidRow
                                anchors.centerIn: parent
                                spacing: 3
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "play"; size: 11; color: "white" }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: tile.modelData.duration ? app.duration(tile.modelData.duration) : ""
                                    font.family: "JetBrains Mono"; font.pixelSize: 11; color: "white"
                                }
                            }
                        }
                        Icon {
                            visible: tile.modelData.fav
                            anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 7
                            name: "star"; size: 16; color: "white"
                            layer.enabled: true
                        }
                        // on its way to the cloud
                        Rectangle {
                            visible: tile.modelData.pending
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 8
                            width: 8; height: 8; radius: 4
                            color: list.c.saffron
                            border.width: 1; border.color: "white"
                        }
                        // the round mark that chooses (on hover, or always while choosing)
                        Rectangle {
                            id: mark
                            visible: hover.hovered || win.chosen.length > 0
                            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 7
                            width: 22; height: 22; radius: 11
                            color: tile.chosen ? list.c.action : Qt.rgba(0, 0, 0, 0.25)
                            border.width: 1.5; border.color: "white"
                            Icon { anchors.centerIn: parent; visible: tile.chosen; name: "check"; size: 13; color: list.c.actionText }
                        }

                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        // one handler for the photo and its mark: a tap on the mark only chooses (it never opens)
                        TapHandler {
                            onTapped: eventPoint => {
                                const p = mark.mapFromItem(tile, eventPoint.position)
                                const onMark = mark.visible && p.x >= -4 && p.y >= -4 && p.x <= mark.width + 4 && p.y <= mark.height + 4
                                list.cursor = tile.modelData.i
                                list.forceActiveFocus()
                                win.clickPhoto(tile.modelData.fileid, tile.modelData.i, onMark)
                            }
                        }
                        // the menu acts on the choice when the photo is in it, else on this photo alone: the
                        // choice itself does not change
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: photoMenu.openFor(tile.chosen ? win.chosen.slice() : [tile.modelData.fileid], tile)
                        }
                        // dragged: to an album of the sidebar, into a note, onto a task
                        Item {
                            id: dragProxy
                            Drag.active: dragHandler.active
                            Drag.dragType: Drag.Automatic
                            Drag.supportedActions: Qt.CopyAction
                            Drag.mimeData: dragHandler.active ? photos.dragData(tile.chosen ? win.chosen : [tile.modelData.fileid]) : ({})
                            Drag.imageSource: img.source
                            Drag.hotSpot: Qt.point(24, 24)
                        }
                        DragHandler {
                            id: dragHandler
                            target: null
                            dragThreshold: 12
                            // while choosing, a photo not chosen starts the rectangle instead
                            enabled: win.chosen.length === 0 || tile.chosen
                        }
                    }
                }
            }
        }
    }

    OMenu {
        id: photoMenu
        property var ids: []
        readonly property bool one: ids.length === 1
        readonly property string kind: photos.view.split(":")[0]
        function openFor(list_, item) {
            ids = list_
            const p = item.mapToItem(list, item.width / 2, item.height / 2)
            x = Math.min(p.x, list.width - width - 8); y = Math.min(p.y, list.height - 300)
            open()
        }
        OMenuItem { visible: photoMenu.one; text: app.t.open; iconName: "image"; onTriggered: viewer.open(photoMenu.ids[0]) }
        OMenuItem { text: app.t.favorite; iconName: "star"; onTriggered: photos.toggleFavorite(photoMenu.ids) }
        OMenuItem { id: albumItem; text: app.t.add_to_album; iconName: "album"; onTriggered: list.albumWanted(photoMenu.ids, albumItem) }
        OMenuItem { visible: photoMenu.one; text: app.t.edit; iconName: "edit"; onTriggered: list.editWanted(photoMenu.ids[0]) }
        OMenuItem { visible: photoMenu.one; text: app.t.copy_image; iconName: "copy"; onTriggered: photos.copyImage(photoMenu.ids[0]) }
        OMenuItem { text: app.t.share_with; iconName: "people"; onTriggered: shareAlbum.ask(photoMenu.ids) }
        OMenuItem { text: app.t.share_link; iconName: "link"; onTriggered: photos.shareLink(photoMenu.ids) }
        OMenuItem { text: app.t.download; iconName: "download"; onTriggered: photos.download(photoMenu.ids) }
        OMenuItem { text: app.t.rotate_left; iconName: "rotate"; onTriggered: photos.rotate(photoMenu.ids, 270) }
        OMenuItem { text: app.t.change_date; iconName: "calendar"; onTriggered: dateDialog.openFor(photoMenu.ids, "") }
        OMenuItem {
            visible: photoMenu.one && ((photoMenu.kind === "albums" && photos.heading.own === true) || photoMenu.kind === "recognize")
            text: app.t.set_cover; iconName: "image"; onTriggered: photos.setCover(photoMenu.ids[0])
        }
        OMenuItem {
            text: photos.view === "archive" ? app.t.unarchive_action : app.t.archive_action; iconName: "archive"
            onTriggered: { photos.archive(photoMenu.ids, photos.view !== "archive"); win.clearChoice() }
        }
        OMenuItem {
            visible: photoMenu.kind === "albums" && photos.heading.own === true
            text: app.t.remove_from_album; iconName: "close"
            onTriggered: { photos.removeFromAlbum(photos.heading.ref, photoMenu.ids); win.clearChoice() }
        }
        OMenuItem {
            visible: photoMenu.kind === "recognize"
            text: app.t.not_this_person; iconName: "close"
            onTriggered: { photos.notThisPerson(photos.heading.ref, photoMenu.ids); win.clearChoice() }
        }
        OMenuItem { text: app.t.delete_action; iconName: "trash"; danger: true; onTriggered: win.remove(photoMenu.ids) }
    }
}
