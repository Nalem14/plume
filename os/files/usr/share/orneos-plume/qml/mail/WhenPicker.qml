// A day and a time to come: « Envoyer plus tard » and « Me le rappeler » when none of the usual moments fits.
// pickFor(title, fn): fn(timestamp in seconds) once chosen.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ODialog {
    id: dialog
    property var callback: null
    property string error
    width: Math.min(420, parent ? parent.width - 48 : 420)

    function pickFor(titleText, fn) {
        title = titleText
        callback = fn
        error = ""
        const tomorrow = new Date()
        tomorrow.setDate(tomorrow.getDate() + 1)
        day.value = tomorrow
        clock.value = "08:00"
        open()
    }
    function accept() {
        const parts = String(clock.value).split(":")
        const at = new Date(day.value.getFullYear(), day.value.getMonth(), day.value.getDate(),
                            parseInt(parts[0]) || 0, parseInt(parts[1]) || 0)
        if (at.getTime() < Date.now() + 60000) {
            error = plume.t.when_past
            return
        }
        close()
        if (callback)
            callback(at.getTime() / 1000)
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        DateField { id: day; Layout.fillWidth: true }
        TimeField { id: clock; Layout.preferredWidth: 110 }
    }
    Text {
        visible: dialog.error !== ""
        Layout.fillWidth: true
        text: dialog.error
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.danger
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: plume.t.when_ok; onClicked: dialog.accept() }
    ]
}
