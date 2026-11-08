// New or edited event: title, when, repeat, calendar, place, Meet, guests (and when those of the cloud are busy),
// reminder, notes.
// Enter saves from the title; a recurring event asks whether the change is for one or all. When it is (start,
// end, all day, repeat) sits together in one well; the dialog carries Agenda's saffron band.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/dates.js" as D
import "repeat.js" as R

ODialog {
    id: editor
    property var info: ({})
    property var guests: []
    property var optional: []          // guests whose presence is optional (ROLE=OPT-PARTICIPANT)
    property var knownNames: ({})      // names the event already had for its guests
    property var rule: R.empty()       // the repetition being edited (ical.repeat_info)
    property var ruleLoaded: R.empty() // as the event had it: unchanged, it is written back untouched
    property string preset: "none"
    property bool ruleKept: false      // a rule the editor cannot show: written back as it is unless changed
    property var alarms: []            // reminders, minutes before the start
    property int otherAlarms: 0        // reminders it does not show (by e-mail, at a fixed date): kept
    property string originalMeet: ""
    property string meet: ""
    property bool creatingMeet: false
    property int ornisRequest: -1
    property string ornisError
    // the guests' busy times that day (only times, never what), asked to the cloud after each change
    property string freeBusyKey
    property var freeBusy: []
    readonly property int slotFrom: allDaySwitch.checked ? 0 : D.minutes(D.withTime(startDate.value, startTime.value))
    readonly property int slotTo: allDaySwitch.checked || D.iso(endDate.value) !== D.iso(startDate.value) ? 1440
                                  : Math.max(slotFrom + 15, D.minutes(D.withTime(endDate.value, endTime.value)))
    readonly property int viewFrom: Math.max(0, Math.min(7 * 60, slotFrom - 60))
    readonly property int viewTo: Math.min(1440, Math.max(21 * 60, slotTo + 60))
    readonly property var busyNow: freeBusy.filter(p => p.busy.some(b => b[0] < slotTo && b[1] > slotFrom)).map(p => p.email)
    readonly property date startValue: allDaySwitch.checked ? startDate.value : D.withTime(startDate.value, startTime.value)
    readonly property bool endInvalid: allDaySwitch.checked ? D.iso(endDate.value) < D.iso(startDate.value)
                                       : D.withTime(endDate.value, endTime.value) < D.withTime(startDate.value, startTime.value)
    signal saveRequested(var fields, bool askScope)

    // ---- "Trouver un créneau": the first time from the chosen start when every guest of the cloud and I are free
    property string slotKey
    property int slotDay: 0
    property bool slotSearching: false
    property string slotNote
    function findSlot() {
        slotDay = 0
        slotNote = ""
        slotSearching = true
        askSlot()
    }
    function askSlot() {
        const day = D.addDays(D.startOfDay(startDate.value), slotDay)
        const me = plume.profile.email ? [plume.profile.email] : []
        slotKey = agenda.freeBusy(D.iso(day), guests.concat(me))
        if (!slotKey) { slotSearching = false; slotNote = plume.t.slot_none }
    }
    function slotFound(result) {
        const length = Math.max(15, slotTo - slotFrom)
        const day = D.addDays(D.startOfDay(startDate.value), slotDay)
        const busy = [].concat.apply([], result.people.filter(p => p.known).map(p => p.busy)).sort((a, b) => a[0] - b[0])
        const now = new Date()
        let from = slotDay === 0 ? slotFrom : (plume.prefs.cal_day_start || 8) * 60
        if (D.sameDay(day, now))
            from = Math.max(from, Math.ceil(D.minutes(now) / 15) * 15)
        from = Math.max(from, (plume.prefs.cal_day_start || 8) * 60)
        const last = 19 * 60
        let t = Math.ceil(from / 15) * 15
        for (const b of busy) {
            if (b[1] <= t) continue
            if (b[0] >= t + length) break
            t = Math.ceil(b[1] / 15) * 15
        }
        if (t + length <= last && (day.getDay() % 6 !== 0 || slotDay === 0)) {
            const start = new Date(day.getFullYear(), day.getMonth(), day.getDate(), Math.floor(t / 60), t % 60)
            const end = new Date(start.getTime() + length * 60000)
            startDate.value = start; startTime.value = D.hm(start)
            endDate.value = end; endTime.value = D.hm(end)
            slotSearching = false
            slotNote = slotDay === 0 ? "" : plume.t.slot_moved.replace("%1", D.capitalize(Qt.locale(plume.locale).toString(start, "dddd d MMMM")))
            return
        }
        if (++slotDay > 14) { slotSearching = false; slotNote = plume.t.slot_none; return }
        askSlot()
    }

    function askFreeBusy() {
        freeBusyKey = agenda.freeBusy(D.iso(startDate.value), guests)
        if (!freeBusyKey)
            freeBusy = []
    }
    function guestName(email) {
        if (knownNames[email]) return knownNames[email]
        const hit = people.suggest(email).find(h => h.email.toLowerCase() === email)
        return hit && hit.name ? hit.name : email
    }
    function setPreset(value) {
        if (value === preset) return
        preset = value
        if (value === "keep") return
        ruleKept = false
        rule = value === "none" ? R.empty() : R.fromPreset(value, startValue, rule)
    }
    function setRule(changes) {
        const r = Object.assign({}, rule, changes)
        ruleKept = false
        rule = r
        if (preset !== "custom") preset = R.presetOf(r, startValue)
    }
    onGuestsChanged: { slotNote = ""; freeBusyTimer.restart() }
    onOpened: { freeBusy = []; freeBusyTimer.restart() }
    Timer { id: freeBusyTimer; interval: 400; onTriggered: if (editor.opened) editor.askFreeBusy() }
    Connections {
        target: agenda
        function onFreeBusyReady(result) {
            if (result.key === editor.freeBusyKey) editor.freeBusy = result.people
            if (editor.slotSearching && result.key === editor.slotKey) editor.slotFound(result)
        }
    }

    width: Math.min(600, parent ? parent.width - 48 : 600)
    tint: theme.c.famOrganize

    // the calendar chosen in the settings while it is still there and writable, else the cloud's « Personnel »
    function newCalendar() {
        const chosen = plume.prefs.cal_default
        return agenda.calendars.some(c => c.id === chosen && !c.readonly) ? chosen : agenda.defaultCalendar
    }

    function openNew(when, allDay, until) {
        const start = when || D.withTime(new Date(), (new Date().getHours() + 1) + ":00")
        info = { eventId: 0, calendarId: newCalendar(), rid: "", recurring: false }
        if (ornisRequest >= 0)
            ornis.cancel(ornisRequest)
        ornisRequest = -1
        ornisError = ""
        describeField.text = ""
        title.text = ""
        allDaySwitch.checked = !!allDay
        startDate.value = start
        startTime.value = D.hm(start)
        const end = until && until > start ? until : new Date(start.getTime() + (plume.prefs.cal_duration || 60) * 60000)
        endDate.value = allDay ? start : end
        endTime.value = D.hm(end)
        rule = R.empty()
        ruleLoaded = rule
        ruleKept = false
        preset = "none"
        calendarBox.select(newCalendar())
        location.text = ""
        guests = []
        optional = []
        knownNames = ({})
        meet = ""
        originalMeet = ""
        const pref = plume.prefs.cal_reminder
        alarms = pref === "" || pref === undefined || pref === null ? [] : [String(allDay ? R.convert(pref, true) : pref)]
        otherAlarms = 0
        slotNote = ""
        slotSearching = false
        notes.text = ""
        open()
        title.forceActiveFocus()
    }

    // an event described in plain words (or found in a message) by Ornis
    function fill(e) {
        if (!e || !e.start)
            return
        if (e.title)
            title.text = e.title
        allDaySwitch.checked = !!e.allDay
        const s = e.allDay ? new Date(e.start.slice(0, 10) + "T00:00") : new Date(e.start)
        let end = e.end ? (e.allDay ? new Date(e.end.slice(0, 10) + "T00:00") : new Date(e.end)) : null
        if (!end || end < s)
            end = e.allDay ? s : new Date(s.getTime() + 3600000)
        startDate.value = s
        startTime.value = D.hm(s)
        endDate.value = end
        endTime.value = D.hm(end)
        if (e.location)
            location.text = e.location
        if (e.notes)
            notes.text = e.notes
    }
    function describe(text) {
        if (!text.trim())
            return
        ornisError = ""
        ornisRequest = ornis.ask("event", { text: text })
    }

    function openEdit(details) {
        info = details
        title.text = details.title
        allDaySwitch.checked = details.allDay
        const s = new Date(details.start), e = new Date(details.end)
        startDate.value = s
        startTime.value = D.hm(s)
        endDate.value = details.allDay ? D.addDays(e, -1) : e
        endTime.value = D.hm(e)
        rule = details.repeat || R.empty()
        ruleLoaded = rule
        ruleKept = !!details.repeat && details.repeat.editable === false
        preset = R.presetOf(rule, s)
        calendarBox.select(details.calendarId)
        location.text = details.location
        guests = details.attendees.map(a => a.email)
        optional = details.attendees.filter(a => a.optional).map(a => a.email)
        const names = {}
        for (const a of details.attendees) if (a.name) names[a.email] = a.name
        knownNames = names
        meet = details.meet || ""
        originalMeet = meet
        alarms = (details.alarms || []).slice()
        otherAlarms = details.otherAlarms || 0
        slotNote = ""
        slotSearching = false
        // the Meet line Plume wrote stays out of the notes: the Meet row shows it
        notes.text = meet ? details.description.split("\n").filter(l => l.trim() !== "Orneos Meet : " + meet).join("\n").trim()
                          : details.description
        open()
        title.forceActiveFocus()
    }

    // « Dupliquer » / « Copier dans mon agenda »: the same event, new, in my calendar; a copy of someone else's
    // event (read-only calendar, invitation) leaves its guests and its Meet behind
    function openDuplicate(details) {
        const theirs = !!details.readonly || !!details.canRespond
        openEdit(details)
        info = { eventId: 0, calendarId: newCalendar(), rid: "", recurring: false }
        calendarBox.select(newCalendar())
        if (details.rid && details.recurring) {     // one occurrence copied: not the whole series
            rule = R.empty(); ruleLoaded = rule; ruleKept = false; preset = "none"
        }
        if (theirs) {
            guests = []
            optional = []
            originalMeet = ""
        }
    }

    function fields() {
        let start, end
        if (allDaySwitch.checked) {
            start = D.iso(startDate.value)
            end = D.iso(D.addDays(endDate.value < startDate.value ? startDate.value : endDate.value, 1))
        } else {
            const s = D.withTime(startDate.value, startTime.value)
            let e = D.withTime(endDate.value, endTime.value)
            if (e < s)
                e = new Date(s.getTime() + 3600000)
            start = D.isoLocal(s)
            end = D.isoLocal(e)
        }
        let description = notes.text
        let place = location.text
        if (originalMeet && originalMeet !== meet) {
            // the link taken away goes from everywhere Plume or another app wrote it
            description = description.split("\n").filter(l => l.indexOf(originalMeet) === -1).join("\n").trim()
            if (place.indexOf(originalMeet) !== -1) place = place.replace(originalMeet, "").trim()
        }
        if (meet && description.indexOf(meet) === -1 && place.indexOf(meet) === -1)
            description = (description ? description + "\n\n" : "") + "Orneos Meet : " + meet
        const names = {}
        for (const g of guests) { const n = guestName(g); if (n !== g) names[g] = n }
        // a weekly or "2nd Tuesday" rule follows a start moved to another day
        let wanted = preset === "WEEKLY" || preset === "MONTHLY_NTH" ? R.fromPreset(preset, startValue, rule) : rule
        const plainRule = x => JSON.stringify([x.freq || "", x.interval || 1, (x.byday || []).slice().sort(), x.monthly || "day",
                                               x.monthly === "weekday" ? x.nth || 0 : 0, x.count || 0, x.until || ""])
        const unchanged = !!info.eventId && plainRule(wanted) === plainRule(ruleLoaded)
        const r = preset === "keep" || ruleKept || unchanged ? { keep: true } : Object.assign({}, wanted)
        return {
            eventId: info.eventId || 0, rid: info.rid || "", calendarId: calendarBox.currentValue,
            title: title.text, allDay: allDaySwitch.checked, start: start, end: end,
            repeat: r, location: place, description: description,
            attendees: guests, guestNames: names, optional: optional.filter(o => guests.indexOf(o) >= 0),
            alarms: alarms
        }
    }

    function save() {
        if (endInvalid) {
            endDate.forceActiveFocus()
            return
        }
        const f = fields()
        if (!f.title.trim())
            f.title = plume.t.untitled
        saveRequested(f, !!info.eventId && !!info.recurring && !!info.rid)
        close()
    }

    Connections {
        target: ornis
        function onAnswered(id, kind, value) {
            if (id !== editor.ornisRequest) return
            editor.ornisRequest = -1
            editor.fill(value)
            describeField.text = ""
            title.forceActiveFocus()
        }
        function onFailed(id, kind, text) {
            if (id !== editor.ornisRequest) return
            editor.ornisRequest = -1
            editor.ornisError = text
        }
    }

    Connections {
        target: agenda
        function onMeetCreated(url) {
            editor.creatingMeet = false
            if (url)
                editor.meet = url
        }
    }

    // new event: describe it, Ornis fills the form
    Rectangle {
        visible: !editor.info.eventId
        Layout.fillWidth: true
        implicitHeight: describeRow.implicitHeight + 12
        radius: 8
        color: theme.c.tint
        RowLayout {
            id: describeRow
            anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 12; anchors.rightMargin: 6
            spacing: 8
            Icon { name: "ornis"; size: 26; color: theme.c.accent }
            TextField {
                id: describeField
                visible: editor.ornisRequest < 0
                Layout.fillWidth: true
                background: null
                placeholderText: editor.ornisError || plume.t.ornis_event_ph
                placeholderTextColor: editor.ornisError ? theme.c.danger : theme.c.muted
                color: theme.c.text
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                selectByMouse: true
                onAccepted: editor.describe(text)
            }
            // Ornis at work: what was asked stays in sight, with the thinking dots
            ColumnLayout {
                visible: editor.ornisRequest >= 0
                Layout.fillWidth: true
                Layout.topMargin: 6; Layout.bottomMargin: 6
                spacing: 4
                Text {
                    Layout.fillWidth: true
                    text: "« " + describeField.text.trim() + " »"
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: theme.c.text
                }
                OrnisThinking { visible: editor.ornisRequest >= 0; text: plume.t.ornis_event_working }
            }
            OButton {
                visible: editor.ornisRequest >= 0
                kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "close"; iconSize: 12
                tip: plume.t.cancel
                onClicked: { ornis.cancel(editor.ornisRequest); editor.ornisRequest = -1; describeField.forceActiveFocus() }
            }
            OButton {
                visible: editor.ornisRequest < 0 && describeField.text.trim() !== ""
                kind: "quiet"; height_: 28; iconName: "arrow"; implicitWidth: 28
                tip: plume.t.ornis_event_go
                onClicked: editor.describe(describeField.text)
            }
        }
    }

    OTextField {
        id: title
        Layout.fillWidth: true
        plain: true
        placeholderText: plume.t.event_title_ph
        font.pixelSize: 24
        font.weight: Font.Bold
        onAccepted: editor.save()
    }

    component WhenLabel: Text {
        Layout.preferredWidth: 64
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
        color: theme.c.muted
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: 4
        implicitHeight: when.implicitHeight + 24
        radius: 10
        color: theme.c.bg
        border.width: 1; border.color: theme.c.hairline
    ColumnLayout {
        id: when
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
        spacing: 10
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        WhenLabel { text: plume.t.starts }
        DateField { id: startDate; Layout.fillWidth: true; onValueChanged: { if (endDate.value < value) endDate.value = value; freeBusyTimer.restart() } }
        TimeField {
            id: startTime
            visible: !allDaySwitch.checked
            onValueChanged: {
                // keep the end after the start when the start moves
                const s = D.withTime(startDate.value, value), e = D.withTime(endDate.value, endTime.value)
                if (e <= s) endTime.value = D.hm(new Date(s.getTime() + 3600000))
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        WhenLabel { text: plume.t.ends }
        DateField { id: endDate; Layout.fillWidth: true }
        TimeField { id: endTime; visible: !allDaySwitch.checked }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        OSwitch {
            id: allDaySwitch
            text: plume.t.all_day
            // the reminders follow: "10 minutes before" becomes "the day before at 9:00", and back
            onToggled: editor.alarms = editor.alarms.map(m => String(R.convert(m, checked)))
                                                  .filter((m, i, all) => all.indexOf(m) === i)
        }
        Item { Layout.fillWidth: true }
        OComboBox {
            id: repeat
            Layout.preferredWidth: 260
            Accessible.name: plume.t.repeat
            model: R.presets(editor.startValue, Qt.locale(plume.locale), plume.t, editor.preset === "keep")
            currentIndex: Math.max(0, model.findIndex(m => m.value === editor.preset))
            onActivated: index => editor.setPreset(model[index].value)
        }
    }
    Text {
        id: endWarning
        visible: editor.endInvalid
        Layout.fillWidth: true
        text: plume.t.end_before_start
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
        color: theme.c.danger
    }
    // custom: every N days/weeks/months/years, which days, which day of the month
    ColumnLayout {
        visible: editor.preset === "custom"
        Layout.fillWidth: true
        spacing: 8
        RowLayout {
            spacing: 8
            WhenLabel { text: plume.t.rep_every }
            Stepper {
                from: 1; to: 99
                value: editor.rule.interval || 1
                onEdited: v => editor.setRule({ interval: v })
            }
            OComboBox {
                Layout.preferredWidth: 150
                model: ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"].map(v => ({ text: plume.t["rep_unit_" + v], value: v }))
                currentIndex: Math.max(0, ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"].indexOf(editor.rule.freq))
                onActivated: index => {
                    const freq = model[index].value
                    editor.setRule({ freq: freq, byday: freq === "WEEKLY" ? [R.dayCode(editor.startValue)] : [],
                                     monthly: "day", nth: 0 })
                }
            }
        }
        Row {
            visible: editor.rule.freq === "WEEKLY"
            Layout.leftMargin: 72
            spacing: 6
            Repeater {
                model: R.DAYS
                AbstractButton {
                    id: dayToggle
                    required property string modelData
                    readonly property bool on: (editor.rule.byday || []).indexOf(modelData) >= 0
                    width: 34; height: 34
                    hoverEnabled: true
                    Accessible.role: Accessible.CheckBox
                    Accessible.checked: on
                    Accessible.name: Qt.locale(plume.locale).dayName(R.jsDay(modelData), Locale.LongFormat)
                    onClicked: {
                        let days = (editor.rule.byday || []).slice()
                        if (on) days = days.filter(d => d !== modelData)
                        else days.push(modelData)
                        if (!days.length) days = [R.dayCode(editor.startValue)]
                        editor.setRule({ byday: days })
                    }
                    background: Rectangle {
                        radius: 17
                        color: dayToggle.on ? theme.c.action : dayToggle.hovered ? theme.c.hover : "transparent"
                        border.width: dayToggle.on ? 0 : 1; border.color: theme.c.line
                    }
                    contentItem: Text {
                        text: Qt.locale(plume.locale).dayName(R.jsDay(dayToggle.modelData), Locale.NarrowFormat).toUpperCase()
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                        color: dayToggle.on ? theme.c.actionText : theme.c.text
                    }
                }
            }
        }
        OComboBox {
            visible: editor.rule.freq === "MONTHLY"
            Layout.leftMargin: 72
            Layout.preferredWidth: 260
            readonly property int nth: R.nthOf(editor.startValue) > 4 ? -1 : R.nthOf(editor.startValue)
            model: [{ text: plume.t.rep_month_day.replace("%1", editor.startValue.getDate()), value: "day" },
                    { text: plume.t.rep_month_nth.replace("%1", R.nthText(nth, plume.t))
                                                .replace("%2", Qt.locale(plume.locale).dayName(editor.startValue.getDay(), Locale.LongFormat)), value: "weekday" }]
            currentIndex: editor.rule.monthly === "weekday" ? 1 : 0
            onActivated: index => editor.setRule({ monthly: model[index].value, nth: index === 1 ? nth : 0 })
        }
    }
    // the end of a repetition: never, on a date, after N times
    RowLayout {
        visible: editor.preset !== "none" && editor.preset !== "keep"
        Layout.fillWidth: true
        spacing: 8
        WhenLabel { text: plume.t.rep_end }
        OComboBox {
            id: endKind
            Layout.preferredWidth: 170
            model: [{ text: plume.t.rep_end_never, value: "never" }, { text: plume.t.rep_end_on, value: "until" },
                    { text: plume.t.rep_end_after, value: "count" }]
            currentIndex: editor.rule.count > 0 ? 2 : editor.rule.until ? 1 : 0
            onActivated: index => {
                const kind = model[index].value
                if (kind === "never") editor.setRule({ count: 0, until: "" })
                else if (kind === "until") editor.setRule({ count: 0, until: D.iso(D.addMonths(editor.startValue, 3)) })
                else editor.setRule({ until: "", count: 10 })
            }
        }
        DateField {
            visible: !!editor.rule.until && !(editor.rule.count > 0)
            Layout.fillWidth: true
            value: editor.rule.until ? new Date(editor.rule.until + "T00:00") : new Date()
            onValueChanged: if (visible && D.iso(value) !== editor.rule.until) editor.setRule({ until: D.iso(value) })
        }
        Stepper {
            visible: editor.rule.count > 0
            from: 1; to: 999
            value: editor.rule.count || 10
            onEdited: v => editor.setRule({ count: v })
        }
        Text {
            visible: editor.rule.count > 0
            text: plume.t.rep_times_unit
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: theme.c.muted
        }
        Item { Layout.fillWidth: true }
    }
    Text {
        visible: editor.preset !== "none"
        Layout.fillWidth: true
        text: R.describe(editor.preset === "keep" ? { freq: "x", editable: false } : editor.rule, editor.startValue, Qt.locale(plume.locale), plume.t)
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.muted
    }
    }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { name: "calendar"; size: 18; color: theme.c.muted }
        OComboBox {
            id: calendarBox
            Layout.fillWidth: true
            model: agenda.calendars.filter(c => !c.readonly).map(c => ({ text: c.name, value: c.id, color: c.color }))
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { name: "pin"; size: 18; color: theme.c.muted }
        OTextField { id: location; Layout.fillWidth: true; placeholderText: plume.t.location_ph }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { name: "video"; size: 18; color: theme.c.muted }
        OButton {
            visible: !editor.meet
            kind: "accent"
            enabled: !editor.creatingMeet
            text: editor.creatingMeet ? "…" : plume.t.add_meet
            onClicked: { editor.creatingMeet = true; agenda.createMeet(title.text) }
        }
        Text {
            visible: !!editor.meet
            Layout.fillWidth: true
            text: editor.meet
            elide: Text.ElideMiddle
            font.family: "JetBrains Mono"; font.pixelSize: 12
            color: theme.c.accent
        }
        OButton { visible: !!editor.meet; kind: "quiet"; iconName: "close"; iconSize: 16; height_: 28; implicitWidth: 28; Accessible.name: plume.t.delete; onClicked: editor.meet = "" }
        Item { Layout.fillWidth: !editor.meet }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { Layout.alignment: Qt.AlignTop; Layout.topMargin: 10; name: "people"; size: 18; color: theme.c.muted }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Flow {
                Layout.fillWidth: true
                visible: editor.guests.length > 0
                spacing: 6
                Repeater {
                    model: editor.guests
                    Rectangle {
                        id: guestPill
                        required property string modelData
                        required property int index
                        readonly property bool opt: editor.optional.indexOf(modelData) >= 0
                        height: 30; radius: 15
                        width: guestRow.implicitWidth + 16
                        color: opt ? "transparent" : theme.c.hover
                        border.width: opt ? 1 : 0; border.color: theme.c.line
                        Row {
                            id: guestRow
                            anchors.centerIn: parent
                            spacing: 6
                            // a click on the name: required ↔ optional
                            AbstractButton {
                                id: guestToggle
                                anchors.verticalCenter: parent.verticalCenter
                                hoverEnabled: true
                                Accessible.name: guestPill.modelData
                                ToolTip.visible: hovered
                                ToolTip.delay: 450
                                ToolTip.text: guestPill.modelData + " · " + (guestPill.opt ? plume.t.guest_optional_tip : plume.t.guest_required_tip)
                                onClicked: editor.optional = guestPill.opt ? editor.optional.filter(e => e !== guestPill.modelData)
                                                                           : editor.optional.concat([guestPill.modelData])
                                background: null
                                contentItem: Text {
                                    text: editor.guestName(guestPill.modelData) + (guestPill.opt ? " · " + plume.t.guest_optional : "")
                                    textFormat: Text.PlainText
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    font.underline: guestToggle.hovered
                                    color: guestPill.opt ? theme.c.muted : theme.c.text
                                }
                            }
                            OButton {
                                anchors.verticalCenter: parent.verticalCenter
                                kind: "quiet"; iconName: "close"; iconSize: 12; height_: 20; implicitWidth: 20
                                tip: plume.t.delete
                                onClicked: { const g = editor.guests.slice(); g.splice(guestPill.index, 1); editor.guests = g }
                            }
                        }
                    }
                }
            }
            OTextField {
                id: guestField
                Layout.fillWidth: true
                placeholderText: plume.t.guests_ph
                property var hits: text.length > 0 ? people.suggest(text) : []
                function add(email) {
                    email = email.trim().toLowerCase()
                    if (email.indexOf("@") > 0 && editor.guests.indexOf(email) === -1)
                        editor.guests = editor.guests.concat([email])
                    text = ""
                }
                onAccepted: add(hits.length ? hits[0].email : text)
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_Comma || event.key === Qt.Key_Semicolon) { add(text); event.accepted = true }
                }
                Popup {
                    y: guestField.height + 4
                    width: guestField.width
                    visible: guestField.activeFocus && guestField.hits.length > 0
                    padding: 4
                    background: Rectangle { radius: 10; color: theme.c.overlay; border.width: 1; border.color: theme.c.overlayLine }
                    contentItem: Column {
                        Repeater {
                            model: guestField.hits
                            AbstractButton {
                                id: hit
                                required property var modelData
                                width: guestField.width - 8; height: 40
                                hoverEnabled: true
                                onClicked: guestField.add(modelData.email)
                                background: Rectangle { radius: 6; color: hit.hovered ? theme.c.hover : "transparent" }
                                contentItem: Row {
                                    spacing: 10; leftPadding: 8
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 26; height: 26; radius: 13; color: theme.c.tint
                                        Text { anchors.centerIn: parent; text: hit.modelData.initials; font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold; color: theme.c.tintText }
                                    }
                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter
                                        Text { text: hit.modelData.name; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: theme.c.text }
                                        Text { text: hit.modelData.email; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.muted }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    // availability: one bar per guest of the cloud, the event's slot outlined
    ColumnLayout {
        visible: editor.guests.length > 0 && editor.freeBusy.some(p => p.known)
        Layout.fillWidth: true
        Layout.leftMargin: 28
        spacing: 6
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: plume.t.availability
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.6
                color: theme.c.muted
            }
            Text {
                text: Math.floor(editor.viewFrom / 60) + " h – " + Math.ceil(editor.viewTo / 60) + " h"
                font.family: "JetBrains Mono"; font.pixelSize: 11
                color: theme.c.faint
            }
        }
        Repeater {
            model: editor.freeBusy
            RowLayout {
                id: fbRow
                required property var modelData
                Layout.fillWidth: true
                spacing: 10
                Text {
                    Layout.preferredWidth: 140
                    text: editor.guestName(fbRow.modelData.email)
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: fbRow.modelData.known ? theme.c.text : theme.c.muted
                }
                Rectangle {
                    id: bar
                    visible: fbRow.modelData.known
                    Layout.fillWidth: true
                    implicitHeight: 16
                    radius: 4
                    color: theme.c.hover
                    readonly property real scale: width / Math.max(1, editor.viewTo - editor.viewFrom)
                    Repeater {
                        model: fbRow.modelData.busy
                        Rectangle {
                            required property var modelData
                            readonly property int from: Math.max(editor.viewFrom, modelData[0])
                            readonly property int to: Math.min(editor.viewTo, modelData[1])
                            visible: to > from
                            x: (from - editor.viewFrom) * bar.scale
                            width: Math.max(2, (to - from) * bar.scale)
                            height: parent.height
                            radius: 4
                            color: editor.busyNow.indexOf(fbRow.modelData.email) >= 0 && modelData[0] < editor.slotTo && modelData[1] > editor.slotFrom
                                   ? theme.c.saffron : theme.c.faint
                        }
                    }
                    Rectangle {
                        x: (Math.max(editor.viewFrom, editor.slotFrom) - editor.viewFrom) * bar.scale
                        width: Math.max(2, (Math.min(editor.viewTo, editor.slotTo) - Math.max(editor.viewFrom, editor.slotFrom)) * bar.scale)
                        height: parent.height
                        radius: 4
                        color: "transparent"
                        border.width: 2; border.color: theme.c.accent
                    }
                }
                Text {
                    visible: !fbRow.modelData.known
                    Layout.fillWidth: true
                    text: plume.t.availability_unknown
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: theme.c.muted
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: editor.slotNote || (editor.busyNow.length ? plume.t.availability_busy.replace("%1", editor.busyNow.map(e => editor.guestName(e)).join(", "))
                                                               : plume.t.availability_free)
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                color: editor.busyNow.length && !editor.slotNote ? theme.c.saffronInk : theme.c.okInk
            }
            OButton {
                visible: editor.busyNow.length > 0 || editor.slotSearching
                kind: "secondary"
                height_: 28
                enabled: !editor.slotSearching
                text: editor.slotSearching ? plume.t.slot_searching : plume.t.slot_find
                onClicked: editor.findSlot()
            }
        }
    }
    // reminders: one pill each, then « Ajouter un rappel »
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { Layout.alignment: Qt.AlignTop; Layout.topMargin: 9; name: "clock"; size: 18; color: theme.c.muted }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: editor.alarms
                Rectangle {
                    id: alarmPill
                    required property string modelData
                    required property int index
                    height: 34; radius: 17
                    width: alarmRow.implicitWidth + 18
                    color: theme.c.hover
                    Row {
                        id: alarmRow
                        anchors.centerIn: parent
                        spacing: 4
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            leftPadding: 4
                            text: R.alarmLabel(alarmPill.modelData, allDaySwitch.checked, plume.t)
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.text
                        }
                        OButton {
                            anchors.verticalCenter: parent.verticalCenter
                            kind: "quiet"; iconName: "close"; iconSize: 12; height_: 22; implicitWidth: 22
                            tip: plume.t.alarm_remove
                            onClicked: { const a = editor.alarms.slice(); a.splice(alarmPill.index, 1); editor.alarms = a }
                        }
                    }
                }
            }
            OButton {
                id: addAlarm
                kind: "quiet"
                height_: 34
                iconName: "plus"
                text: editor.alarms.length ? plume.t.alarm_add_more : plume.t.alarm_add
                onClicked: alarmMenu.open()
                OMenu {
                    id: alarmMenu
                    y: addAlarm.height + 4
                    Repeater {
                        model: (allDaySwitch.checked ? R.ALL_DAY : R.TIMED).filter(m => editor.alarms.indexOf(String(m)) < 0)
                        OMenuItem {
                            required property int modelData
                            text: R.alarmLabel(modelData, allDaySwitch.checked, plume.t)
                            onTriggered: editor.alarms = editor.alarms.concat([String(modelData)])
                                                                  .sort((a, b) => parseInt(b) - parseInt(a))
                        }
                    }
                }
            }
            Text {
                visible: editor.otherAlarms > 0
                height: 34
                verticalAlignment: Text.AlignVCenter
                text: plume.t.alarm_others.replace("%1", editor.otherAlarms)
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: theme.c.muted
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Icon { Layout.alignment: Qt.AlignTop; Layout.topMargin: 12; name: "draft"; size: 18; color: theme.c.muted }
        OTextArea { id: notes; Layout.fillWidth: true; Layout.preferredHeight: 96; placeholderText: plume.t.notes_ph }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: editor.close() },
        OButton { kind: "primary"; text: plume.t.save; enabled: !editor.endInvalid; onClicked: editor.save() }
    ]
}
