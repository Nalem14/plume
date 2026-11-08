// A calendar: made, followed from a link (webcal, .ics: holidays, a club, a school) or renamed and recoloured.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../components/colors.js" as Colors

ODialog {
    id: dialog
    property string mode: "new"              // "new" | "subscribe" | "edit"
    property int calendarId: 0
    property string color: palette[0]
    readonly property var palette: ["#002FA7", "#2F7D6D", "#8A5A00", "#1A5F7A", "#7A3B6E", "#C8381E", "#0F2440", "#6B7A93", "#F0A202"]
    readonly property bool urlOk: /^(webcals?|https?):\/\/[^\s]+\.[^\s]+/i.test(url.text.trim())
    width: Math.min(460, parent ? parent.width - 48 : 460)
    tint: theme.c.famOrganize
    title: mode === "subscribe" ? plume.t.cal_subscribe_title : mode === "edit" ? plume.t.cal_edit_title : plume.t.cal_new_title

    function openNew() {
        mode = "new"; calendarId = 0; name.text = ""; url.text = ""
        const used = agenda.calendars.map(c => c.color.toUpperCase())
        color = palette.find(p => used.indexOf(p) < 0) || palette[0]
        open(); name.forceActiveFocus()
    }
    function openSubscribe(link) {
        mode = "subscribe"; calendarId = 0; name.text = ""; url.text = link || ""
        color = palette[7]
        open(); (link ? name : url).forceActiveFocus()
    }
    function openEdit(cal) {
        mode = "edit"; calendarId = cal.id; name.text = cal.name; url.text = ""
        color = cal.color
        open(); name.forceActiveFocus(); name.selectAll()
    }
    function accept() {
        if (mode === "subscribe") {
            if (!urlOk) return
            agenda.subscribeCalendar(url.text.trim(), name.text.trim(), color)
            plume.toast(plume.t.cal_subscribed)
        } else if (mode === "edit") {
            const cal = agenda.calendars.find(c => c.id === calendarId)
            const newName = cal && name.text.trim() && name.text.trim() !== cal.name ? name.text.trim() : ""
            const newColor = cal && color !== cal.color ? color : ""
            if (newName || newColor) agenda.editCalendar(calendarId, newName, newColor)   // one change: both arrive
        } else {
            if (!name.text.trim()) return
            agenda.createCalendar(name.text.trim(), color)
        }
        close()
    }

    Text {
        visible: dialog.mode === "subscribe"
        Layout.fillWidth: true
        text: plume.t.cal_subscribe_hint
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    OTextField {
        id: url
        visible: dialog.mode === "subscribe"
        Layout.fillWidth: true
        placeholderText: "webcal://…"
        onAccepted: name.forceActiveFocus()
    }
    OTextField {
        id: name
        Layout.fillWidth: true
        placeholderText: dialog.mode === "subscribe" ? plume.t.cal_name_optional : plume.t.cal_name
        onAccepted: dialog.accept()
    }
    Flow {
        Layout.fillWidth: true
        spacing: 8
        Repeater {
            model: dialog.palette
            AbstractButton {
                id: swatch
                required property string modelData
                readonly property bool on: dialog.color.toUpperCase() === modelData.toUpperCase()
                width: 30; height: 30
                hoverEnabled: true
                Accessible.role: Accessible.RadioButton
                Accessible.checked: on
                Accessible.name: modelData
                onClicked: dialog.color = modelData
                background: Rectangle {
                    radius: 15
                    color: Colors.display(swatch.modelData, theme.dark)
                    border.width: swatch.on ? 3 : swatch.hovered ? 2 : 0
                    border.color: theme.c.card
                    Rectangle {
                        anchors.fill: parent; anchors.margins: -3; radius: 18; color: "transparent"
                        border.width: swatch.on ? 2 : 0; border.color: Colors.display(swatch.modelData, theme.dark)
                    }
                }
            }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"
            text: dialog.mode === "subscribe" ? plume.t.cal_subscribe : dialog.mode === "edit" ? plume.t.save : plume.t.cal_create
            enabled: dialog.mode === "subscribe" ? dialog.urlOk : name.text.trim() !== ""
            onClicked: dialog.accept()
        }
    ]
}
