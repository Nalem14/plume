// A question with a few answers (one event or the series, delete or keep). choose(id) runs the callback.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ODialog {
    id: dialog
    property string message
    property var choices: []          // [{id, text, kind}]
    property var callback: null
    width: Math.min(460, parent ? parent.width - 48 : 460)

    function ask(titleText, messageText, options, fn) {
        title = titleText
        message = messageText
        choices = options
        callback = fn
        open()
    }

    Text { textFormat: Text.PlainText;
        visible: dialog.message !== ""
        Layout.fillWidth: true
        text: dialog.message
        wrapMode: Text.Wrap
        lineHeight: 1.3
        font.family: "Schibsted Grotesk"; font.pixelSize: 15
        color: theme.c.muted
    }

    footer: [
        Item { Layout.fillWidth: true },
        Repeater {
            model: dialog.choices
            OButton {
                required property var modelData
                kind: modelData.kind || "secondary"
                text: modelData.text
                onClicked: {
                    dialog.close()
                    if (modelData.id !== "cancel" && dialog.callback)
                        dialog.callback(modelData.id)
                }
            }
        }
    ]
}
