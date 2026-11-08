// The day a photo was taken, changed (a scan, a camera set to the wrong date): one photo, its day and time;
// several, one day for all, each keeping its own time. Written into the files by the cloud.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property var ids: []
    readonly property bool many: ids.length > 1
    width: Math.min(420, parent ? parent.width - 48 : 420)
    tint: theme.c.famMedia
    title: many ? app.plural("date_title_many", ids.length) : app.t.date_title_one
    property bool bad: false

    // taken: « YYYY-MM-DDTHH:MM » when known (the viewer's details), else the day of the first photo
    function openFor(list, taken) {
        ids = list.slice()
        bad = false
        let t = String(taken || "")
        if (!t && ids.length) {
            const p = photos.photo(ids[0])
            if (p.dayid !== undefined) t = new Date(p.dayid * 86400000).toISOString().slice(0, 10) + "T12:00"
        }
        day.text = t.slice(0, 10)
        clock.text = t.length >= 16 ? t.slice(11, 16) : ""
        open()
        day.forceActiveFocus()
        day.selectAll()
    }
    function valid() {
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day.text.trim())
        if (!m) return false
        const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]))
        if (d.getUTCMonth() !== +m[2] - 1 || +m[1] < 1900 || d.getTime() > Date.now() + 86400000) return false
        return many || clock.text.trim() === "" || /^([01]\d|2[0-3]):[0-5]\d$/.test(clock.text.trim())
    }
    function accept() {
        if (!valid()) { bad = true; return }
        photos.setDate(ids, day.text.trim(), many ? "" : clock.text.trim())
        close()
    }

    Text {
        visible: dialog.many
        Layout.fillWidth: true
        text: app.t.date_lead_many
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text { text: app.t.date_day; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.muted }
            OTextField {
                id: day
                Layout.fillWidth: true
                placeholderText: "2026-07-14"
                inputMethodHints: Qt.ImhDate
                onTextChanged: dialog.bad = false
                onAccepted: dialog.accept()
            }
        }
        ColumnLayout {
            visible: !dialog.many
            Layout.preferredWidth: 110
            spacing: 4
            Text { text: app.t.date_time; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: theme.c.muted }
            OTextField {
                id: clock
                Layout.fillWidth: true
                placeholderText: "14:30"
                inputMethodHints: Qt.ImhTime
                onTextChanged: dialog.bad = false
                onAccepted: dialog.accept()
            }
        }
    }
    Text {
        visible: dialog.bad
        text: app.t.date_bad
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.danger
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: app.t.save; onClicked: dialog.accept() }
    ]
}
