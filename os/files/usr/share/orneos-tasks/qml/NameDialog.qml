// A name asked for (a new section, a section renamed): one field, Return saves.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property var onDone: null
    property string action: ""
    width: Math.min(420, parent ? parent.width - 48 : 420)

    function ask(heading, placeholder, initial, actionText, done) {
        title = heading
        field.placeholderText = placeholder
        field.text = initial || ""
        action = actionText
        onDone = done
        open()
        field.forceActiveFocus()
        field.selectAll()
    }
    function accept() {
        const text = field.text.trim()
        if (!text) return
        close()
        if (onDone) onDone(text)
    }

    OTextField {
        id: field
        Layout.fillWidth: true
        onAccepted: dialog.accept()
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: dialog.action || app.t.save; onClicked: dialog.accept() }
    ]
}
