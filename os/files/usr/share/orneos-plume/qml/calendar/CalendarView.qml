// Agenda module: the capture line, the calendars and the month on the side, the account and settings at its
// foot; on the right the hero (the ring of the day, the title, what comes next, the views), then the day,
// week, month or schedule on a card.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/colors.js" as Colors
import "../components/dates.js" as D

Rectangle {
    id: view
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    property date anchor: new Date()
    property string mode: plume.prefs.cal_view || "week"     // the view it opens on: not a binding once changed
    property string sideTab: "calendars"
    property alias editor: editor
    property alias invitationKind: invitations.kind
    color: c.bg

    readonly property date rangeStart: mode === "week" ? D.startOfWeek(anchor)
                                     : mode === "month" ? D.startOfWeek(D.startOfMonth(anchor))
                                     : D.startOfDay(anchor)
    readonly property int rangeDays: mode === "week" ? 7 : mode === "month" ? 42 : mode === "agenda" ? agendaDays : 1
    property int agendaDays: 60                 // the schedule grows as one scrolls down it
    onAnchorChanged: agendaDays = 60
    onModeChanged: agendaDays = 60
    // the tasks of Tâches due in the range, beside the events (Réglages); read again when the window comes back
    property int tasksRevision: 0
    Connections { target: Qt.application; function onStateChanged() { if (Qt.application.state === Qt.ApplicationActive) view.tasksRevision++ } }
    readonly property var items: {
        agenda.revision; tasksRevision
        const events = agenda.occurrences(D.iso(rangeStart), rangeDays)
        return plume.prefs.cal_tasks === false ? events : events.concat(agenda.tasks(D.iso(rangeStart), rangeDays))
    }
    // the search: events of a year back to two years ahead, the next ones first
    property string query: ""
    readonly property var found: { agenda.revision; return query.trim().length >= 2 ? agenda.search(query) : [] }

    function title() {
        if (mode === "day")
            return D.capitalize(loc.toString(anchor, "dddd d MMMM yyyy"))
        if (mode === "week") {
            const s = rangeStart, e = D.addDays(rangeStart, 6)
            const head = s.getMonth() === e.getMonth()
                ? D.capitalize(loc.standaloneMonthName(s.getMonth())) + " " + s.getFullYear()
                : D.capitalize(loc.monthName(s.getMonth(), Locale.ShortFormat)) + " – " + loc.monthName(e.getMonth(), Locale.ShortFormat) + " " + e.getFullYear()
            return head
        }
        return D.capitalize(loc.standaloneMonthName(anchor.getMonth())) + " " + anchor.getFullYear()
    }
    function step(n) {
        anchor = mode === "month" ? D.addMonths(anchor, n) : D.addDays(anchor, n * (mode === "week" ? 7 : mode === "agenda" ? 30 : 1))
    }
    // Day view of today: the ring of the day (docs/ROADMAP.md › Anneau), 8 h to 20 h, events in the action colour,
    // the elapsed part in saffron, a dot at the current time; beside it, what comes next.
    property date now: new Date()
    Timer { interval: 30000; running: view.mode === "day"; repeat: true; onTriggered: view.now = new Date() }
    readonly property bool dayIsToday: mode === "day" && D.iso(anchor) === D.iso(now)
    readonly property var timedToday: dayIsToday ? items.filter(i => !i.allDay) : []
    function dayFrac(ts) {
        const d = new Date(ts * 1000)
        if (D.iso(d) !== D.iso(now)) return d < now ? 0 : 1
        return Math.max(0, Math.min(1, (d.getHours() + d.getMinutes() / 60 - 8) / 12))
    }
    function dayLine() {
        const t = now.getTime() / 1000, hm = ts => loc.toString(new Date(ts * 1000), "HH:mm")
        const cur = timedToday.find(i => i.startTs <= t && i.endTs > t)
        if (cur) return plume.t.day_now.replace("%1", hm(cur.endTs))
        const next = timedToday.find(i => i.startTs > t)
        if (!next) return plume.t.day_free
        const title = next.title || plume.t.untitled
        return next.startTs - t < 3600 ? plume.t.day_next_soon.replace("%1", title).replace("%2", Math.max(1, Math.round((next.startTs - t) / 60)))
                                      : plume.t.day_next.replace("%1", title).replace("%2", hm(next.startTs))
    }
    // the menu of a calendar: rename and colour (mine, or followed), remove it
    property var menuCalendar: ({})
    function calendarMenu(cal, item) {
        menuCalendar = cal
        const p = item.mapToItem(view, 0, item.height + 2)
        calMenu.x = Math.min(p.x, view.width - calMenu.implicitWidth - 8)
        calMenu.y = p.y
        calMenu.open()
    }
    function removeCalendar(cal) {
        const n = agenda.eventCount(cal.id)
        const own = !cal.shared && !cal.followed
        choice.ask(own ? plume.t.cal_delete_title.replace("%1", cal.name) : plume.t.cal_remove_title.replace("%1", cal.name),
                   own ? plume.t.cal_delete_text.replace("%1", n) : cal.followed ? plume.t.cal_unfollow_text : plume.t.cal_unshare_text, [
            { id: "cancel", text: plume.t.cancel },
            { id: "delete", text: own ? plume.t.delete : plume.t.cal_remove, kind: "danger" }
        ], () => agenda.deleteCalendar(cal.id))
    }
    function newEvent(when, allDay, until) { editor.openNew(when, allDay, until) }
    // a drag in the grid: shown there at once, the cloud follows; a recurring one first asks which occurrences
    function moveEvent(occ, from, to) {
        const allDay = !!occ.allDay
        const stamp = d => allDay ? D.iso(d) : D.isoLocal(d)
        const fields = { eventId: occ.eventId, calendarId: occ.calendarId, rid: occ.rid || "", allDay: allDay,
                         start: stamp(from), end: stamp(to) }
        const title = occ.title || plume.t.untitled
        const when = allDay || !D.sameDay(from, new Date(occ.start))
            ? D.capitalize(loc.toString(from, "ddd d MMM")) + (allDay ? "" : " " + D.hm(from)) : D.hm(from)
        const back = Object.assign({}, fields, { start: stamp(new Date(occ.start)), end: stamp(new Date(occ.end)) })
        const go = which => {
            fields.scope = which
            agenda.save(fields)
            if (which === "all" || which === "future")
                calToast.show(plume.t.moved_event.replace("%1", title).replace("%2", when))
            else
                calToast.show(plume.t.moved_event.replace("%1", title).replace("%2", when), plume.t.undo, () => {
                    // the occurrence moved: it is now known by its own id, the same rid
                    back.scope = which
                    agenda.save(back)
                }, 6)
        }
        if (occ.recurring && occ.rid)
            scope.ask(plume.t.scope_edit, title, go)
        else
            go("all")
    }
    function openCard(occ, item) {
        if (occ.task)
            agenda.openTask(occ.uid)
        else
            card.show(occ, item || view)
    }
    function editEvent(info) { editor.openEdit(info) }
    // Deleted at once, « Annuler » for a few seconds (the cloud only hears of it after): a recurring one first
    // asks which occurrences
    function deleteEvent(info) {
        const title = info.title || plume.t.untitled
        const go = scope => {
            const token = agenda.removeLater(info.eventId, info.rid || "", scope, info.start || "")
            calToast.show(plume.t["deleted_" + scope].replace("%1", title), plume.t.undo, () => agenda.undoRemove(token), 6)
        }
        if (info.recurring && info.rid)
            scope.ask(plume.t.scope_delete, title, go)
        else
            go("all")
    }

    // the letters of the views: not while a card or the editor has the keyboard
    readonly property bool keys: plume.module === "calendar" && !card.opened && !editor.opened && !scope.opened
    Shortcut { enabled: view.keys; sequence: "Ctrl+N"; onActivated: view.newEvent(null, false) }
    Shortcut { enabled: view.keys; sequence: "T"; onActivated: view.anchor = new Date() }
    Shortcut { enabled: view.keys; sequences: ["J", "Right"]; onActivated: view.step(1) }
    Shortcut { enabled: view.keys; sequences: ["K", "Left"]; onActivated: view.step(-1) }
    Shortcut { enabled: view.keys; sequence: "D"; onActivated: view.mode = "day" }
    Shortcut { enabled: view.keys; sequence: "W"; onActivated: view.mode = "week" }
    Shortcut { enabled: view.keys; sequence: "M"; onActivated: view.mode = "month" }
    Shortcut { enabled: view.keys; sequence: "A"; onActivated: view.mode = "agenda" }
    Shortcut { enabled: view.keys; sequences: [StandardKey.Find, "/"]; onActivated: { searchField.forceActiveFocus(); searchField.selectAll() } }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---- side: new event, the month, the calendars ----
        Rectangle {
            Layout.preferredWidth: 256
            Layout.fillHeight: true
            color: view.c.chrome
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: view.c.hairline }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12; anchors.topMargin: 14
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 4; Layout.bottomMargin: -2
                    spacing: 8
                    Text {
                        text: plume.t.calendar
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                        color: view.c.famOrganize
                    }
                    Text {
                        Layout.fillWidth: true
                        text: D.capitalize(view.loc.standaloneMonthName(view.now.getMonth())) + " " + view.now.getFullYear()
                        font.family: "JetBrains Mono"; font.pixelSize: 11
                        color: view.c.muted
                        elide: Text.ElideRight
                    }
                }
                // the new-item line: opens the event editor
                Capture {
                    Layout.fillWidth: true
                    enabled: agenda.defaultCalendar > 0
                    tint: view.c.famOrganize
                    text: plume.t.new_event_hint
                    shortcut: "Ctrl N"
                    onClicked: view.newEvent(null, false)
                }

                // Calendars / Invitations
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    spacing: 4
                    Repeater {
                        model: [["calendars", "calendar", plume.t.tab_calendars], ["invitations", "inbox", plume.t.tab_invitations]]
                        AbstractButton {
                            id: tab
                            required property var modelData
                            readonly property bool active: view.sideTab === modelData[0]
                            Layout.fillWidth: true
                            implicitHeight: 34
                            hoverEnabled: true
                            Accessible.role: Accessible.PageTab
                            Accessible.name: modelData[2]
                            onClicked: view.sideTab = modelData[0]
                            background: Rectangle {
                                radius: 7
                                color: tab.active ? view.c.card : tab.hovered ? view.c.hover : "transparent"
                                Rectangle {
                                    visible: tab.active
                                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 14; rightMargin: 14 }
                                    height: 2; radius: 1; color: view.c.famOrganize
                                }
                            }
                            contentItem: Item {
                                Row {
                                    spacing: 7
                                    anchors.centerIn: parent
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: tab.modelData[2]
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: tab.active ? Font.DemiBold : Font.Medium
                                        color: view.c.text
                                    }
                                    Rectangle {
                                        visible: tab.modelData[0] === "invitations" && agenda.pending > 0
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: Math.max(18, badge.implicitWidth + 8); height: 18; radius: 9
                                        color: view.c.saffron
                                        Text { id: badge; anchors.centerIn: parent; text: agenda.pending; font.family: "JetBrains Mono"; font.pixelSize: 11; color: view.c.saffronText }
                                    }
                                }
                            }
                        }
                    }
                }

                Flickable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentHeight: view.sideTab === "calendars" ? side.implicitHeight : invitations.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}

                    InvitationsPanel {
                        id: invitations
                        visible: view.sideTab === "invitations"
                        width: parent.width
                        onOpenRequested: invite => {
                            view.anchor = new Date(invite.start)
                            if (view.mode === "agenda" || view.mode === "month")
                                view.mode = "week"
                            Qt.callLater(() => view.openCard({ eventId: invite.eventId, rid: invite.rid }))
                        }
                    }

                    ColumnLayout {
                        id: side
                        visible: view.sideTab === "calendars"
                        width: parent.width
                        spacing: 4
                        Repeater {
                            model: [
                                { label: plume.t.my_calendars, shared: false },
                                { label: plume.t.shared_calendars, shared: true }
                            ]
                            ColumnLayout {
                                id: group
                                required property var modelData
                                readonly property var list: agenda.calendars.filter(c => c.shared === modelData.shared)
                                visible: list.length > 0
                                Layout.fillWidth: true
                                Layout.topMargin: modelData.shared ? 14 : 4
                                spacing: 0
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 4; Layout.bottomMargin: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: group.modelData.label
                                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                                        font.capitalization: Font.AllUppercase
                                        color: view.c.muted
                                    }
                                    // new calendar, or one followed from a link
                                    OButton {
                                        id: addCalendar
                                        visible: !group.modelData.shared
                                        kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 24; implicitWidth: 24
                                        tip: plume.t.cal_add
                                        onClicked: addMenu.open()
                                        OMenu {
                                            id: addMenu
                                            y: addCalendar.height + 4
                                            OMenuItem { text: plume.t.cal_new; iconName: "calendar"; onTriggered: calDialog.openNew() }
                                            OMenuItem { text: plume.t.cal_subscribe_menu; iconName: "link"; onTriggered: calDialog.openSubscribe("") }
                                            OMenuItem { text: plume.t.cal_share_cloud; iconName: "people"; onTriggered: plume.openCloud("/apps/calendar/") }
                                        }
                                    }
                                }
                                Repeater {
                                    model: group.list
                                    AbstractButton {
                                        id: cal
                                        required property var modelData
                                        Layout.fillWidth: true
                                        implicitHeight: 34
                                        hoverEnabled: true
                                        Accessible.name: modelData.name
                                        Accessible.role: Accessible.CheckBox
                                        Accessible.checked: modelData.enabled
                                        onClicked: agenda.setEnabled(modelData.id, !modelData.enabled)
                                        TapHandler {
                                            acceptedButtons: Qt.RightButton
                                            onTapped: view.calendarMenu(cal.modelData, cal)
                                        }
                                        background: Rectangle { radius: 6; color: cal.hovered ? view.c.hover : "transparent" }
                                        contentItem: RowLayout {
                                            spacing: 10
                                            Rectangle {
                                                Layout.leftMargin: 6
                                                implicitWidth: 16; implicitHeight: 16; radius: 4
                                                color: cal.modelData.enabled ? Colors.display(cal.modelData.color, theme.dark) : "transparent"
                                                border.width: 1.5; border.color: Colors.display(cal.modelData.color, theme.dark)
                                                Icon { anchors.centerIn: parent; visible: cal.modelData.enabled; name: "check"; size: 12; color: theme.dark ? "#0A1424" : "white" }
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: cal.modelData.name
                                                elide: Text.ElideRight
                                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                                color: view.c.text
                                            }
                                            Text {
                                                visible: cal.modelData.ownerName !== "" && !cal.hovered
                                                Layout.rightMargin: 4
                                                Layout.maximumWidth: 80
                                                text: cal.modelData.ownerName
                                                elide: Text.ElideRight
                                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                                color: view.c.muted
                                            }
                                            Icon {
                                                visible: cal.modelData.followed && !cal.hovered
                                                Layout.rightMargin: 6
                                                name: "link"; size: 13; color: view.c.faint
                                            }
                                            OButton {
                                                visible: cal.hovered || cal.visualFocus
                                                kind: "quiet"; iconName: "more"; iconSize: 14; height_: 24; implicitWidth: 24
                                                tip: plume.t.cal_options
                                                onClicked: view.calendarMenu(cal.modelData, this)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.hairline }
                MiniMonth {
                    Layout.fillWidth: true
                    selected: view.anchor
                    weekBand: view.mode === "week"
                    onPicked: day => view.anchor = day
                }
                AccountBar {
                    Layout.fillWidth: true
                    Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
                    name: plume.profile.name || ""
                    email: plume.profile.email || ""
                    initials: plume.profile.initials || ""
                    onSettingsRequested: plume.openSettings("")
                    OMenuItem { text: plume.t.account_manage; iconName: "user"; onTriggered: plume.openAccount() }
                    OMenuItem { visible: !signin.canSignOut; height: visible ? implicitHeight : 0; text: plume.t.reconnect; iconName: "refresh"; onTriggered: plume.openConnect() }
                    OMenuItem { visible: signin.canSignOut; height: visible ? implicitHeight : 0; text: plume.t.sign_out; iconName: "lock"; onTriggered: plume.openSettings("") }
                }
            }
        }

        // ---- main: toolbar, then the current view ----
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            Hero {
                id: hero
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.topMargin: 14; Layout.bottomMargin: 10
                tint: view.c.famOrganize
                titleSize: 26
                kicker: view.dayIsToday ? plume.t.today
                      : view.mode === "week" ? plume.t.week_short.replace("%1", D.weekNumber(view.rangeStart)) : ""
                title: view.title()
                meta: view.dayIsToday ? view.dayLine() : ""
                // the only state of the sync ever shown: offline, with when the cloud last answered
                offline: !plume.connection.dav.online
                offlineText: plume.connection.dav.online ? "" : plume.offlineLine("dav")
                // Day view of today: the ring of the day (docs/ROADMAP.md › Anneau)
                leading: Ring {
                    visible: view.dayIsToday
                    width: visible ? 60 : 0; height: 60
                    lineWidth: 6
                    trackColor: view.c.accentLine
                    markerColor: view.c.saffron
                    markerOutline: view.c.card
                    marker: view.dayFrac(view.now.getTime() / 1000)
                    segments: [{ from: 0, to: view.dayFrac(view.now.getTime() / 1000), color: view.c.saffron }]
                        .concat(view.timedToday.map(i => ({ from: view.dayFrac(i.startTs) + 0.012, to: view.dayFrac(i.endTs) - 0.012, color: view.c.famOrganize })))
                    Accessible.role: Accessible.StaticText
                    Accessible.name: view.dayLine()
                }
                OTextField {
                    id: searchField
                    // a magnifier until it is used (the title of the day keeps its room), then a field
                    readonly property bool open_: activeFocus || text !== ""
                    Layout.preferredWidth: open_ ? 240 : 38
                    Behavior on Layout.preferredWidth { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                    iconName: "search"
                    placeholderText: open_ ? plume.t.cal_search_ph : ""
                    Accessible.name: plume.t.cal_search_ph
                    ToolTip.visible: !open_ && hovered
                    ToolTip.delay: 450
                    ToolTip.text: plume.t.cal_search_ph + " (Ctrl+F)"
                    onTextChanged: searchTimer.restart()
                    onCleared: view.query = ""
                    Keys.onEscapePressed: { text = ""; view.query = ""; focus = false }
                    Timer { id: searchTimer; interval: 220; onTriggered: view.query = searchField.text }
                }
                OButton { kind: "quiet"; text: plume.t.today; onClicked: { searchField.clear(); view.anchor = new Date() } }
                OButton { kind: "quiet"; iconName: "chevronLeft"; Accessible.name: plume.t.previous; implicitWidth: 34; onClicked: view.step(-1) }
                OButton { kind: "quiet"; iconName: "chevronRight"; Accessible.name: plume.t.next; implicitWidth: 34; onClicked: view.step(1) }
                Rectangle {
                    Layout.leftMargin: 6
                    implicitWidth: segments.implicitWidth + 6
                    implicitHeight: 34
                    radius: 9
                    color: view.c.bg
                    border.width: 1; border.color: view.c.line
                    Row {
                        id: segments
                        anchors.centerIn: parent
                        spacing: 0
                        Repeater {
                            model: [["day", plume.t.view_day], ["week", plume.t.view_week], ["month", plume.t.view_month], ["agenda", plume.t.view_agenda]]
                            AbstractButton {
                                id: seg
                                required property var modelData
                                readonly property bool active: view.mode === modelData[0]
                                height: 28
                                width: segLabel.implicitWidth + 22
                                hoverEnabled: true
                                onClicked: view.mode = modelData[0]
                                Accessible.role: Accessible.RadioButton
                                Accessible.checked: active
                                background: Rectangle {
                                    radius: 7
                                    color: seg.active ? view.c.card : "transparent"
                                    border.width: seg.active && theme.dark ? 1 : 0; border.color: view.c.line
                                }
                                contentItem: Text {
                                    id: segLabel
                                    text: seg.modelData[1]
                                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    font.weight: seg.active ? Font.DemiBold : Font.Medium
                                    color: seg.active || seg.hovered ? view.c.text : view.c.muted
                                }
                            }
                        }
                    }
                }
            }

            Surface {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 16
            StackLayout {
                anchors.fill: parent
                anchors.margins: 1
                clip: true
                currentIndex: view.query.trim().length >= 2 ? 3 : view.mode === "month" ? 1 : view.mode === "agenda" ? 2 : 0
                TimeGrid {
                    start: view.rangeStart
                    days: view.mode === "day" ? 1 : 7
                    items: view.mode === "day" || view.mode === "week" ? view.items : []
                    onEventClicked: (occ, item) => view.openCard(occ, item)
                    onSlotClicked: (when, allDay) => view.newEvent(when, allDay)
                    onRangeSelected: (from, to) => view.newEvent(from, false, to)
                    onMoveRequested: (occ, from, to) => view.moveEvent(occ, from, to)
                    onDayClicked: day => { view.anchor = day; view.mode = "day" }
                }
                MonthView {
                    shown: view.anchor
                    items: view.mode === "month" ? view.items : []
                    onEventClicked: (occ, item) => view.openCard(occ, item)
                    onDayClicked: day => { view.anchor = day; view.mode = "day" }
                    onSlotClicked: (when, allDay) => view.newEvent(when, allDay)
                    onMoveRequested: (occ, days) => view.moveEvent(occ, D.addDays(new Date(occ.start), days), D.addDays(new Date(occ.end), days))
                }
                AgendaList {
                    start: view.rangeStart
                    items: view.mode === "agenda" ? view.items : []
                    onEventClicked: (occ, item) => view.openCard(occ, item)
                    onMoreWanted: if (view.agendaDays < 730) view.agendaDays += 60
                }
                AgendaList {
                    searching: true
                    start: new Date(2000, 0, 1)
                    items: view.found
                    emptyText: plume.t.cal_search_none.replace("%1", view.query.trim())
                    onEventClicked: (occ, item) => {
                        view.anchor = new Date(occ.start)
                        view.openCard(occ, item)
                    }
                }
            }
            }
        }
    }

    EventCard {
        id: card
        onEditRequested: info => view.editEvent(info)
        onDeleteRequested: info => view.deleteEvent(info)
        onDuplicateRequested: info => editor.openDuplicate(info)
    }
    EventEditor {
        id: editor
        onSaveRequested: (fields, askScope) => {
            if (!askScope) {
                agenda.save(fields)
                return
            }
            scope.ask(plume.t.scope_edit, fields.title, which => { fields.scope = which; agenda.save(fields) })
        }
    }
    ChoiceDialog { id: choice }
    ScopeDialog { id: scope }
    CalendarDialog { id: calDialog }
    OMenu {
        id: calMenu
        heading: view.menuCalendar.name || ""
        OMenuItem {
            visible: !view.menuCalendar.shared; height: visible ? implicitHeight : 0
            text: plume.t.cal_edit; iconName: "draft"
            onTriggered: calDialog.openEdit(view.menuCalendar)
        }
        OMenuItem {
            text: view.menuCalendar.enabled ? plume.t.cal_hide : plume.t.cal_show; iconName: "eye"
            onTriggered: agenda.setEnabled(view.menuCalendar.id, !view.menuCalendar.enabled)
        }
        OMenuItem {
            text: plume.t.cal_only; iconName: "check"
            onTriggered: {
                for (const c of agenda.calendars)
                    agenda.setEnabled(c.id, c.id === view.menuCalendar.id)
            }
        }
        OMenuItem {
            visible: !view.menuCalendar.readonly && agenda.calendars.filter(c => !c.readonly).length > 1; height: visible ? implicitHeight : 0
            text: plume.t.cal_make_default; iconName: "star"
            onTriggered: plume.setPref("cal_default", view.menuCalendar.id)
        }
        OMenuItem {
            visible: !view.menuCalendar.shared && !view.menuCalendar.followed; height: visible ? implicitHeight : 0
            text: plume.t.cal_share_cloud; iconName: "people"
            onTriggered: plume.openCloud("/apps/calendar/")
        }
        OMenuItem {
            visible: !(view.menuCalendar.personal && !view.menuCalendar.shared)
            height: visible ? implicitHeight : 0
            danger: true
            text: !view.menuCalendar.shared && !view.menuCalendar.followed ? plume.t.cal_delete : plume.t.cal_remove
            iconName: "trash"
            onTriggered: view.removeCalendar(view.menuCalendar)
        }
    }
    Toast { id: calToast }

    Connections {
        target: plume
        function onPlanRequested(address) {
            editor.openNew(null, false)
            editor.guests = [address.toLowerCase()]
        }
        function onCalendarRequested(what, value) {
            if (what === "invitations") {
                view.sideTab = "invitations"
                view.invitationKind = "new"
            } else if (what === "subscribe") {
                calDialog.openSubscribe(value)
            } else if (what === "date" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
                view.anchor = new Date(value + "T00:00")
            } else if (what === "event") {
                const [id, start] = value.split("|")
                view.anchor = new Date(start)
                if (view.mode === "agenda" || view.mode === "month")
                    view.mode = "week"
                Qt.callLater(() => view.openCard({ eventId: parseInt(id), rid: "" }))
            }
        }
        function onEventProposed(e) {
            editor.openNew(null, false)
            editor.fill(e)
        }
        function onImportRequested(path) {
            const n = agenda.importFile(path)
            plume.toast(plume.t.imported_events.replace("%1", n))
        }
    }
}
