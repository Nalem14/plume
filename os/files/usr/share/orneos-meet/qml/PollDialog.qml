// A new poll in the conversation: the question, two options or more, one answer or several, anonymous or not.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.new_poll
    tint: theme.c.famCommunicate
    property var options: ["", ""]

    function start() {
        question.text = ""
        options = ["", ""]
        multiple.checked = false
        anonymous.checked = false
        open()
        question.forceActiveFocus()
    }

    OTextField {
        id: question
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        placeholderText: app.t.poll_question
    }
    Repeater {
        model: dialog.options.length
        RowLayout {
            required property int index
            Layout.fillWidth: true
            Layout.leftMargin: 22; Layout.rightMargin: 22
            OTextField {
                Layout.fillWidth: true
                placeholderText: app.t.poll_option.replace("%1", parent.index + 1)
                text: dialog.options[parent.index]
                onTextChanged: if (dialog.options[parent.index] !== text) { const o = dialog.options.slice(); o[parent.index] = text; dialog.options = o }
            }
            OButton {
                visible: dialog.options.length > 2
                kind: "quiet"; iconName: "close"; tip: app.t.remove
                onClicked: { const o = dialog.options.slice(); o.splice(parent.index, 1); dialog.options = o }
            }
        }
    }
    OButton {
        Layout.leftMargin: 22
        kind: "quiet"; iconName: "plus"; text: app.t.poll_add_option
        onClicked: dialog.options = dialog.options.concat([""])
    }
    RowLayout {
        Layout.leftMargin: 22; Layout.rightMargin: 22
        OSwitch { id: multiple }
        Text { text: app.t.poll_multiple; color: theme.c.text; font.pixelSize: 14; Layout.fillWidth: true }
    }
    RowLayout {
        Layout.leftMargin: 22; Layout.rightMargin: 22
        OSwitch { id: anonymous }
        Text { text: app.t.poll_anonymous; color: theme.c.text; font.pixelSize: 14; Layout.fillWidth: true }
    }
    footer: [
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; text: app.t.poll_create
            enabled: question.text.trim() !== "" && dialog.options.filter(o => o.trim()).length >= 2
            onClicked: { meet.createPoll(question.text, dialog.options, multiple.checked, anonymous.checked); dialog.close() }
        }
    ]
}
