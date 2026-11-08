import QtQuick
import QtQuick.Controls

TextArea {
    id: area
    readonly property var c: theme.c
    color: c.text
    placeholderTextColor: c.muted
    selectionColor: c.tint
    selectedTextColor: c.text
    selectByMouse: true
    wrapMode: TextEdit.Wrap
    font.family: "Schibsted Grotesk"
    font.pixelSize: 15
    padding: 12
    background: Rectangle {
        radius: 6
        color: area.c.field
        border.width: area.activeFocus ? 2 : 1
        border.color: area.activeFocus ? area.c.action : area.c.line
    }
}
