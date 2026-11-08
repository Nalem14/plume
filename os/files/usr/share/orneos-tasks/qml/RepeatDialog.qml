// « Personnaliser… » the repeat of a task: every N days, weeks (on some days), months or years, and when it ends
// (never, on a date, after a number of times). The sentence under it says what was chosen, as the list will.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string key: ""
    property string due: ""
    property string freq: "WEEKLY"
    property int interval: 1
    property var days: []
    property string end: "never"
    property string until: ""
    property int count: 5
    readonly property var codes: ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    width: Math.min(460, parent ? parent.width - 48 : 460)
    title: app.t.repeat_title

    function openFor(k, rule) {
        key = k
        const d = tasks.detail(k)
        due = d.dueValue || new Date().toISOString().slice(0, 10)
        const p = tasks.ruleParts(rule)
        freq = p.freq; interval = p.interval; days = p.days; end = p.end; count = p.count
        if (p.until) until = p.until
        else { const u = new Date(due.slice(0, 10) + "T12:00"); u.setMonth(u.getMonth() + 3); until = isoOf(u) }
        open()
    }
    function isoOf(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") }
    function choice() { return { freq: freq, interval: interval, days: days, end: end, until: until, count: count } }
    function toggleDay(code) {
        const out = days.slice()
        const at = out.indexOf(code)
        if (at >= 0) out.splice(at, 1)
        else out.push(code)
        days = out
    }

    component Stepper: RowLayout {
        id: stepper
        property int value: 1
        property int minimum: 1
        property int maximum: 99
        signal moved(int value)
        spacing: 4
        OButton { kind: "quiet"; implicitWidth: 30; height_: 30; text: "−"; enabled: stepper.value > stepper.minimum; tip: "−"; onClicked: stepper.moved(stepper.value - 1) }
        TextField {
            implicitWidth: 52
            text: String(stepper.value)
            horizontalAlignment: Text.AlignHCenter
            validator: IntValidator { bottom: stepper.minimum; top: stepper.maximum }
            font.family: "JetBrains Mono"; font.pixelSize: 14
            color: dialog.c.text
            background: Rectangle { radius: 6; color: dialog.c.field; border.width: 1; border.color: parent.activeFocus ? dialog.c.action : dialog.c.line }
            onEditingFinished: if (acceptableInput) stepper.moved(parseInt(text))
            Accessible.name: dialog.title
        }
        OButton { kind: "quiet"; implicitWidth: 30; height_: 30; text: "+"; enabled: stepper.value < stepper.maximum; tip: "+"; onClicked: stepper.moved(stepper.value + 1) }
    }
    component Choice: AbstractButton {
        id: choiceBtn
        property bool on: false
        implicitWidth: 22; implicitHeight: 22
        Accessible.role: Accessible.RadioButton
        Accessible.checked: on
        background: Rectangle {
            radius: 11; color: "transparent"
            border.width: choiceBtn.on ? 6 : 1.5
            border.color: choiceBtn.on ? dialog.c.action : dialog.c.line
        }
    }
    component Label_: Text {
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.text
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Label_ { text: app.t.repeat_every }
        Stepper { value: dialog.interval; onMoved: v => dialog.interval = v }
        OComboBox {
            id: unit
            Layout.fillWidth: true
            model: [{ text: app.t.repeat_unit_days, value: "DAILY" }, { text: app.t.repeat_unit_weeks, value: "WEEKLY" },
                    { text: app.t.repeat_unit_months, value: "MONTHLY" }, { text: app.t.repeat_unit_years, value: "YEARLY" }]
            Component.onCompleted: select(dialog.freq)
            Connections { target: dialog; function onFreqChanged() { unit.select(dialog.freq) } }
            onActivated: dialog.freq = currentValue
        }
    }

    // the days of the week, for a weekly repeat (none chosen: the day of the date)
    ColumnLayout {
        Layout.fillWidth: true
        visible: dialog.freq === "WEEKLY"
        spacing: 6
        Text { text: app.t.repeat_on; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.muted }
        RowLayout {
            spacing: 6
            Repeater {
                model: 7
                AbstractButton {
                    id: dayBtn
                    required property int index
                    readonly property string code: dialog.codes[index]
                    readonly property bool on: dialog.days.indexOf(code) >= 0
                    implicitWidth: 36; implicitHeight: 36
                    hoverEnabled: true
                    Accessible.name: app.t.weekdays.split(",")[index]
                    Accessible.role: Accessible.CheckBox
                    Accessible.checked: on
                    ToolTip.text: app.t.weekdays.split(",")[index]; ToolTip.visible: hovered; ToolTip.delay: 500
                    onClicked: dialog.toggleDay(code)
                    background: Rectangle {
                        radius: 18
                        color: dayBtn.on ? dialog.c.action : dayBtn.hovered ? dialog.c.hover : dialog.c.field
                        border.width: dayBtn.on ? 0 : 1; border.color: dialog.c.line
                    }
                    contentItem: Text {
                        text: app.t.weekdays_letters.split(",")[dayBtn.index]
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                        color: dayBtn.on ? dialog.c.actionText : dialog.c.text
                    }
                }
            }
        }
    }
    Text {
        visible: dialog.freq === "MONTHLY"
        text: app.t.repeat_monthday.replace("%1", String(parseInt(dialog.due.slice(8, 10), 10) || ""))
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }

    Text { Layout.topMargin: 6; text: app.t.repeat_end; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.muted }
    RowLayout {
        spacing: 10
        Choice { on: dialog.end === "never"; onClicked: dialog.end = "never"; Accessible.name: app.t.repeat_end_never }
        Label_ { text: app.t.repeat_end_never; TapHandler { onTapped: dialog.end = "never" } }
    }
    RowLayout {
        spacing: 10
        Choice { on: dialog.end === "until"; onClicked: dialog.end = "until"; Accessible.name: app.t.repeat_end_on }
        Label_ { text: app.t.repeat_end_on; TapHandler { onTapped: dialog.end = "until" } }
        OButton {
            id: untilBtn
            height_: 30; iconName: "calendar"; iconSize: 15
            text: app.dateLabel(dialog.until)
            onClicked: { dialog.end = "until"; untilPicker.open() }
            DatePicker {
                id: untilPicker
                y: untilBtn.height + 4
                value: dialog.until
                onPicked: iso => { if (iso) dialog.until = iso }
            }
        }
    }
    RowLayout {
        spacing: 10
        Choice { on: dialog.end === "count"; onClicked: dialog.end = "count"; Accessible.name: app.t.repeat_end_after }
        Label_ { text: app.t.repeat_end_after; TapHandler { onTapped: dialog.end = "count" } }
        Stepper { value: dialog.count; maximum: 999; onMoved: v => { dialog.count = v; dialog.end = "count" } }
        Label_ { text: app.t.repeat_end_count }
    }

    Text {
        Layout.fillWidth: true
        Layout.topMargin: 8
        text: tasks.describeRule(tasks.buildRule(dialog.key, dialog.choice()))
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
        color: dialog.c.accent
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; text: app.t.save
            onClicked: { tasks.edit(dialog.key, { repeat: tasks.buildRule(dialog.key, dialog.choice()) }); dialog.close() }
        }
    ]
}
