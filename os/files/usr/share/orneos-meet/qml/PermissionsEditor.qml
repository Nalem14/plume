// Talk's permissions, one line each with its box: what everyone may do in a conversation, or one person.
// value is Talk's bit field; edited(value) when a box changes (bit 1, « Custom », is Talk's own).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: editor
    property int value: 0
    signal edited(int value)
    readonly property var c: theme.c
    readonly property var bits: [
        { bit: 2, icon: "phone", text: app.t.perm_start_call },
        { bit: 4, icon: "people", text: app.t.perm_join_call },
        { bit: 8, icon: "unlock", text: app.t.perm_lobby },
        { bit: 16, icon: "mic", text: app.t.perm_audio },
        { bit: 32, icon: "video", text: app.t.perm_video },
        { bit: 64, icon: "screen", text: app.t.perm_screen },
        { bit: 128, icon: "chat", text: app.t.perm_chat },
        { bit: 256, icon: "smile", text: app.t.perm_react }
    ]
    spacing: 0

    Repeater {
        model: editor.bits
        AbstractButton {
            id: line
            required property var modelData
            readonly property bool on: (editor.value & modelData.bit) !== 0
            Layout.fillWidth: true
            implicitHeight: 38
            hoverEnabled: true
            Accessible.role: Accessible.CheckBox
            Accessible.name: modelData.text
            Accessible.checked: on
            onClicked: editor.edited(on ? (editor.value & ~modelData.bit) : (editor.value | modelData.bit))
            background: Rectangle { radius: 8; color: line.hovered || line.visualFocus ? editor.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 12
                Rectangle {
                    Layout.leftMargin: 8
                    implicitWidth: 18; implicitHeight: 18; radius: 5
                    color: line.on ? editor.c.action : "transparent"
                    border.width: line.on ? 0 : 1.5; border.color: editor.c.line
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Icon { anchors.centerIn: parent; visible: line.on; name: "check"; size: 13; color: editor.c.actionText }
                }
                Icon { name: line.modelData.icon; size: 16; color: editor.c.muted }
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: line.modelData.text
                    font.pixelSize: 14; color: editor.c.text
                    elide: Text.ElideRight
                }
            }
        }
    }
}
