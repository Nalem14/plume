// Which occurrences of a recurring event a change or a deletion is for: this one, this one and the following
// ones, or the whole series. One line each, the most common first; Enter takes the highlighted one.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ODialog {
    id: dialog
    property string message
    property var callback: null
    property string choice: "this"
    width: Math.min(440, parent ? parent.width - 48 : 440)
    tint: theme.c.famOrganize

    function ask(titleText, messageText, fn) {
        title = titleText
        message = messageText
        callback = fn
        choice = "this"
        open()
        list.forceActiveFocus()
    }
    function done() {
        close()
        if (callback)
            callback(choice)
    }

    Text {
        textFormat: Text.PlainText
        visible: dialog.message !== ""
        Layout.fillWidth: true
        text: dialog.message
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
        color: theme.c.text
    }
    ColumnLayout {
        id: list
        Layout.fillWidth: true
        spacing: 4
        focus: true
        readonly property var ids: ["this", "future", "all"]
        Keys.onUpPressed: dialog.choice = ids[Math.max(0, ids.indexOf(dialog.choice) - 1)]
        Keys.onDownPressed: dialog.choice = ids[Math.min(2, ids.indexOf(dialog.choice) + 1)]
        Keys.onReturnPressed: dialog.done()
        Keys.onEnterPressed: dialog.done()
        Repeater {
            model: [["this", plume.t.scope_this], ["future", plume.t.scope_future], ["all", plume.t.scope_all]]
            AbstractButton {
                id: option
                required property var modelData
                readonly property bool on: dialog.choice === modelData[0]
                Layout.fillWidth: true
                implicitHeight: 42
                hoverEnabled: true
                Accessible.role: Accessible.RadioButton
                Accessible.checked: on
                Accessible.name: modelData[1]
                onClicked: dialog.choice = modelData[0]
                onDoubleClicked: { dialog.choice = modelData[0]; dialog.done() }
                background: Rectangle {
                    radius: 8
                    color: option.on ? theme.c.tint : option.hovered ? theme.c.hover : "transparent"
                    border.width: option.on ? 1 : 0; border.color: theme.c.accentLine
                }
                contentItem: RowLayout {
                    spacing: 12
                    Rectangle {
                        Layout.leftMargin: 12
                        implicitWidth: 18; implicitHeight: 18; radius: 9
                        color: "transparent"
                        border.width: option.on ? 5 : 1.5
                        border.color: option.on ? theme.c.action : theme.c.line
                    }
                    Text {
                        Layout.fillWidth: true
                        text: option.modelData[1]
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: option.on ? Font.DemiBold : Font.Normal
                        color: theme.c.text
                    }
                }
            }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: plume.t.ok_scope; onClicked: dialog.done() }
    ]
}
