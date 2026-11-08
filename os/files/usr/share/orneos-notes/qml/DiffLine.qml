// One line of a comparison: the same in both (plain), only in the first (struck, red tint), only in the
// second (green tint), as in « Versions précédentes » and the choice after a conflict.
import QtQuick
import "components"

Rectangle {
    id: row
    readonly property var c: theme.c
    property var line: ({})
    readonly property bool here: line.kind === "here"
    readonly property bool other: line.kind === "other"
    implicitHeight: label.implicitHeight + 4
    radius: 4
    color: here ? Qt.alpha(c.danger, 0.12) : other ? Qt.alpha(c.ok, 0.16) : "transparent"
    Text {
        id: sign
        x: 6; y: 2
        width: 14
        text: row.here ? "−" : row.other ? "+" : ""
        font.family: "JetBrains Mono"; font.pixelSize: 13
        color: row.here ? row.c.danger : row.c.ok
    }
    Text {
        id: label
        x: 22; y: 2
        width: row.width - 28
        text: row.line.text || " "
        wrapMode: Text.WrapAtWordBoundaryOrAnywhere
        textFormat: Text.PlainText
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        font.strikeout: row.here
        color: row.here ? row.c.muted : row.c.body
    }
}
