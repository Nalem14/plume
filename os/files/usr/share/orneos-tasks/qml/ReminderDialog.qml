// « À un moment précis… »: a reminder on a day and at a time of one's choice, with or without a due date
// (an absolute TRIGGER in the cloud, which the phone and the cloud's Tasks app show as well).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string key: ""
    property string day: ""
    property string clock: "09:00"
    width: Math.min(420, parent ? parent.width - 48 : 420)
    title: app.t.reminder_title

    function isoOf(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") }
    // at: the reminder there is (2026-11-06T09:00), else due: the date of the task
    function openFor(k, at, due) {
        key = k
        if (at) { day = at.slice(0, 10); clock = at.slice(11, 16) || "09:00" }
        else if (due) { day = due.slice(0, 10); clock = due.length > 10 ? due.slice(11, 16) : "09:00" }
        else {
            const next = new Date()
            next.setHours(next.getHours() + 1, 0, 0, 0)
            day = isoOf(next); clock = String(next.getHours()).padStart(2, "0") + ":00"
        }
        time.text = clock
        open()
    }
    function save() {
        const m = time.text.match(/^(\d{1,2}):(\d{2})$/)
        if (!m || +m[1] > 23 || +m[2] > 59) { time.forceActiveFocus(); return }
        tasks.edit(key, { alarm: "at:" + day + "T" + m[1].padStart(2, "0") + ":" + m[2] })
        close()
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        OButton {
            id: dayBtn
            Layout.fillWidth: true
            iconName: "calendar"; iconSize: 16
            text: app.dateLabel(dialog.day)
            onClicked: picker.open()
            DatePicker {
                id: picker
                y: dayBtn.height + 4
                value: dialog.day
                onPicked: iso => { if (iso) dialog.day = iso }
            }
        }
        TextField {
            id: time
            implicitWidth: 86; implicitHeight: 38
            inputMask: "99:99"
            horizontalAlignment: Text.AlignHCenter
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: dialog.c.text
            Accessible.name: app.t.time
            background: Rectangle { radius: 6; color: dialog.c.field; border.width: 1; border.color: time.activeFocus ? dialog.c.action : dialog.c.line }
            onAccepted: dialog.save()
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: app.t.save; onClicked: dialog.save() }
    ]
}
