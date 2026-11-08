// One line to type (a group's name): ask(title, text, placeholder, value, button, fn) runs fn(value).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ODialog {
    id: dialog
    property string message
    property string action
    property var callback: null
    width: Math.min(440, parent ? parent.width - 48 : 440)

    function ask(titleText, messageText, placeholder, value, actionText, fn) {
        title = titleText
        message = messageText
        field.placeholderText = placeholder
        field.text = value
        action = actionText
        callback = fn
        open()
        field.forceActiveFocus()
        field.selectAll()
    }
    function accept() {
        const value = field.text.trim()
        if (!value)
            return
        dialog.close()
        if (dialog.callback)
            dialog.callback(value)
    }

    Text {
        visible: dialog.message !== ""
        Layout.fillWidth: true
        text: dialog.message
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    OTextField {
        id: field
        Layout.fillWidth: true
        onAccepted: dialog.accept()
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"
            enabled: field.text.trim() !== ""
            opacity: enabled ? 1 : 0.5
            text: dialog.action
            onClicked: dialog.accept()
        }
    ]
}
